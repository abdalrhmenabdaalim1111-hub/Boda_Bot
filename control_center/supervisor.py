"""
control_center/supervisor.py — the bot process supervisor.

The project historically had three different process managers (Tkinter
``Manager.py``, console ``StartManager.py`` and the headless
``server_runner.py``). This module implements **one** supervisor that the
Control Center API, the CLI and — later — the Tkinter manager all use.

Design decisions
----------------
* **One process per bot.** A fresh process is the only reliable way to pick
  up new code after a restart, and it isolates a crashing bot from the API.
* **Exponential backoff.** A crashing bot is restarted after
  ``backoff_base`` seconds, doubling up to ``backoff_max``.
* **Never two owners.** Starting a bot that is already owned by a running
  ``server_runner.py`` is refused — two pollers on the same token make
  Telegram return 409 Conflict.
* **Graceful shutdown.** ``SIGTERM`` first, then ``SIGKILL`` after a grace
  period, so bots can close their Telegram sessions cleanly.
"""

import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from . import config

# Log-line heuristics: the project logger does not emit a level field, so the
# supervisor infers one from well known markers.
_LEVEL_MARKERS = (
    ("critical", ("critical", "fatal", "💀")),
    ("error", ("error", "exception", "traceback", "❌", "✖")),
    ("warning", ("warning", "warn", "⚠")),
    ("info", ("info", "✅", "🚀", "🌐", "📡")),
)


def detect_level(line: str) -> str:
    """Best-effort log level for a raw log line."""
    if not line:
        return "info"
    lowered = line.lower()
    for level, markers in _LEVEL_MARKERS:
        for marker in markers:
            if marker in lowered:
                return level
    return "info"


@dataclass
class BotState:
    """Live state of a single managed bot."""

    bot_id: str
    tier: str = "light"
    enabled: bool = True
    running: bool = False
    pid: int = 0
    started_at: float = 0.0
    stopped_at: float = 0.0
    restarts: int = 0
    last_error: str = ""
    last_exit_code: int = 0
    auto_restart: bool = True
    backoff: float = 0.0
    next_restart_at: float = 0.0
    script_path: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def as_dict(self) -> dict:
        uptime = 0
        if self.running and self.started_at:
            uptime = int(max(0, time.time() - self.started_at))
        return {
            "bot_id": self.bot_id,
            "tier": self.tier,
            "enabled": self.enabled,
            "running": self.running,
            "pid": self.pid,
            "uptime_seconds": uptime,
            "started_at": (time.strftime("%Y-%m-%dT%H:%M:%S",
                                        time.localtime(self.started_at))
                           if self.started_at else ""),
            "restarts": self.restarts,
            "last_error": self.last_error,
            "last_exit_code": self.last_exit_code,
            "auto_restart": self.auto_restart,
            "next_restart_at": (int(self.next_restart_at)
                                if self.next_restart_at else 0),
            "script_path": self.script_path,
        }


