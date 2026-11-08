# =============================================================================
#  ui/theme.py — نظام الألوان والأنماط المركزي لـ Boda Bot Manager
# =============================================================================

# ── Colour palette ─────────────────────────────────────────────────────────────
C = {
    "bg":          "#0d1117",
    "panel":       "#161b22",
    "card":        "#1c2128",
    "card_run":    "#0d2018",
    "border":      "#30363d",
    "accent":      "#229ed9",
    "accent2":     "#1a7bbf",
    "success":     "#3fb950",
    "warning":     "#d29922",
    "danger":      "#f85149",
    "text":        "#e6edf3",
    "text_dim":    "#8b949e",
    "text_bright": "#ffffff",
    "log_bg":      "#010409",
    "log_fg":      "#c9d1d9",
    "log_err":     "#ff7b72",
    "log_warn":    "#e3b341",
    "log_ok":      "#56d364",
    "log_tg":      "#79c0ff",
    "log_sys":     "#8b949e",
    "log_accent":  "#58a6ff",
}

# ── Bot colour tags (each bot gets unique colour in combined log) ──────────────
BOT_COLORS = [
    "#79c0ff", "#56d364", "#d2a8ff", "#ffa657",
    "#ff7b72", "#e3b341", "#58a6ff", "#3fb950",
    "#f0883e", "#bc8cff", "#39d353", "#db6d28",
]


def apply_styles(root):
    """تطبيق أنماط ttk على النافذة الرئيسية."""
    from tkinter import ttk

    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure(".", background=C["bg"], foreground=C["text"],
                font=("Segoe UI", 9), borderwidth=0)
    s.configure("TFrame",     background=C["bg"])
    s.configure("TSeparator", background=C["border"])

    for name, bg, fg, abg in [
        ("Success", C["success"],  "#000",        "#2ea043"),
        ("Danger",  C["danger"],   "#fff",        "#da3633"),
        ("Warning", C["warning"],  "#000",        "#bb8009"),
        ("Accent",  C["accent"],   "#fff",        C["accent2"]),
        ("Neutral", C["card"],     C["text"],     C["border"]),
        ("Dark",    C["panel"],    C["text_dim"], C["card"]),
    ]:
        s.configure(f"{name}.TButton",
            background=bg, foreground=fg,
            font=("Segoe UI", 9, "bold"),
            relief="flat", borderwidth=0, padding=(10, 5))
        s.map(f"{name}.TButton",
            background=[("active", abg), ("pressed", abg)],
            foreground=[("active", fg)])

    s.configure("TScrollbar",
        background=C["border"], troughcolor=C["panel"],
        borderwidth=0, arrowsize=10)

    s.configure("TNotebook",
        background=C["bg"], borderwidth=0)
    s.configure("TNotebook.Tab",
        background=C["panel"], foreground=C["text_dim"],
        font=("Segoe UI", 9), padding=(12, 6))
    s.map("TNotebook.Tab",
        background=[("selected", C["card"])],
        foreground=[("selected", C["text_bright"])])
