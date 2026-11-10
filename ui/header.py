# =============================================================================
#  ui/header.py — شريط العنوان الرئيسي لـ Boda Bot Manager
# =============================================================================
import tkinter as tk
from tkinter import ttk
from ui.theme import C


class Header:
    """مكوّن Header: الشعار + أزرار التحكم العامة."""

    def __init__(self, parent, callbacks: dict):
        """
        Args:
            parent:    النافذة أو الإطار الأب
            callbacks: dict يحتوي على: start_all, stop_all, refresh,
                       open_folder, export_log, clear_log
        """
        self.frame = tk.Frame(parent, bg=C["panel"], height=60)
        self.frame.grid(row=0, column=0, sticky="ew")
        self.frame.grid_propagate(False)
        self.frame.columnconfigure(1, weight=1)

        self._build_logo()
        self._build_buttons(callbacks)
        self._build_divider(parent)

    # ── شعار التطبيق ──────────────────────────────────────────────────────────
    def _build_logo(self):
        logo = tk.Frame(self.frame, bg=C["panel"])
        logo.grid(row=0, column=0, padx=16, pady=10, sticky="w")

        tk.Label(logo, text="🤖", font=("Segoe UI Emoji", 22),
                 bg=C["panel"], fg=C["text_bright"]).pack(side="left", padx=(0, 8))

        sub = tk.Frame(logo, bg=C["panel"])
        sub.pack(side="left")
        tk.Label(sub, text="Boda Bot Manager",
                 font=("Segoe UI", 14, "bold"),
                 bg=C["panel"], fg=C["text_bright"]).pack(anchor="w")
        tk.Label(sub, text="Telegram Edition  •  v4.5",
                 font=("Segoe UI", 8),
                 bg=C["panel"], fg=C["accent"]).pack(anchor="w")

    # ── أزرار التحكم ──────────────────────────────────────────────────────────
    def _build_buttons(self, callbacks):
        btns = tk.Frame(self.frame, bg=C["panel"])
        btns.grid(row=0, column=2, padx=16, pady=10, sticky="e")

        btn_defs = [
            ("▶  Start All",   "Success", callbacks.get("start_all")),
            ("⏹  Stop All",    "Danger",  callbacks.get("stop_all")),
            ("🔄  Refresh",    "Accent",  callbacks.get("refresh")),
            ("📂  Open Folder","Neutral",  callbacks.get("open_folder")),
            ("🖨  Export Log",  "Neutral",  callbacks.get("export_log")),
            ("🗑  Clear Log",  "Dark",    callbacks.get("clear_log")),
        ]

        for text, style, cmd in btn_defs:
            b = ttk.Button(btns, text=text,
                           style=f"{style}.TButton", command=cmd)
            b.pack(side="left", padx=3)

    def _build_divider(self, parent):
        tk.Frame(parent, bg=C["border"], height=1).grid(
            row=0, column=0, sticky="sew")
