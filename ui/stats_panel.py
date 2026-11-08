# =============================================================================
#  ui/stats_panel.py — لوحة الإحصائيات (تبويب جديد)
# =============================================================================
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from ui.theme import C


class StatsPanel:
    """
    لوحة إحصائيات حية تعرض:
    - ملخص حالة البوتات
    - أوقات التشغيل
    - عدد إعادة التشغيل
    - بطاقات ملخص سريع
    """

    def __init__(self, parent):
        self.frame = parent
        self._bot_rows: dict[str, dict] = {}

        parent.configure(bg=C["bg"])
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        self._build_summary_cards(parent)
        self._build_table(parent)

    # ── بطاقات الملخص السريع ─────────────────────────────────────────────────
    def _build_summary_cards(self, parent):
        cards_frame = tk.Frame(parent, bg=C["bg"])
        cards_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=12)

        cards_data = [
            ("running_val",  "0", "🟢 Running",  C["success"]),
            ("stopped_val",  "0", "🔴 Stopped",  C["danger"]),
            ("restarts_val", "0", "🔄 Restarts", C["warning"]),
            ("total_val",    "0", "🤖 Total",    C["accent"]),
        ]

        for i, (attr, val, label, color) in enumerate(cards_data):
            card = tk.Frame(cards_frame, bg=C["card"],
                            highlightthickness=1,
                            highlightbackground=color)
            card.grid(row=0, column=i, padx=6, pady=0, ipadx=16, ipady=10)

            val_lbl = tk.Label(card, text=val,
                                font=("Segoe UI", 28, "bold"),
                                bg=C["card"], fg=color)
            val_lbl.pack()

            tk.Label(card, text=label,
                     font=("Segoe UI", 9),
                     bg=C["card"], fg=C["text_dim"]).pack()

            setattr(self, attr, val_lbl)

        for i in range(4):
            cards_frame.columnconfigure(i, weight=1)

    # ── جدول التفاصيل ─────────────────────────────────────────────────────────
    def _build_table(self, parent):
        # Header
        header = tk.Frame(parent, bg=C["panel"])
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(0, 0))
        # يتم بناؤه بعد الكروت — نعيد الترتيب
        # استخدام Treeview للجدول
        tree_frame = tk.Frame(parent, bg=C["bg"])
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        style = ttk.Style()
        style.configure("Stats.Treeview",
                         background=C["card"],
                         foreground=C["text"],
                         rowheight=28,
                         fieldbackground=C["card"],
                         font=("Segoe UI", 9))
        style.configure("Stats.Treeview.Heading",
                         background=C["panel"],
                         foreground=C["text_dim"],
                         font=("Segoe UI", 9, "bold"),
                         relief="flat")
        style.map("Stats.Treeview",
                  background=[("selected", C["accent2"])],
                  foreground=[("selected", "white")])

        columns = ("name", "status", "uptime", "restarts", "pid")
        self.tree = ttk.Treeview(tree_frame,
                                  columns=columns,
                                  show="headings",
                                  style="Stats.Treeview",
                                  selectmode="browse")

        col_defs = [
            ("name",     "البوت",          180),
            ("status",   "الحالة",          90),
            ("uptime",   "وقت التشغيل",    120),
            ("restarts", "إعادة التشغيل",   100),
            ("pid",      "PID",             80),
        ]
        for col_id, heading, width in col_defs:
            self.tree.heading(col_id, text=heading)
            self.tree.column(col_id, width=width, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # آخر تحديث
        self._last_update = tk.Label(parent,
                                      text="",
                                      font=("Segoe UI", 8),
                                      bg=C["bg"], fg=C["text_dim"])
        self._last_update.grid(row=2, column=0, sticky="e", padx=16, pady=(0, 8))

    # ── تحديث الإحصائيات ─────────────────────────────────────────────────────
    def refresh(self, bots: dict):
        """
        تحديث كامل للإحصائيات.
        
        Args:
            bots: dict[name -> BotEntry]
        """
        running = stopped = restarts = 0

        # مسح الجدول
        for item in self.tree.get_children():
            self.tree.delete(item)

        for name, bot in bots.items():
            if bot.status == "running":
                running += 1
                status_text = "🟢 يعمل"
                tag = "run"
            elif bot.status == "error":
                stopped += 1
                status_text = "⚠️ خطأ"
                tag = "err"
            else:
                stopped += 1
                status_text = "⚪ متوقف"
                tag = "stop"

            restarts += bot.restart_count

            self.tree.insert("", "end", values=(
                bot.display_name,
                status_text,
                bot.uptime,
                bot.restart_count or "—",
                bot.pid or "—",
            ), tags=(tag,))

        # ألوان الصفوف
        self.tree.tag_configure("run",  foreground=C["success"])
        self.tree.tag_configure("err",  foreground=C["warning"])
        self.tree.tag_configure("stop", foreground=C["text_dim"])

        # تحديث البطاقات
        self.running_val.config(text=str(running))
        self.stopped_val.config(text=str(stopped))
        self.restarts_val.config(text=str(restarts))
        self.total_val.config(text=str(len(bots)))

        self._last_update.config(
            text=f"آخر تحديث: {datetime.now().strftime('%H:%M:%S')}")
