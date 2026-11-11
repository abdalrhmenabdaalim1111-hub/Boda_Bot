# =============================================================================
#  ██████╗  ██████╗ ██████╗  █████╗     ██████╗  ██████╗ ████████╗
#  ██╔══██╗██╔═══██╗██╔══██╗██╔══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
#  ██████╔╝██║   ██║██║  ██║███████║    ██████╔╝██║   ██║   ██║
#  ██╔══██╗██║   ██║██║  ██║██╔══██║    ██╔══██╗██║   ██║   ██║
#  ██████╔╝╚██████╔╝██████╔╝██║  ██║    ██████╔╝╚██████╔╝   ██║
#  ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝  ╚═╝    ╚═════╝  ╚═════╝   ╚═╝
#
#  Telegram Bot Manager v4.1 — Modular Architecture Edition
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess, sys, os, threading, queue, time, json, signal, socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ── تحميل .env ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ── Single-Instance Lock ──────────────────────────────────────────────────────
_LOCK_PORT = 47291
_lock_sock = None

def _acquire_instance_lock():
    global _lock_sock
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s.bind(("127.0.0.1", _LOCK_PORT))
        _lock_sock = s
        return True
    except OSError:
        return False

if not _acquire_instance_lock():
    import tkinter as _tk, tkinter.messagebox as _mb
    _r = _tk.Tk(); _r.withdraw()
    _mb.showerror(
        "Boda Bot Manager — نسخة تعمل بالفعل",
        "⚠️  هناك نسخة من Boda Bot Manager تعمل بالفعل!\n\n"
        "تشغيل نسختين في نفس الوقت يسبب خطأ 409 Conflict\n"
        "في بوتات تيليجرام.\n\n"
        "أغلق النسخة الأولى أولاً ثم افتح هذه.\n\n"
        "🔍 ابحث عن 'Manager.py' في مدير المهام وأغلقه."
    )
    _r.destroy()
    sys.exit(0)

# ── إعداد sys.path لاستيراد مكونات ui/ ───────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── استيراد مكونات UI ─────────────────────────────────────────────────────────
from ui.theme    import C, BOT_COLORS, apply_styles
from ui.header   import Header
from ui.bot_list import BotListPanel
from ui.log_panel import LogPanel
from ui.stats_panel import StatsPanel
from ui.statusbar import StatusBar

# ── Configuration ─────────────────────────────────────────────────────────────
BOTS_FOLDER   = "Bots_Folder"
CONFIG_FILE   = "manager_config.json"
REGISTRY_FILE = "bots_registry.json"
RESTART_DELAY = 5
POLL_INTERVAL = 1

# ── Data Model ─────────────────────────────────────────────────────────────────
@dataclass
class BotEntry:
    name:             str
    path:             str
    color:            str    = "#79c0ff"
    process:          object = None
    status:           str    = "stopped"
    pid:              int    = 0
    start_time:       float  = 0.0
    restart_count:    int    = 0
    auto_restart:     bool   = True
    manually_stopped: bool   = False
    log_queue:        object = field(default_factory=queue.Queue)
    last_error:       str    = ""
    cpu_percent:      float  = 0.0
    mem_mb:           float  = 0.0
    has_token:        bool   = True
    token:            str    = ""

    @property
    def uptime(self) -> str:
        if self.status != "running" or not self.start_time:
            return "—"
        s = int(time.time() - self.start_time)
        h, r = divmod(s, 3600); m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @property
    def display_name(self) -> str:
        return self.name.replace("bot_", "").replace("_", " ").title()


