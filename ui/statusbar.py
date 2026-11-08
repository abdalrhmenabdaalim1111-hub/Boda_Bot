# =============================================================================
#  ui/statusbar.py — شريط الحالة السفلي
# =============================================================================
import os
import tkinter as tk
from datetime import datetime
from ui.theme import C


class StatusBar:
    """شريط الحالة السفلي: عداد Running/Stopped/Restarts + الوقت + المسار."""

    def __init__(self, parent, bots_folder_path: str = ""):
        tk.Frame(parent, bg=C["border"], height=1).grid(
            row=2, column=0, sticky="new")

        self.frame = tk.Frame(parent, bg=C["panel"], height=26)
        self.frame.grid(row=2, column=0, sticky="ew")
        self.frame.grid_propagate(False)

        self._sb_run  = self._lbl("⚡ 0 Running",  C["success"])
        self._sep()
        self._sb_stop = self._lbl("⏹ 0 Stopped",  C["text_dim"])
        self._sep()
        self._sb_rest = self._lbl("🔄 0 Restarts", C["text_dim"])
        self._sb_time = self._lbl("", C["text_dim"], "right")
        self._sb_path = self._lbl(
            f"📁 {os.path.abspath(bots_folder_path)}",
            C["text_dim"], "right")

    def _lbl(self, text, fg, side="left"):
        l = tk.Label(self.frame, text=text, font=("Segoe UI", 8),
                     bg=C["panel"], fg=fg, padx=10)
        l.pack(side=side)
        return l

    def _sep(self):
        tk.Label(self.frame, text="|", bg=C["panel"],
                 fg=C["border"]).pack(side="left")

    def update(self, running: int, stopped: int, restarts: int):
        self._sb_run.config(
            text=f"⚡ {running} Running",
            fg=C["success"] if running else C["text_dim"])
        self._sb_stop.config(text=f"⏹ {stopped} Stopped")
        self._sb_rest.config(
            text=f"🔄 {restarts} Restarts",
            fg=C["warning"] if restarts else C["text_dim"])
        self._sb_time.config(
            text=datetime.now().strftime("%H:%M:%S  "))
