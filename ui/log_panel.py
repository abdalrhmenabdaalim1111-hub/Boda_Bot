# =============================================================================
#  ui/log_panel.py — لوحة السجل الموحد (الجانب الأيمن)
# =============================================================================
import os
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime
from ui.theme import C


class LogPanel:
    """
    اللوحة اليمنى: سجل موحد لجميع البوتات مع:
    - فلتر حسب البوت
    - Auto-scroll toggle
    - قائمة سياق (copy, clear)
    - تصدير السجل
    """

    def __init__(self, parent, bots_folder_path: str = ""):
        self._bots_folder = bots_folder_path
        self._sys_callback = None  # يُعيَّن من الخارج إذا لزم

        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        self._build_toolbar(parent)
        self._build_log_area(parent)
        self._write_banner()

    # ── Toolbar ───────────────────────────────────────────────────────────────
    def _build_toolbar(self, parent):
        toolbar = tk.Frame(parent, bg=C["panel"])
        toolbar.grid(row=0, column=0, sticky="ew")

        tk.Label(toolbar, text="  📋  SYSTEM LOG",
                 font=("Segoe UI", 9, "bold"),
                 bg=C["panel"], fg=C["text_dim"]).pack(side="left", pady=6)

        # Auto-scroll
        self._autoscroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(toolbar,
                       text="Auto-scroll",
                       variable=self._autoscroll_var,
                       bg=C["panel"], fg=C["text_dim"],
                       activebackground=C["panel"],
                       selectcolor=C["card"],
                       font=("Segoe UI", 8),
                       cursor="hand2").pack(side="right", padx=8)

        tk.Label(toolbar, text="|", bg=C["panel"],
                 fg=C["border"]).pack(side="right")

        # Filter
        tk.Label(toolbar, text="Filter:",
                 font=("Segoe UI", 8),
                 bg=C["panel"], fg=C["text_dim"]).pack(side="right", padx=(0, 2))

        self._filter_var = tk.StringVar(value="ALL")
        self._filter_menu = ttk.Combobox(toolbar,
                                          textvariable=self._filter_var,
                                          values=["ALL"],
                                          width=14,
                                          state="readonly",
                                          font=("Segoe UI", 8))
        self._filter_menu.pack(side="right", padx=4)

        tk.Frame(parent, bg=C["border"], height=1).grid(
            row=0, column=0, sticky="sew")

    # ── منطقة النص ────────────────────────────────────────────────────────────
    def _build_log_area(self, parent):
        log_frame = tk.Frame(parent, bg=C["log_bg"])
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.text = tk.Text(log_frame,
                            bg=C["log_bg"], fg=C["log_fg"],
                            font=("Consolas", 9),
                            wrap="word", state="disabled",
                            bd=0, relief="flat",
                            insertbackground=C["text"],
                            selectbackground=C["accent2"],
                            padx=12, pady=8)
        vsb = ttk.Scrollbar(log_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Color tags
        self.text.tag_config("sys",    foreground=C["log_sys"])
        self.text.tag_config("ok",     foreground=C["log_ok"])
        self.text.tag_config("err",    foreground=C["log_err"])
        self.text.tag_config("warn",   foreground=C["log_warn"])
        self.text.tag_config("accent", foreground=C["log_accent"])
        self.text.tag_config("time",   foreground=C["text_dim"])
        self.text.tag_config("sep",    foreground=C["border"])

        # Context menu
        ctx = tk.Menu(self.text, tearoff=0,
                      bg=C["panel"], fg=C["text"],
                      activebackground=C["accent"],
                      activeforeground="white")
        ctx.add_command(label="📋  Copy Selection", command=self._copy_sel)
        ctx.add_command(label="📄  Copy All",       command=self._copy_all)
        ctx.add_separator()
        ctx.add_command(label="🗑  Clear Log",      command=self.clear)
        self.text.bind("<Button-3>",
                       lambda e: ctx.post(e.x_root, e.y_root))
        self.text.bind("<Key>", lambda e: "break")

    # ── كتابة في السجل ────────────────────────────────────────────────────────
    def append(self, text: str, tag: str = "sys"):
        """إضافة نص مباشرة بوسم معين."""
        self.text.configure(state="normal")
        self.text.insert("end", text, tag)
        self.text.configure(state="disabled")
        if self._autoscroll_var.get():
            self.text.see("end")

    def write_bot_line(self, bot_name: str, bot_color: str,
                       display_name: str, text: str, tag: str = None):
        """
        كتابة سطر منسّق للسجل الموحد.

        Args:
            bot_name:    اسم البوت الداخلي
            bot_color:   لون البوت الفريد
            display_name: اسم العرض (للفلتر)
            text:        نص السطر
            tag:         وسم اللون (يُكتشف تلقائياً إذا None)
        """
        # إعداد وسم لون البوت
        color_tag = f"bot_{bot_name}"
        if color_tag not in self.text.tag_names():
            self.text.tag_config(color_tag, foreground=bot_color)

        # الكشف التلقائي عن التصنيف
        if tag is None:
            tl = text.lower()
            if any(k in tl for k in ("error", "exception", "traceback", "❌", "failed")):
                tag = "err"
            elif any(k in tl for k in ("warning", "warn", "⚠️")):
                tag = "warn"
            elif any(k in tl for k in ("started", "running", "polling", "✅", "ok", "success")):
                tag = "ok"
            else:
                tag = "sys"

        # فحص الفلتر
        filt = self._filter_var.get()
        if filt != "ALL" and filt != display_name:
            return

        ts     = datetime.now().strftime("%H:%M:%S")
        head   = f"[{ts}] "
        prefix = f"[{display_name:12s}] "
        line   = text.rstrip() + "\n"

        self.text.configure(state="normal")
        self.text.insert("end", head,   "time")
        self.text.insert("end", prefix, color_tag)
        self.text.insert("end", line,   tag)
        self.text.configure(state="disabled")
        if self._autoscroll_var.get():
            self.text.see("end")

    def write_sys(self, text: str, tag: str = "sys"):
        """كتابة رسالة نظام."""
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] [{'System':12s}] {text}\n"
        self.append(line, tag)

    # ── Banner ────────────────────────────────────────────────────────────────
    def _write_banner(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            ("═" * 62,                                              "sep"),
            (f"  🤖  Boda Bot Manager v4.1  |  Telegram Edition",  "accent"),
            (f"  📂  {os.path.abspath(self._bots_folder)}",        "sys"),
            (f"  🕐  {ts}",                                        "sys"),
            ("═" * 62,                                              "sep"),
        ]
        for text, t in lines:
            self.append(text + "\n", t)

    # ── أدوات ─────────────────────────────────────────────────────────────────
    def scroll_to(self, search_tag: str):
        """تمرير السجل إلى آخر إدخال يحتوي على الوسم."""
        try:
            idx = self.text.search(
                search_tag, "end", backwards=True, stopindex="1.0")
            if idx:
                self.text.see(idx)
                line_end = f"{idx.split('.')[0]}.end"
                self.text.tag_add("_flash", idx, line_end)
                self.text.tag_config("_flash", background=C["accent2"])
                self.text.after(600, lambda: self.text.tag_delete("_flash"))
        except Exception:
            pass

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._write_banner()

    def export(self):
        """حفظ السجل إلى ملف نصي."""
        text = self.text.get("1.0", "end")
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"boda_log_{ts}.txt",
            title="حفظ السجل"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.write_sys(f"✅ تم تصدير السجل: {path}", "ok")
            except Exception as e:
                self.write_sys(f"❌ خطأ في حفظ السجل: {e}", "err")

    def update_filter_list(self, bot_display_names: list):
        """تحديث قائمة الفلتر بأسماء البوتات."""
        self._filter_menu.config(values=["ALL"] + bot_display_names)

    def _copy_sel(self):
        try:
            text = self.text.get("sel.first", "sel.last")
            self.text.clipboard_clear()
            self.text.clipboard_append(text)
        except Exception:
            pass

    def _copy_all(self):
        text = self.text.get("1.0", "end")
        self.text.clipboard_clear()
        self.text.clipboard_append(text)
