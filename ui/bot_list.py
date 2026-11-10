# =============================================================================
#  ui/bot_list.py — لوحة قائمة البوتات (الجانب الأيسر)
# =============================================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import C


class BotListPanel:
    """
    اللوحة اليسرى: قائمة بوتات قابلة للتمرير مع بطاقات مضغوطة.
    كل بطاقة تعرض: Status dot، الاسم، Uptime، CPU/RAM، أزرار ▶ ⏹
    """

    def __init__(self, parent, on_start, on_stop, on_scroll_log, on_set_token=None, on_set_ads=None):
        """
        Args:
            parent:        الإطار الأب
            on_start:      callback(bot_name) عند الضغط على ▶
            on_stop:       callback(bot_name) عند الضغط على ⏹
            on_scroll_log: callback(bot_name) عند النقر على البطاقة
            on_set_token:  callback(bot_name) عند النقر على زر التوكن 🔑
            on_set_ads:    callback(bot_name) عند النقر على زر إعلانات Monetag 📢
        """
        self._on_start      = on_start
        self._on_stop       = on_stop
        self._on_scroll_log = on_scroll_log
        self._on_set_token  = on_set_token
        self._on_set_ads    = on_set_ads
        self.bot_widgets: dict[str, dict] = {}

        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        self._build_header(parent)
        self._build_scroll(parent)

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self, parent):
        hdr = tk.Frame(parent, bg=C["panel"])
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        tk.Label(hdr, text="BOTS", font=("Segoe UI", 8, "bold"),
                 bg=C["panel"], fg=C["text_dim"]).pack(side="left")

        self.lbl_count = tk.Label(hdr, text="0",
                                   font=("Segoe UI", 8),
                                   bg=C["panel"], fg=C["accent"])
        self.lbl_count.pack(side="right")

        tk.Frame(parent, bg=C["border"], height=1).grid(
            row=0, column=0, sticky="sew")

    # ── Scrollable canvas ─────────────────────────────────────────────────────
    def _build_scroll(self, parent):
        cf = tk.Frame(parent, bg=C["panel"])
        cf.grid(row=1, column=0, sticky="nsew")
        cf.rowconfigure(0, weight=1)
        cf.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(cf, bg=C["panel"],
                                 highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(cf, orient="vertical",
                             command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.list_frame = tk.Frame(self.canvas, bg=C["panel"])
        self._win = self.canvas.create_window(
            (0, 0), window=self.list_frame, anchor="nw")

        self.list_frame.bind("<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
            lambda e: self.canvas.itemconfig(self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>",
            lambda e: self.canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"))

    # ── إنشاء بطاقة بوت ───────────────────────────────────────────────────────
    def add_card(self, bot):
        """
        إنشاء بطاقة عرض لبوت وإضافتها للقائمة.
        
        Args:
            bot: كائن BotEntry
        """
        row = tk.Frame(self.list_frame, bg=C["panel"],
                       highlightthickness=1,
                       highlightbackground=C["border"],
                       cursor="hand2")
        row.pack(fill="x", padx=5, pady=2)

        inner = tk.Frame(row, bg=C["panel"])
        inner.pack(fill="x", padx=5, pady=4)

        # نقطة الحالة
        dot = tk.Label(inner, text="●", font=("Segoe UI", 9),
                       bg=C["panel"], fg=C["danger"])
        dot.pack(side="left")

        # اسم البوت
        name_lbl = tk.Label(inner,
                             text=bot.display_name,
                             font=("Segoe UI", 9, "bold"),
                             bg=C["panel"], fg=bot.color,
                             anchor="w", width=11)
        name_lbl.pack(side="left", padx=(3, 0))

        # Uptime
        uptime_lbl = tk.Label(inner, text="—",
                               font=("Consolas", 7),
                               bg=C["panel"], fg=C["text_dim"],
                               width=7)
        uptime_lbl.pack(side="left", padx=(3, 0))

        # CPU/RAM
        perf_lbl = tk.Label(inner, text="",
                             font=("Consolas", 7),
                             bg=C["panel"], fg=C["text_dim"],
                             width=10)
        perf_lbl.pack(side="left", padx=(2, 0))

        # عداد إعادة التشغيل
        restart_lbl = tk.Label(inner, text="",
                                font=("Segoe UI", 7),
                                bg=C["panel"], fg=C["warning"])
        restart_lbl.pack(side="left")

        # زر الإيقاف
        stop_btn = tk.Button(inner, text="⏹",
                              font=("Segoe UI Emoji", 8),
                              bg=C["danger"], fg="white",
                              relief="flat", bd=0, padx=2, pady=0,
                              cursor="hand2",
                              command=lambda n=bot.name: self._on_stop(n))
        stop_btn.pack(side="right", padx=(1, 0))

        # زر التشغيل
        start_btn = tk.Button(inner, text="▶",
                               font=("Segoe UI Emoji", 8),
                               bg=C["success"], fg="white",
                               relief="flat", bd=0, padx=2, pady=0,
                               cursor="hand2",
                               command=lambda n=bot.name: self._on_start(n))
        start_btn.pack(side="right", padx=(1, 0))

        # زر التوكن السريع 🔑
        has_token = getattr(bot, "has_token", True)
        token_btn = tk.Button(inner, text="🔑",
                               font=("Segoe UI Emoji", 8),
                               bg=C["warning"] if not has_token else C["border"],
                               fg="black" if not has_token else C["text_dim"],
                               relief="flat", bd=0, padx=3, pady=0,
                               cursor="hand2",
                               command=lambda n=bot.name: self._on_set_token(n) if self._on_set_token else None)
        token_btn.pack(side="right", padx=(1, 1))

        # زر إعلانات Monetag 📢
        ads_btn = tk.Button(inner, text="📢",
                             font=("Segoe UI Emoji", 8),
                             bg=C["border"], fg=C["text_dim"],
                             relief="flat", bd=0, padx=3, pady=0,
                             cursor="hand2",
                             command=lambda n=bot.name: self._on_set_ads(n) if self._on_set_ads else None)
        ads_btn.pack(side="right", padx=(1, 1))

        # النقر على البطاقة → الانتقال في السجل
        for w in (row, inner, name_lbl, dot, uptime_lbl):
            w.bind("<Button-1>",
                   lambda e, n=bot.name: self._on_scroll_log(n))

        self.bot_widgets[bot.name] = {
            "card":      row,
            "dot":       dot,
            "uptime":    uptime_lbl,
            "perf":      perf_lbl,
            "restart":   restart_lbl,
            "start_btn": start_btn,
            "stop_btn":  stop_btn,
            "token_btn": token_btn,
            "ads_btn":   ads_btn,
        }

    # ── تحديث حالة بطاقة ─────────────────────────────────────────────────────
    def update_card(self, bot, perf_text="", perf_color=None):
        """تحديث مظهر بطاقة البوت بناءً على حالته الحالية وحالة التوكن."""
        w = self.bot_widgets.get(bot.name)
        if not w:
            return

        pc = perf_color or C["text_dim"]
        has_token = getattr(bot, "has_token", True)

        if not has_token:
            w["dot"].config(fg=C["warning"])
            w["card"].config(highlightbackground=C["warning"])
            w["uptime"].config(text="يحتاج توكن", fg=C["warning"])
            w["token_btn"].config(bg=C["warning"], fg="black", text="🔑 توكن")
            w["start_btn"].config(state="disabled", bg=C["border"])
        else:
            w["start_btn"].config(state="normal", bg=C["success"])
            w["token_btn"].config(bg=C["border"], fg=C["text_dim"], text="🔑")
            if bot.status == "running":
                w["dot"].config(fg=C["success"])
                w["card"].config(highlightbackground=bot.color)
            elif bot.status == "error":
                w["dot"].config(fg=C["warning"])
                w["card"].config(highlightbackground=C["warning"])
            else:
                w["dot"].config(fg=C["danger"])
                w["card"].config(highlightbackground=C["border"])
            w["uptime"].config(text=bot.uptime, fg=C["text_dim"])

        w["restart"].config(
            text=f"↺{bot.restart_count}" if bot.restart_count else "")
        w["perf"].config(text=perf_text, fg=pc)

        # تحديث حالة زر Monetag 📢
        try:
            from ad_manager import get_ad_manager
            clean_id = bot.name.replace("bot_", "")
            has_custom_ad = get_ad_manager().has_custom_monetag_ad(clean_id)
            if has_custom_ad:
                w["ads_btn"].config(bg="#27ae60", fg="white")
            else:
                w["ads_btn"].config(bg=C["border"], fg=C["text_dim"])
        except Exception:
            pass

    # ── تحديث العداد ─────────────────────────────────────────────────────────
    def set_count(self, n: int):
        self.lbl_count.config(text=str(n))
