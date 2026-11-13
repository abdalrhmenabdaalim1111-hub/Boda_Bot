"""
tests/test_control_center_supervisor.py — اختبارات مشرف البوتات

تغطي:
• اكتشاف البوتات من السجل
• التشغيل / الإيقاف / إعادة التشغيل
• الحالة الحيّة (running / uptime / pid)
• التقاط السجلات وتصفيتها حسب المستوى
• تفعيل / تعطيل بوت
• إعادة التشغيل التلقائي بعد الانهيار (backoff)
• رفض تشغيل بوت يسيطر عليه server_runner آخر
"""

import io
import json
import time

import pytest

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401  (path bootstrap)

from control_center.supervisor import BotSupervisor, detect_level

ERROR_MARK = "\u274c"      # cross mark
WARNING_MARK = "\u26a0"    # warning sign
SUCCESS_MARK = "\u2705"    # check mark


class FakeProcess:
    """A stand-in for ``subprocess.Popen`` used by the tests."""

    _next_pid = [41000]

    def __init__(self, lines=(), exit_code=0):
        FakeProcess._next_pid[0] += 1
        self.pid = FakeProcess._next_pid[0]
        self.returncode = None
        self._exit_code = exit_code
        self.stdout = io.StringIO("".join(f"{line}\n" for line in lines))
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = self._exit_code

    def kill(self):
        self.killed = True
        self.returncode = self._exit_code

    def crash(self, code=1):
        """Simulate an unexpected exit."""
        self.returncode = code


@pytest.fixture()
def registry(tmp_path):
    path = tmp_path / "bots_registry.json"
    path.write_text(json.dumps([
        {"id": "alpha", "name": "Alpha", "file": "bot_alpha.py",
         "category": "tools", "emoji": "A"},
        {"id": "beta", "name": "Beta", "file": "bot_beta.py",
         "category": "fun", "emoji": "B"},
    ]), encoding="utf-8")
    return path


@pytest.fixture()
def supervisor(registry, tmp_path):
    """A supervisor wired to a fake process factory."""
    created = []

    def _spawner(bot_id):
        proc = FakeProcess(lines=[f"started {bot_id}", "ERROR something failed"])
        created.append(proc)
        return proc

    bots_dir = tmp_path / "Bots_Folder"
    bots_dir.mkdir()
    for name in ("bot_alpha.py", "bot_beta.py"):
        (bots_dir / name).write_text("# fake\n", encoding="utf-8")

    sup = BotSupervisor(base_dir=tmp_path, registry_path=registry,
                        spawner=_spawner)
    sup.created = created
    yield sup
    sup.shutdown()


def test_discover_reads_registry(supervisor):
    """اكتشاف البوتات من سجل البوتات"""
    ids = [entry["id"] for entry in supervisor.discover()]
    assert ids == ["alpha", "beta"]
    assert all(entry["registered"] for entry in supervisor.discover())


def test_start_marks_bot_running(supervisor):
    """التشغيل يغيّر الحالة إلى running"""
    result = supervisor.start("alpha")
    assert result["ok"] is True
    state = supervisor.state("alpha")
    assert state.running is True
    assert state.pid > 0
    assert state.started_at > 0


def test_start_twice_is_a_noop(supervisor):
    """التشغيل مرتين لا يولّد عمليتين"""
    supervisor.start("alpha")
    pid = supervisor.state("alpha").pid
    result = supervisor.start("alpha")
    assert result.get("already_running") is True
    assert supervisor.state("alpha").pid == pid


def test_stop_marks_bot_stopped(supervisor):
    """الإيقاف يوقف العملية ويحدّث الحالة"""
    supervisor.start("alpha")
    result = supervisor.stop("alpha")
    assert result["ok"] is True
    state = supervisor.state("alpha")
    assert state.running is False
    assert state.pid == 0
    assert supervisor.created[0].terminated is True