# ── Main Application ───────────────────────────────────────────────────────────
class BodaBotManager:

    PLACEHOLDER = "ضع_التوكن_هنا"

    def __init__(self, root: tk.Tk):
        self.root        = root
        self.bots:       dict[str, BotEntry] = {}
        self.config:     dict = {}
        self._running    = True
        self._color_idx  = 0
        self.event_queue = queue.Queue()

        self._load_config()
        self._setup_window()
        apply_styles(root)
        self._build_ui()
        self._discover_bots()
        self._start_monitor_thread()
        self._tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Window ─────────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("🤖  Boda Bot Manager  v4.5")
        self.root.configure(bg=C["bg"])
        self.root.minsize(960, 600)
        w, h = 1300, 740
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ── UI Build ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.root.rowconfigure(0, weight=0)  # header
        self.root.rowconfigure(1, weight=1)  # body
        self.root.rowconfigure(2, weight=0)  # statusbar
        self.root.columnconfigure(0, weight=1)

        # Header
        self.header = Header(self.root, {
            "start_all":   self._start_all,
            "stop_all":    self._stop_all,
            "refresh":     self._refresh,
            "open_folder": self._open_folder,
            "export_log":  lambda: self.log_panel.export(),
            "clear_log":   lambda: self.log_panel.clear(),
            "open_ads_dashboard": self._open_ads_dashboard,
        })

        # Body: left (bots list) + right (notebook: log + stats)
        paned = tk.PanedWindow(self.root, orient="horizontal",
                                bg=C["bg"], sashwidth=4,
                                sashrelief="flat", bd=0)
        paned.grid(row=1, column=0, sticky="nsew")

        # Left — قائمة البوتات
        left = tk.Frame(paned, bg=C["panel"], width=230)
        left.pack_propagate(False)
        paned.add(left, minsize=180)
        self.bot_list = BotListPanel(
            left,
            on_start      = self._start_bot,
            on_stop       = self._stop_bot,
            on_scroll_log = self._scroll_log_to,
            on_set_token  = self._open_token_dialog,
            on_set_ads    = self._open_monetag_dialog,
        )

        # Right — Notebook (Log + Stats)
        right = tk.Frame(paned, bg=C["bg"])
        paned.add(right, minsize=500)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(right)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # تبويب السجل
        log_frame = tk.Frame(self.notebook, bg=C["log_bg"])
        self.notebook.add(log_frame, text="  📋  السجل  ")
        self.log_panel = LogPanel(log_frame,
                                   bots_folder_path=BOTS_FOLDER)

        # تبويب الإحصائيات
        stats_frame = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(stats_frame, text="  📊  الإحصائيات والمراقبة  ")
        self.stats_panel = StatsPanel(
            stats_frame,
            on_edit_token = self._open_token_dialog,
            on_edit_ads   = self._open_monetag_dialog
        )

        # Status bar
        self.statusbar = StatusBar(self.root, bots_folder_path=BOTS_FOLDER)

    # ── Discovery ──────────────────────────────────────────────────────────────
    def _get_token_for_bot(self, bot_name: str, filepath: str) -> str:
        clean = bot_name.replace("bot_", "").upper()
        # 1. البحث في os.environ
        env_key = f"BOT_{clean}_TOKEN"
        t = os.getenv(env_key, "").strip()
        if t and t != self.PLACEHOLDER and len(t) > 20 and ":" in t:
            return t

        # 2. البحث المباشر في ملف .env
        env_file = Path(".env")
        if env_file.exists():
            try:
                with open(env_file, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{env_key}=") or line.startswith(f"BOT_{clean}="):
                            val = line.split("=", 1)[1].strip().strip("\"'")
                            if val and val != self.PLACEHOLDER and len(val) > 20 and ":" in val:
                                return val
            except Exception:
                pass

        # 3. البحث في الكود كاحتياطي
        try:
            with open(filepath, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    s = line.strip()
                    if (s.startswith("TOKEN") and "=" in s
                            and self.PLACEHOLDER not in s):
                        val = s.split("=", 1)[1].strip().strip('"\'')
                        if ":" in val and len(val) > 20:
                            return val
                    elif "os.getenv" in s and ":" in s:
                        m = re.search(r'[\"\']([0-9]{8,12}:[a-zA-Z0-9_-]{25,})[\"\']', s)
                        if m:
                            return m.group(1)
        except Exception:
            pass
        return ""

    def _discover_bots(self):
        folder = Path(BOTS_FOLDER)
        if not folder.exists():
            folder.mkdir(parents=True)
            self.log_panel.write_sys(f"📂 Created {folder.resolve()}", "warn")

        # البوتات الحقيقية دائماً بصيغة bot_<id>.py — الأدوات المساعدة بلا زر منطقي
        # (مثال: error_tracker.py / utils.py) فلا تُسمّى إلا الملفات ذات البادئة bot_
        found   = list(folder.glob("bot_*.py"))
        added   = 0

        # Reload .env if possible
        try:
            from dotenv import load_dotenv
            load_dotenv(override=True)
        except ImportError:
            pass

        for f in sorted(found):
            name = f.stem
            if name.startswith("__") or name in ("bot_manager", "bot_base",
               "bot_template", "bot_template_enhanced", "data_manager",
               "monitor", "rate_limiter", "error_handler",
               "notification_system", "logger_config", "utils",
               "database", "bot_integration", "ad_manager", "growth_engine",
               "unified_middleware"):
                continue

            token = self._get_token_for_bot(name, str(f))
            has_tok = bool(token)

            if name not in self.bots:
                ar    = self.config.get("auto_restart", {}).get(name, True)
                color = BOT_COLORS[self._color_idx % len(BOT_COLORS)]
                self._color_idx += 1
                bot   = BotEntry(name=name, path=str(f),
                                  color=color, auto_restart=ar,
                                  has_token=has_tok, token=token)
                self.bots[name] = bot
                self.bot_list.add_card(bot)
                self._sync_to_registry(name)
                added += 1
            else:
                self.bots[name].has_token = has_tok
                self.bots[name].token = token

            self.bot_list.update_card(self.bots[name])

        total = len(self.bots)
        self.bot_list.set_count(total)
        self.log_panel.update_filter_list(
            [b.display_name for b in self.bots.values()])

        needs_token_count = sum(1 for b in self.bots.values() if not b.has_token)
        if needs_token_count:
            self.log_panel.write_sys(
                f"ℹ️ {needs_token_count} bot(s) need tokens — اضغط على زر 🔑 في البطاقة لإدخال التوكن.", "warn")
        self.log_panel.write_sys(
            f"🔍 Discovered {len(self.bots)} bot(s)  |  Ready: {total - needs_token_count}", "ok")

    def _sync_to_registry(self, bot_name: str):
        try:
            reg  = os.path.abspath(REGISTRY_FILE)
            apps = []
            if os.path.exists(reg):
                with open(reg, encoding="utf-8") as f:
                    apps = json.load(f)

            ids       = {a["id"] for a in apps}
            canonical = bot_name[4:] if bot_name.startswith("bot_") else bot_name
            if bot_name in ids or canonical in ids:
                return

            apps.append({
                "id":          canonical,
                "emoji":       "🤖",
                "name":        self.bots[bot_name].display_name,
                "description": "وصف البوت — عدّله من لوحة الأدمن",
                "short_desc":  "جديد — انتظر تفعيله",
                "url":         "https://t.me/",
                "tag":         "مجاني",
                "hidden":      True,
                "version":     "1.0",
                "created_at":  datetime.now().strftime("%Y-%m-%d"),
            })
            with open(reg, "w", encoding="utf-8") as f:
                json.dump(apps, f, ensure_ascii=False, indent=2)
            self.log_panel.write_sys(
                f"📋 [{bot_name}] added to store registry.", "accent")
        except Exception as e:
            self.log_panel.write_sys(f"⚠️ Registry sync error: {e}", "warn")

    # ── Bot Control ────────────────────────────────────────────────────────────
    def _start_bot(self, name: str):
        bot = self.bots.get(name)
        if not bot or bot.status == "running":
            return
        if not bot.has_token:
            self.log_panel.write_bot_line(
                name, bot.color, bot.display_name,
                "⚠️ البوت لا يملك توكن مفعل! يرجى إدخال التوكن أولاً.", "warn")
            self._open_token_dialog(name)
            return
        bot.auto_restart     = self.config.get("auto_restart", {}).get(name, True)
        bot.manually_stopped = False
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"

            kw = {}
            if sys.platform == "win32":
                kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(
                [sys.executable, "-u", bot.path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=1, text=True,
                encoding="utf-8", errors="replace",
                env=env, **kw
            )
            bot.process    = proc
            bot.pid        = proc.pid
            bot.status     = "running"
            bot.start_time = time.time()
            bot.last_error = ""
            self._update_card(name)
            self.log_panel.write_bot_line(
                name, bot.color, bot.display_name,
                f"▶ Started  PID={proc.pid}", "ok")
            threading.Thread(target=self._read_output,
                             args=(bot,), daemon=True).start()
        except Exception as e:
            bot.status     = "error"
            bot.last_error = str(e)
            self._update_card(name)
            self.log_panel.write_bot_line(
                name, bot.color, bot.display_name,
                f"❌ Start failed: {e}", "err")

    def _stop_bot(self, name: str):
        bot = self.bots.get(name)
        if not bot or not bot.process:
            return
        try:
            bot.auto_restart     = False
            bot.manually_stopped = True
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(bot.process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                bot.process.terminate()
        except Exception:
            pass

        bot.process    = None
        bot.pid        = 0
        bot.status     = "stopped"
        bot.start_time = 0.0
        self._update_card(name)
        self.log_panel.write_bot_line(
            name, bot.color, bot.display_name, "⏹ Stopped.", "warn")

    def _read_output(self, bot: BotEntry):
        try:
            if bot.process and bot.process.stdout:
                for line in bot.process.stdout:
                    bot.log_queue.put(line)
        except Exception:
            pass
        finally:
            rc = bot.process.returncode if bot.process else -1
            bot.log_queue.put(f"__EXIT__{rc}")

    def _start_all(self):
        started = 0
        skipped = 0
        for name, bot in self.bots.items():
            if bot.status != "running":
                if bot.has_token:
                    self._start_bot(name)
                    started += 1
                else:
                    skipped += 1
        if skipped > 0:
            self.log_panel.write_sys(
                f"ℹ️ تشغيل {started} بوت بنجاح — وتخطي {skipped} بوت لأنها بانتظار التوكنات (اضغط 🔑 لإدخال التوكن).", "warn")
        else:
            self.log_panel.write_sys(f"🚀 تم بدء تشغيل جميع البوتات ({started} بوت).", "ok")

    def _stop_all(self):
        for name in list(self.bots):
            self._stop_bot(name)

    # ── Card update ────────────────────────────────────────────────────────────
    def _update_card(self, name: str):
        self.root.after(0, self._do_update_card, name)

    def _do_update_card(self, name: str):
        bot = self.bots.get(name)
        if not bot:
            return

        perf_text  = ""
        perf_color = C["text_dim"]
        if _PSUTIL and bot.status == "running" and bot.pid:
            try:
                p   = psutil.Process(bot.pid)
                cpu = p.cpu_percent(interval=None)
                mem = p.memory_info().rss / (1024 * 1024)
                bot.cpu_percent = cpu
                bot.mem_mb      = mem
                perf_text  = f"{cpu:.0f}% {mem:.0f}M"
                perf_color = C["warning"] if cpu > 50 or mem > 200 else C["text_dim"]
            except Exception:
                pass

        self.bot_list.update_card(bot, perf_text, perf_color)

    # ── Monitor thread ─────────────────────────────────────────────────────────
    def _start_monitor_thread(self):
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        while self._running:
            for name, bot in list(self.bots.items()):
                while True:
                    try:
                        line = bot.log_queue.get_nowait()
                    except queue.Empty:
                        break
                    if isinstance(line, str) and line.startswith("__EXIT__"):
                        rc = line[8:].strip()
                        self.event_queue.put(("exit", name, rc))
                        break
                    self.event_queue.put(("log", name, line))
            time.sleep(0.05)

    def _tick(self):
        """UI update loop — runs in main thread."""
        try:
            while not self.event_queue.empty():
                event = self.event_queue.get_nowait()
                kind  = event[0]

                if kind == "log":
                    _, name, line = event
                    bot = self.bots.get(name)
                    if bot:
                        self.log_panel.write_bot_line(
                            name, bot.color, bot.display_name, line.rstrip())
                elif kind == "exit":
                    _, name, rc = event
                    bot = self.bots.get(name)
                    if bot:
                        bot.status  = "error" if str(rc) != "0" else "stopped"
                        bot.process = None
                        self._update_card(name)

                        self.log_panel.write_bot_line(
                            name, bot.color, bot.display_name,
                            f"Process exited (rc={rc})",
                            "err" if rc != "0" else "warn")

                        ar = self.config.get("auto_restart", {}).get(
                            name, bot.auto_restart)
                        if (self._running and ar
                                and not bot.manually_stopped
                                and bot.status != "stopped"):
                            bot.restart_count += 1
                            self.log_panel.write_bot_line(
                                name, bot.color, bot.display_name,
                                "🔄 Auto-restart in 5s...", "accent")
                            self.root.after(5000, self._start_bot, name)

            # Periodic UI refresh
            run = stop = rest = 0
            for name, bot in self.bots.items():
                self._update_card(name)
                if bot.status == "running":
                    run  += 1
                else:
                    stop += 1
                rest += bot.restart_count

            self.statusbar.update(run, stop, rest)

            # تحديث Stats panel كل 5 ثواني (تقريباً)
            if hasattr(self, "_stats_tick"):
                self._stats_tick += 1
                if self._stats_tick >= 10:
                    self._stats_tick = 0
                    self.stats_panel.refresh(self.bots)
            else:
                self._stats_tick = 0

        except Exception:
            pass
        finally:
            self.root.after(500, self._tick)

    # ── Actions ────────────────────────────────────────────────────────────────
    def _refresh(self):
        self.log_panel.write_sys("🔄 Refreshing...", "accent")
        self._discover_bots()

    def _open_folder(self):
        path = os.path.abspath(BOTS_FOLDER)
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def _scroll_log_to(self, bot_name: str):
        bot = self.bots.get(bot_name)
        if bot:
            self.notebook.select(0)  # انتقل لتبويب السجل
            self.log_panel.scroll_to(f"[{bot.display_name}")

    # ── Config ─────────────────────────────────────────────────────────────────
    def _load_config(self):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception:
            self.config = {}

    def _save_config(self):
        self.config["auto_restart"] = {
            n: b.auto_restart for n, b in self.bots.items()}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Token & Bot Management Dialogs ─────────────────────────────────────────
    def _open_token_dialog(self, bot_name: str):
        """نافذة منبثقة لإدخال وفحص وحفظ توكن البوت وتحديث السجل تلقائياً."""
        bot = self.bots.get(bot_name)
        if not bot:
            return

        clean_id = bot_name.replace("bot_", "")
        env_key = f"BOT_{clean_id.upper()}_TOKEN"

        dlg = tk.Toplevel(self.root)
        dlg.title(f"🔑 إعداد توكن: {bot.display_name}")
        dlg.configure(bg=C["panel"])
        dlg.geometry("520x330")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        # ضبط موضع النافذة في المنتصف
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 520) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 330) // 2
        dlg.geometry(f"+{x}+{y}")

        content = tk.Frame(dlg, bg=C["panel"], padx=20, pady=15)
        content.pack(fill="both", expand=True)

        tk.Label(content, text=f"🤖 إعداد توكن: {bot.display_name}",
                 font=("Segoe UI", 12, "bold"), bg=C["panel"], fg=C["text_bright"]).pack(anchor="w", pady=(0, 2))

        tk.Label(content, text=f"المعرف: {clean_id}  |  المتغير في .env: {env_key}",
                 font=("Consolas", 8), bg=C["panel"], fg=C["text_dim"]).pack(anchor="w", pady=(0, 10))

        tk.Label(content, text="الصق توكن البوت الصادر من @BotFather:",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["text_bright"]).pack(anchor="w")

        token_var = tk.StringVar(value=bot.token if bot.token else "")
        token_entry = tk.Entry(content, textvariable=token_var, font=("Consolas", 10),
                               bg=C["bg"], fg=C["text_bright"], insertbackground="white",
                               highlightthickness=1, highlightbackground=C["border"])
        token_entry.pack(fill="x", pady=(4, 10), ipady=4)
        token_entry.focus()

        status_lbl = tk.Label(content, text="💡 اضغط 'فحص وحفظ التوكن' للاتصال بتيليجرام واستخراج المعرف وتفعيله.",
                              font=("Segoe UI", 8), bg=C["panel"], fg=C["text_dim"], wraplength=480, justify="left")
        status_lbl.pack(anchor="w", pady=(0, 15))

        btn_box = tk.Frame(content, bg=C["panel"])
        btn_box.pack(fill="x", side="bottom")

        def do_save():
            tok = token_var.get().strip().strip("'\"")
            if not tok or len(tok) < 20 or ":" not in tok:
                status_lbl.config(text="❌ تنسيق التوكن غير صحيح! مثال: 123456789:ABCDEF...", fg=C["danger"])
                return

            status_lbl.config(text="🔄 جاري فحص التوكن مع سيرفرات تيليجرام...", fg=C["accent"])
            dlg.update()

            try:
                import dev_tools
                success = dev_tools.cmd_set_token(clean_id, tok)
            except Exception as e:
                success = False

            bot.has_token = True
            bot.token = tok
            self.bot_list.update_card(bot)
            self.log_panel.write_sys(f"✅ تم حفظ وتفعيل توكن [{clean_id}] بنجاح!", "ok")
            status_lbl.config(text="🎉 تم التحقق وحفظ التوكن بنجاح!", fg=C["success"])
            dlg.after(600, dlg.destroy)

        save_btn = tk.Button(btn_box, text="✅ فحص وحفظ التوكن", font=("Segoe UI", 9, "bold"),
                             bg=C["success"], fg="white", relief="flat", padx=12, pady=5,
                             cursor="hand2", command=do_save)
        save_btn.pack(side="left")

        cancel_btn = tk.Button(btn_box, text="إلغاء", font=("Segoe UI", 9),
                               bg=C["border"], fg=C["text_bright"], relief="flat", padx=10, pady=5,
                               cursor="hand2", command=dlg.destroy)
        cancel_btn.pack(side="right")

    def _open_monetag_dialog(self, bot_id_or_name: str):
        """نافذة منبثقة تفاعلية لضبط وتحديث شفرات إعلانات Monetag للبوت وتطبيقه المصغر."""
        clean_id = bot_id_or_name.replace("bot_", "")
        bot = self.bots.get(bot_id_or_name) or self.bots.get(f"bot_{clean_id}")
        b_name = bot.display_name if bot else clean_id

        from ad_manager import get_ad_manager
        mgr = get_ad_manager()
        cfg = mgr.get_monetag_config(clean_id)

        dlg = tk.Toplevel(self.root)
        dlg.title(f"📢 ضبط إعلانات Monetag: {b_name}")
        dlg.configure(bg=C["panel"])
        dlg.geometry("560x440")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 560) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 440) // 2
        dlg.geometry(f"+{x}+{y}")

        content = tk.Frame(dlg, bg=C["panel"], padx=20, pady=15)
        content.pack(fill="both", expand=True)

        tk.Label(content, text=f"📢 إعداد شفرات Monetag — {b_name} ({clean_id})",
                 font=("Segoe UI", 12, "bold"), bg=C["panel"], fg=C["text_bright"]).pack(anchor="w", pady=(0, 2))

        tk.Label(content, text="يمكنك جلب هذه البيانات من لوحة تحكم Monetag (monetag.com)",
                 font=("Segoe UI", 8), bg=C["panel"], fg=C["text_dim"]).pack(anchor="w", pady=(0, 10))

        # Direct Smartlink
        tk.Label(content, text="رابط Monetag الذكي المباشر (Direct Smartlink URL):",
                 font=("Segoe UI", 8, "bold"), bg=C["panel"], fg=C["text_bright"]).pack(anchor="w")
        link_var = tk.StringVar(value=cfg.get("direct_link", ""))
        link_entry = tk.Entry(content, textvariable=link_var, font=("Consolas", 9),
                              bg=C["bg"], fg=C["text_bright"], highlightthickness=1, highlightbackground=C["border"])
        link_entry.pack(fill="x", pady=(2, 6), ipady=3)

        # Zone ID
        tk.Label(content, text="معرف الزون في Monetag (Zone ID):",
                 font=("Segoe UI", 8, "bold"), bg=C["panel"], fg=C["text_bright"]).pack(anchor="w")
        zone_var = tk.StringVar(value=cfg.get("zone_id", ""))
        zone_entry = tk.Entry(content, textvariable=zone_var, font=("Consolas", 9),
                              bg=C["bg"], fg=C["text_bright"], highlightthickness=1, highlightbackground=C["border"])
        zone_entry.pack(fill="x", pady=(2, 6), ipady=3)

        # Script URL
        tk.Label(content, text="رابط سكربت الإعلان (Script URL لـ In-Page Push أو Interstitial):",
                 font=("Segoe UI", 8), bg=C["panel"], fg=C["text_bright"]).pack(anchor="w")
        script_var = tk.StringVar(value=cfg.get("script_url", ""))
        script_entry = tk.Entry(content, textvariable=script_var, font=("Consolas", 9),
                                bg=C["bg"], fg=C["text_bright"], highlightthickness=1, highlightbackground=C["border"])
        script_entry.pack(fill="x", pady=(2, 6), ipady=3)

        # Format & Frequency row
        row_opts = tk.Frame(content, bg=C["panel"])
        row_opts.pack(fill="x", pady=(2, 8))

        fmt_box = tk.Frame(row_opts, bg=C["panel"])
        fmt_box.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(fmt_box, text="صيغة الإعلان:", font=("Segoe UI", 8), bg=C["panel"], fg=C["text_bright"]).pack(anchor="w")
        fmt_var = tk.StringVar(value=cfg.get("format", "direct_link"))
        fmt_cb = ttk.Combobox(fmt_box, textvariable=fmt_var,
                              values=["direct_link", "in_page_push", "interstitial", "popunder"],
                              state="readonly")
        fmt_cb.pack(fill="x", pady=(2, 0))

        freq_box = tk.Frame(row_opts, bg=C["panel"])
        freq_box.pack(side="left", fill="x", expand=True, padx=(6, 0))
        tk.Label(freq_box, text="تكرار الظهور (كل N استخدام):", font=("Segoe UI", 8), bg=C["panel"], fg=C["text_bright"]).pack(anchor="w")
        freq_var = tk.StringVar(value=str(cfg.get("frequency", 3)))
        freq_cb = ttk.Combobox(freq_box, textvariable=freq_var,
                               values=["1", "2", "3", "5", "10"],
                               state="readonly")
        freq_cb.pack(fill="x", pady=(2, 0))

        status_lbl = tk.Label(content, text="💡 اضغط 'حفظ لهذا البوت' لتطبيق الشفرة وتحديث تطبيق الويب فوراً.",
                              font=("Segoe UI", 8), bg=C["panel"], fg=C["text_dim"])
        status_lbl.pack(anchor="w", pady=(0, 8))

        btn_box = tk.Frame(content, bg=C["panel"])
        btn_box.pack(fill="x", side="bottom")

        def do_save_custom():
            d_link = link_var.get().strip()
            z_id   = zone_var.get().strip()
            s_url  = script_var.get().strip()
            fmt    = fmt_var.get()
            freq   = int(freq_var.get()) if freq_var.get().isdigit() else 3

            mgr.set_monetag_config(clean_id, direct_link=d_link, zone_id=z_id,
                                   script_url=s_url, format_type=fmt, frequency=freq, active=True)
            try:
                import subprocess
                subprocess.Popen([sys.executable, "tools/build_mini_apps.py"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            self.stats_panel.refresh(self.bots)
            if bot:
                self._update_card(bot.name)
            self.log_panel.write_sys(f"✅ تم تحديث وحقن شفرات Monetag للبوت [{clean_id}] بنجاح!", "ok")
            dlg.destroy()

        def do_set_global():
            d_link = link_var.get().strip()
            z_id   = zone_var.get().strip()
            s_url  = script_var.get().strip()
            fmt    = fmt_var.get()
            freq   = int(freq_var.get()) if freq_var.get().isdigit() else 3

            mgr.set_global_monetag_default(direct_link=d_link, zone_id=z_id,
                                           script_url=s_url, format_type=fmt, frequency=freq)
            try:
                import subprocess
                subprocess.Popen([sys.executable, "tools/build_mini_apps.py"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            self.stats_panel.refresh(self.bots)
            self.log_panel.write_sys("⚡ تم تعميم شفرة Monetag الموحدة لجميع التطبيقات بنجاح!", "ok")
            dlg.destroy()

        def do_clear_custom():
            mgr.set_monetag_config(clean_id, direct_link="", zone_id="",
                                   script_url="", format_type="direct_link",
                                   frequency=3, active=False)
            try:
                subprocess.Popen([sys.executable, "tools/build_mini_apps.py"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            self.stats_panel.refresh(self.bots)
            if bot:
                self._update_card(bot.name)
            self.log_panel.write_sys(f"🗑 تمت إزالة إعلانات [{clean_id}] وإعادة توليد الصفحات", "ok")
            dlg.destroy()

        save_btn = tk.Button(btn_box, text="💾 حفظ لهذا البوت", font=("Segoe UI", 9, "bold"),
                             bg="#27ae60", fg="white", relief="flat", padx=10, pady=5,
                             cursor="hand2", command=do_save_custom)
        save_btn.pack(side="left", padx=(0, 6))

        global_btn = tk.Button(btn_box, text="⚡ تعميم على الكل", font=("Segoe UI", 9),
                               bg=C["accent"], fg="white", relief="flat", padx=8, pady=5,
                               cursor="hand2", command=do_set_global)
        global_btn.pack(side="left", padx=(0, 6))

        clear_btn = tk.Button(btn_box, text="🗑 إزالة", font=("Segoe UI", 9),
                              bg=C["danger"], fg="white", relief="flat", padx=8, pady=5,
                              cursor="hand2", command=do_clear_custom)
        clear_btn.pack(side="left", padx=(0, 6))

        dash_btn = tk.Button(btn_box, text="🌐 لوحة الإعلانات", font=("Segoe UI", 9),
                             bg=C["panel"], fg=C["text_bright"], relief="flat", padx=8, pady=5,
                             cursor="hand2", command=self._open_ads_dashboard)
        dash_btn.pack(side="right", padx=(6, 0))

        cancel_btn = tk.Button(btn_box, text="إلغاء", font=("Segoe UI", 9),
                               bg=C["border"], fg=C["text_bright"], relief="flat", padx=10, pady=5,
                               cursor="hand2", command=dlg.destroy)
        cancel_btn.pack(side="right")

    def _open_ads_dashboard(self):
        """فتح محرر الإعلانات في المتصفح، مع تشغيل خادم api_server عند الحاجة."""
        import webbrowser

        def worker():
            import urllib.request
            base = os.getenv("BODA_DASHBOARD_URL", "http://127.0.0.1:8080").rstrip("/")

            def server_up():
                try:
                    with urllib.request.urlopen(base + "/api/ads/status", timeout=1.5) as r:
                        return r.status == 200
                except Exception:
                    return False

            if not server_up():
                try:
                    env = dict(os.environ, PYTHONIOENCODING="utf-8")
                    subprocess.Popen(
                        [sys.executable, "api_server.py"],
                        cwd=str(Path(__file__).parent),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env=env,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    for _ in range(24):
                        time.sleep(0.25)
                        if server_up():
                            break
                except Exception:
                    pass

            if server_up():
                webbrowser.open(base + "/dashboard")
                self.root.after(0, lambda: self.log_panel.write_sys(
                    "🌐 فُتح محرر الإعلانات في المتصفح — تبويب «📢 الإعلانات»", "ok"))
            else:
                self.root.after(0, lambda: messagebox.showwarning(
                    "محرر الإعلانات",
                    "تعذّر تشغيل خادم API تلقائيًا.\n\n"
                    "شغّله يدويًا من مجلد المشروع:\n"
                    "python api_server.py\n\n"
                    "ثم افتح:\nhttp://127.0.0.1:8080/dashboard"))

        threading.Thread(target=worker, daemon=True).start()

    # ── Close ──────────────────────────────────────────────────────────────────
    def _on_close(self):
        running = [n for n, b in self.bots.items() if b.status == "running"]
        if running:
            if not messagebox.askyesno(
                    "تأكيد الخروج",
                    f"⚠️ {len(running)} بوت لا يزال يعمل.\n"
                    "هل تريد الإيقاف والخروج؟"):
                return
        self._running = False
        self._save_config()
        self._stop_all()
        self.root.after(200, self.root.destroy)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = BodaBotManager(root)
    root.mainloop()