class BotSupervisor:
    """Starts, stops, restarts and observes the bot processes."""

    def __init__(self, base_dir: Path | None = None,
                 registry_path: Path | None = None,
                 logger=None,
                 spawner=None):
        self.base_dir = Path(base_dir or config.BASE_DIR)
        self.bots_dir = self.base_dir / "Bots_Folder"
        self.registry_path = Path(registry_path or config.REGISTRY_PATH)
        self.log = logger
        self._spawner = spawner          # injectable for tests
        self._states: dict = {}
        self._procs: dict = {}
        self._buffers: dict = {}
        self._subscribers: dict = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor = None
        self._tail_size = config.log_tail_size()
        self._runner_checked_at = 0.0
        self._runner_active = False
        self._runner_cache_ttl = 30.0
        self._session_queue = queue.Queue()
        self._session_thread = None

    # ── Logging helper ──────────────────────────────────────────────────────
    def _info(self, msg: str):
        if self.log:
            self.log.info(msg)

    def _error(self, msg: str):
        if self.log:
            self.log.error(msg)

    # ── Discovery ───────────────────────────────────────────────────────────
    def discover(self) -> list:
        """
        Return the catalogue of known bots.

        The registry is the source of truth (decision D4); bots that exist on
        disk but are not registered are still reported so the UI can offer to
        register them.
        """
        import json
        entries = []
        seen = set()
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text(encoding="utf-8"))
                bots = data if isinstance(data, list) else data.get("bots", [])
                for bot in bots:
                    bot_id = str(bot.get("id") or "").strip()
                    if not bot_id or bot_id in seen:
                        continue
                    seen.add(bot_id)
                    entries.append({
                        "id": bot_id,
                        "name": bot.get("name") or bot_id,
                        "emoji": bot.get("emoji", "🤖"),
                        "category": bot.get("category", ""),
                        "tag": bot.get("tag", ""),
                        "username": bot.get("username", ""),
                        "tier": bot.get("tier", "light"),
                        "file": bot.get("file") or f"bot_{bot_id}.py",
                        "registered": True,
                    })
            except Exception:
                pass

        # Bots present on disk but missing from the registry.
        if self.bots_dir.exists():
            for path in sorted(self.bots_dir.glob("bot_*.py")):
                bot_id = path.stem[4:]
                if not bot_id or bot_id in seen:
                    continue
                if bot_id in ("template",):
                    continue
                seen.add(bot_id)
                entries.append({
                    "id": bot_id,
                    "name": bot_id,
                    "emoji": "🤖",
                    "category": "",
                    "tag": "",
                    "username": "",
                    "tier": "light",
                    "file": path.name,
                    "registered": False,
                })
        return entries

    def script_for(self, bot_id: str) -> Path:
        """Resolve the module file of a bot."""
        for entry in self.discover():
            if entry["id"] == bot_id:
                return self.bots_dir / (entry.get("file") or f"bot_{bot_id}.py")
        return self.bots_dir / f"bot_{bot_id}.py"

    # ── State ───────────────────────────────────────────────────────────────
    def state(self, bot_id: str) -> BotState:
        with self._lock:
            if bot_id not in self._states:
                tier = "light"
                for entry in self.discover():
                    if entry["id"] == bot_id:
                        tier = entry.get("tier", "light")
                        break
                self._states[bot_id] = BotState(
                    bot_id=bot_id,
                    tier=tier,
                    auto_restart=config.auto_restart_default(),
                    script_path=str(self.script_for(bot_id)),
                )
            return self._states[bot_id]

    def set_enabled(self, bot_id: str, enabled: bool) -> BotState:
        """Enable or disable a bot (disabled bots are never auto-restarted)."""
        state = self.state(bot_id)
        with state.lock:
            state.enabled = bool(enabled)
        return state

    # ── Process control ─────────────────────────────────────────────────────
    def _server_runner_active(self) -> bool:
        """
        Detect an external ``server_runner.py`` that already owns the bots.

        The result is cached for a few seconds: the check walks the whole
        process table, and ``start_all`` would otherwise repeat it once per
        bot (34 scans on Windows is far too slow).
        """
        now = time.time()
        with self._lock:
            if self._runner_checked_at and (now - self._runner_checked_at) < self._runner_cache_ttl:
                return self._runner_active

        active = self._scan_for_runner()
        with self._lock:
            self._runner_checked_at = now
            self._runner_active = active
        return active

    def _scan_for_runner(self) -> bool:
        """
        Walk the process table looking for a foreign ``server_runner.py``.

        Reading the command line of every process on Windows costs several
        seconds, so the (cheap) process name is checked first and only
        Python processes are inspected in detail.
        """
        try:
            import psutil
        except ImportError:
            return False
        me = os.getpid()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pid = proc.info.get("pid")
                name = (proc.info.get("name") or "").lower()
                if not pid or pid == me:
                    continue
                if "python" not in name and "boda" not in name:
                    continue
                cmdline = proc.cmdline()
                if any("server_runner.py" in part for part in cmdline):
                    return True
            except Exception:
                continue
        return False

    def _build_env(self, bot_id: str | None = None) -> dict:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("PYTHONPATH", str(self.base_dir))
        if bot_id:
            try:
                from . import botconfig, crypto
                token = botconfig.resolve_token(bot_id)
                if token:
                    env[crypto.env_var_name(bot_id)] = token
            except Exception:
                pass
        return env

    def _spawn(self, bot_id: str):
        """Launch the bot process. Overridable in tests."""
        if self._spawner:
            return self._spawner(bot_id)
        script = self.script_for(bot_id)
        if not script.exists():
            raise FileNotFoundError(f"bot module not found: {script.name}")
        return subprocess.Popen(
            [sys.executable, "-u", str(script)],
            cwd=str(self.base_dir),
            env=self._build_env(bot_id),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                           if sys.platform == "win32" else 0),
        )

    def start(self, bot_id: str, force: bool = False, runner_active=None) -> dict:
        """
        Start a bot.

        ``runner_active`` lets a batch operation (``start_all``) perform the
        expensive external-runner detection once and reuse the result.

        Returns a result dict; ``ok`` tells whether the bot is running.
        """
        state = self.state(bot_id)
        with self._lock:
            if bot_id in self._procs and self._procs[bot_id].poll() is None:
                return {"ok": True, "already_running": True, "bot_id": bot_id}
        if not state.enabled and not force:
            return {"ok": False, "error": "bot is disabled", "bot_id": bot_id}
        if runner_active is None:
            runner_active = self._server_runner_active()
        if runner_active and not force:
            return {
                "ok": False,
                "error": "another server_runner.py instance already owns the bots; "
                         "stop it first or use force=true",
                "bot_id": bot_id,
            }

        # Guard: heavy bots require adequate system memory to prevent host freeze
        if state.tier == "heavy" and not force:
            try:
                import psutil
                vm = psutil.virtual_memory()
                if vm.percent > 95:
                    return {
                        "ok": False,
                        "error": f"Memory critically low ({vm.percent}% used); heavy bot '{bot_id}' delayed to protect host stability",
                        "bot_id": bot_id,
                    }
            except Exception:
                pass

        try:
            proc = self._spawn(bot_id)
        except Exception as exc:
            with state.lock:
                state.last_error = str(exc)
                state.last_exit_code = -1
            self._error(f"✖ [{bot_id}] فشل التشغيل: {exc}")
            return {"ok": False, "error": str(exc), "bot_id": bot_id}

        with self._lock:
            self._procs[bot_id] = proc
            self._buffers.setdefault(bot_id, deque(maxlen=self._tail_size))
            with state.lock:
                state.running = True
                state.pid = proc.pid
                state.started_at = time.time()
                state.backoff = 0.0
                state.next_restart_at = 0.0

        self._record_session_start(bot_id)
        self._info(f"▶ [{bot_id}] بدأ التشغيل (pid={proc.pid})")
        threading.Thread(target=self._read_output, args=(bot_id, proc),
                         name=f"cc-logs-{bot_id}", daemon=True).start()
        return {"ok": True, "bot_id": bot_id, "pid": proc.pid}

    def stop(self, bot_id: str, timeout: float = 8.0) -> dict:
        """Stop a bot gracefully (SIGTERM, then SIGKILL)."""
        with self._lock:
            proc = self._procs.pop(bot_id, None)
        state = self.state(bot_id)
        if proc is None:
            with state.lock:
                state.running = False
                state.pid = 0
            return {"ok": True, "already_stopped": True, "bot_id": bot_id}

        self._info(f"⏹ [{bot_id}] إيقاف (pid={proc.pid})")
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.kill(proc.pid, signal.SIGTERM)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        deadline = time.time() + max(1.0, timeout)
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        else:
            try:
                proc.kill()
            except Exception:
                pass

        with state.lock:
            state.running = False
            state.pid = 0
            state.stopped_at = time.time()
            state.next_restart_at = 0.0
        self._record_session_stop(bot_id, proc.returncode or 0)
        return {"ok": True, "bot_id": bot_id}

    def restart(self, bot_id: str) -> dict:
        """Stop then start a bot — the restart picks up the new code."""
        self.stop(bot_id)
        time.sleep(0.4)
        result = self.start(bot_id)
        result["restarted"] = True
        return result

    def start_all(self, only_enabled: bool = True) -> list:
        """
        Start every known bot.

        The external-runner detection is performed **once** for the whole
        batch — it walks the process table and is far too slow to repeat for
        every bot.
        """
        results = []
        runner_active = self._server_runner_active()
        for entry in self.discover():
            bot_id = entry["id"]
            state = self.state(bot_id)
            if only_enabled and not state.enabled:
                continue
            results.append(self.start(bot_id, runner_active=runner_active))
        return results

    def stop_all(self) -> list:
        """Stop every running bot."""
        results = []
        with self._lock:
            bot_ids = list(self._procs.keys())
        for bot_id in bot_ids:
            results.append(self.stop(bot_id))
        return results

    # ── Auto-restart monitor ────────────────────────────────────────────────
    def start_monitor(self) -> threading.Thread:
        """Start the background thread that restarts crashed bots."""
        self._start_session_recorder()
        if self._monitor and self._monitor.is_alive():
            return self._monitor

        def _loop():
            while not self._stop_event.wait(1.0):
                self._check_crashed()

        self._stop_event.clear()
        self._monitor = threading.Thread(target=_loop, name="cc-supervisor",
                                         daemon=True)
        self._monitor.start()
        return self._monitor

    def _check_crashed(self) -> None:
        now = time.time()
        with self._lock:
            dead = [(bid, proc) for bid, proc in self._procs.items()
                    if proc.poll() is not None]
        for bot_id, proc in dead:
            with self._lock:
                self._procs.pop(bot_id, None)
            state = self.state(bot_id)
            exit_code = proc.returncode or 0
            with state.lock:
                state.running = False
                state.pid = 0
                state.last_exit_code = exit_code
                if exit_code:
                    state.last_error = f"process exited with code {exit_code}"
                state.backoff = (config.backoff_base() if not state.backoff
                                 else min(state.backoff * 2, config.backoff_max()))
                state.next_restart_at = now + state.backoff
                should_restart = (state.enabled and state.auto_restart
                                  and not self._stop_event.is_set())
            self._record_session_stop(bot_id, exit_code)
            self._error(f"✖ [{bot_id}] توقف غير متوقع (code={exit_code})")
            if should_restart:
                self._info(f"↻ [{bot_id}] إعادة تشغيل بعد {state.backoff:.0f}ث")
                result = self.start(bot_id)
                if result.get("ok"):
                    with state.lock:
                        state.restarts += 1

    def shutdown(self) -> None:
        """Stop everything and terminate the monitor thread."""
        self._stop_event.set()
        self.stop_all()

    # ── Logging ─────────────────────────────────────────────────────────────
    def _read_output(self, bot_id: str, proc) -> None:
        """Consume the process output into the in-memory ring buffer."""
        stream = getattr(proc, "stdout", None)
        if stream is None:
            return
        try:
            for raw in iter(stream.readline, ""):
                if not raw:
                    break
                line = raw.rstrip("\n")
                self._append_log(bot_id, line)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _append_log(self, bot_id: str, line: str) -> None:
        entry = {"ts": time.time(), "line": line, "level": detect_level(line)}
        with self._lock:
            buf = self._buffers.setdefault(bot_id, deque(maxlen=self._tail_size))
            buf.append(entry)
            subscribers = list(self._subscribers.get(bot_id, []))
        for callback in subscribers:
            try:
                callback(entry)
            except Exception:
                pass

    def logs(self, bot_id: str = "", limit: int = 200, level: str = "") -> list:
        """
        Return recent log lines.

        ``level`` filters on the detected level (``error``, ``warning``,
        ``info``). An empty ``bot_id`` merges every known bot.
        """
        with self._lock:
            if bot_id:
                buffers = {bot_id: self._buffers.get(bot_id, deque())}
            else:
                buffers = dict(self._buffers)
        wanted = (level or "").strip().lower()
        lines = []
        for bid, buf in buffers.items():
            for entry in buf:
                if wanted and entry["level"] != wanted:
                    continue
                lines.append({"bot_id": bid, **entry})
        lines.sort(key=lambda item: item["ts"])
        return lines[-max(1, min(int(limit), 5000)):]

    def subscribe(self, bot_id: str, callback) -> None:
        """Register a callback invoked for every new log line of a bot."""
        with self._lock:
            self._subscribers.setdefault(bot_id, []).append(callback)

    def unsubscribe(self, bot_id: str, callback) -> None:
        with self._lock:
            handlers = self._subscribers.get(bot_id, [])
            if callback in handlers:
                handlers.remove(callback)

    # ── Persistence ─────────────────────────────────────────────────────────
    def _record_session_start(self, bot_id: str) -> None:
        """Queue a session-start record (processed in the background)."""
        self._session_queue.put((bot_id, "start", 0))

    def _record_session_stop(self, bot_id: str, exit_code: int = 0) -> None:
        """Queue a session-stop record (processed in the background)."""
        self._session_queue.put((bot_id, "stop", exit_code))

    def _session_recorder_loop(self) -> None:
        """
        Write session bookkeeping to the database in the background.

        Writing a session row opens a database connection, which costs ~100 ms
        on Windows. Doing that inline would make "start all" (34 bots) take
        several seconds and delay the HTTP response — so it happens here.
        """
        while not self._stop_event.is_set():
            try:
                bot_id, action, exit_code = self._session_queue.get(timeout=1.0)
            except Exception:
                continue
            try:
                from database import get_db
                db = get_db()
                if not db:
                    continue
                if action == "start":
                    db.record_bot_start(bot_id)
                else:
                    db.record_bot_stop(bot_id, exit_code=exit_code)
            except Exception:
                pass
            finally:
                try:
                    self._session_queue.task_done()
                except Exception:
                    pass

    def _start_session_recorder(self) -> None:
        if self._session_thread and self._session_thread.is_alive():
            return
        self._session_thread = threading.Thread(
            target=self._session_recorder_loop, name="cc-sessions", daemon=True)
        self._session_thread.start()

    # ── Introspection ───────────────────────────────────────────────────────
    def status(self) -> list:
        """Full status of every known bot."""
        result = []
        for entry in self.discover():
            bot_id = entry["id"]
            state = self.state(bot_id)
            data = state.as_dict()
            data.update({
                "name": entry.get("name", bot_id),
                "emoji": entry.get("emoji", "🤖"),
                "category": entry.get("category", ""),
                "registered": entry.get("registered", False),
                "last_error": state.last_error or self._latest_db_error(bot_id),
            })
            result.append(data)
        return result

    @staticmethod
    def _latest_db_error(bot_id: str) -> str:
        try:
            from database import get_db
            db = get_db()
            if not db:
                return ""
            rows = db.get_recent_errors(bot_id, limit=1)
            if not rows:
                return ""
            row = rows[0]
            return f"{row.get('error_type', 'error')}: {row.get('error_message', '')}"[:200]
        except Exception:
            return ""