def test_restart_replaces_the_process(supervisor):
    """إعادة التشغيل تُنهي العملية وتُشغّل عملية جديدة"""
    supervisor.start("alpha")
    first_pid = supervisor.state("alpha").pid
    result = supervisor.restart("alpha")
    assert result.get("restarted") is True
    assert supervisor.state("alpha").pid != first_pid
    assert supervisor.state("alpha").running is True


def test_status_reports_uptime_and_flags(supervisor):
    """الحالة تعرض التشغيل ومدة التشغيل"""
    supervisor.start("alpha")
    status = {item["bot_id"]: item for item in supervisor.status()}
    assert status["alpha"]["running"] is True
    assert status["alpha"]["uptime_seconds"] >= 0
    assert status["beta"]["running"] is False


def test_logs_are_captured_and_filtered(supervisor):
    """السجلات تُلتقط من مخرجات العملية ويمكن تصفيتها"""
    supervisor.start("alpha")
    time.sleep(0.4)

    lines = supervisor.logs("alpha", limit=50)
    assert lines
    assert any("started" in item["line"] for item in lines)

    errors = supervisor.logs("alpha", limit=50, level="error")
    assert errors
    assert all(item["level"] == "error" for item in errors)


def test_detect_level():
    """كشف مستوى السطر من العلامات المعروفة"""
    assert detect_level(f"{ERROR_MARK} failure") == "error"
    assert detect_level(f"{WARNING_MARK} slow") == "warning"
    assert detect_level(f"{SUCCESS_MARK} done") == "info"
    assert detect_level("plain line") == "info"
    assert detect_level("") == "info"


def test_enable_disable(supervisor):
    """التفعيل والتعطيل يغيّران حالة البوت"""
    supervisor.set_enabled("alpha", False)
    assert supervisor.state("alpha").enabled is False
    supervisor.set_enabled("alpha", True)
    assert supervisor.state("alpha").enabled is True


def test_disabled_bot_is_not_started(supervisor):
    """البوت المعطّل لا يُشغَّل"""
    supervisor.set_enabled("alpha", False)
    result = supervisor.start("alpha")
    assert result["ok"] is False
    assert result["error"] == "bot is disabled"


def test_start_all_and_stop_all(supervisor):
    """تشغيل وإيقاف كل البوتات"""
    started = supervisor.start_all()
    assert len(started) == 2
    assert all(item["ok"] for item in started)

    stopped = supervisor.stop_all()
    assert len(stopped) == 2
    assert supervisor.state("alpha").running is False


def test_auto_restart_after_crash(supervisor, monkeypatch):
    """البوت المنهار يُعاد تشغيله تلقائياً"""
    import control_center.supervisor as sup_module
    monkeypatch.setattr(sup_module.config, "backoff_base", lambda: 1)
    monkeypatch.setattr(sup_module.config, "backoff_max", lambda: 1)

    supervisor.start("alpha")
    supervisor.created[0].crash(code=7)

    deadline = time.time() + 8
    restarted = False
    while time.time() < deadline:
        supervisor._check_crashed()
        if len(supervisor.created) > 1:
            restarted = True
            break
        time.sleep(0.2)

    assert restarted is True
    assert supervisor.state("alpha").restarts >= 1
    assert supervisor.state("alpha").last_exit_code == 7


def test_external_runner_blocks_start(supervisor, monkeypatch):
    """لا يمكن تشغيل بوت يسيطر عليه server_runner آخر"""
    monkeypatch.setattr(supervisor, "_server_runner_active", lambda: True)
    result = supervisor.start("alpha")
    assert result["ok"] is False
    assert "server_runner" in result["error"]


def test_subscribe_receives_new_lines(supervisor):
    """المشترك يستقبل السطور الجديدة"""
    received = []
    supervisor.subscribe("alpha", received.append)
    supervisor._append_log("alpha", "hello world")
    assert received and received[0]["line"] == "hello world"
