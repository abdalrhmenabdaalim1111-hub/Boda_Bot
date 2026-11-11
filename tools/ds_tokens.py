# -*- coding: utf-8 -*-
"""
tools/ds_tokens.py — Design Tokens الأساسية لنظام تصميم Boda

يُستخدم من ``app_template.py`` عند توليد كل تطبيق مصغّر. الأهداف:
  1. مصدر واحد للألوان/الخطوط/المسافات/الزوايا/الظلال/الحركة.
  2. تكيّف كامل مع ``Telegram.WebApp.themeParams`` (فاتح/داكن) مع بدائل آمنة.
  3. هوية لونية ثابتة لكل مجموعة بوتات (أدوات/وسائط/ترفيه/صحة/نصوص/متجر).
  4. أسماء توكنز جديدة ``--bd-*`` + أسماء قديمة متوافقة (``--bg``, ``--accent`` …)
     كي لا تنكسر أنماط التطبيقات الحالية في ``app_defs.py``.
"""

# ── لوحة الهوية لكل مجموعة ──────────────────────────────────────────────────
# (المفتاح، اللون الأساسي، اللون الثانوي، إيموجي المجموعة)
GROUP_THEMES = {
    "tools":  ("#3b82f6", "#22d3ee", "🛠️"),   # أدوات يومية — أزرق
    "media":  ("#8b5cf6", "#ec4899", "🎬"),   # وسائط وملفات — بنفسجي
    "fun":    ("#f97316", "#f43f5e", "🎲"),   # اختبارات وترفيه — برتقالي/وردي
    "health": ("#22c55e", "#14b8a6", "💪"),   # صحة — أخضر
    "text":   ("#14b8a6", "#38bdf8", "✍️"),   # ترجمة وكتابة — تركوازي
    "store":  ("#eab308", "#f97316", "🏪"),   # متجر — ذهبي
}

# كلمات مفتاحية عربية/إنجليزية → مجموعة
_GROUP_KEYWORDS = (
    ("health", ("صحة", "طب", "لياقة", "سعرات", "وزن", "health", "fit")),
    ("media",  ("وسائط", "تحميل", "تيك توك", "فيديو", "صور", "تصميم", "صوت",
                "كاميرا", "media", "video", "photo", "image", "tiktok", "audio")),
    ("fun",    ("ترفيه", "ألعاب", "لعبة", "اختبار", "حظ", "تسلية", "fun",
                "game", "quiz", "test", "luck")),
    ("text",   ("ترجمة", "كتابة", "مهني", "ذكاء", "نصوص", "سيرة", "translate",
                "text", "writing", "cv", "ai")),
    ("store",  ("متجر", "دليل", "store", "shop", "catalog")),
    ("tools",  ("أدوات", "إنتاجية", "أمان", "مالية", "معلومات", "طقس", "عملات",
                "tool", "utility", "security", "money", "weather", "currency")),
)


def group_key(tag: str = "", bot_id: str = "") -> str:
    """تحويل وسم البوت/معرّفه إلى مجموعة هوية معروفة."""
    haystack = f"{tag} {bot_id}".lower()
    for key, words in _GROUP_KEYWORDS:
        if any(w.lower() in haystack for w in words):
            return key
    return "tools"


def group_palette(tag: str = "", bot_id: str = "") -> dict:
    """إرجاع لوني الهوية وإيموجي المجموعة."""
    key = group_key(tag, bot_id)
    accent, accent2, emoji = GROUP_THEMES[key]
    return {"group": key, "brand": accent, "brand2": accent2, "emoji": emoji}


# ── @font-face محلي (Cairo متغيّر الوزن 400–800) ─────────────────────────────
FONT_CSS = """
@font-face{
  font-family:'Cairo';
  font-style:normal;
  font-weight:400 800;
  font-display:swap;
  src:url('../assets/fonts/cairo-arabic.woff2') format('woff2');
  unicode-range:U+0600-06FF,U+0750-077F,U+0870-0891,U+0897-08E1,U+08E3-08FF,
    U+200C-200E,U+2010-2011,U+204F,U+2E41,U+FB50-FDFF,U+FE70-FE74,
    U+FE76-FEFC,U+102E0-102FB,U+10E60-10E7E,U+10EC2-10EC7,U+10EC9-10EEE,
    U+10EF0-10EFF,U+1EE00-1EE03,U+1EE05-1EE1F,U+1EE21-1EE22,U+1EE24,
    U+1EE27,U+1EE29-1EE32,U+1EE34-1EE37,U+1EE39,U+1EE3B,U+1EE42,U+1EE47,
    U+1EE49,U+1EE4B,U+1EE4D-1EE4F,U+1EE51-1EE52,U+1EE54,U+1EE57,U+1EE59,
    U+1EE5B,U+1EE5D,U+1EE5F,U+1EE61-1EE62,U+1EE64,U+1EE67-1EE6A,U+1EE6C-1EE72,
    U+1EE74-1EE77,U+1EE79-1EE7C,U+1EE7E,U+1EE80-1EE89,U+1EE8B-1EE9B,
    U+1EEA1-1EEA3,U+1EEA5-1EEA9,U+1EEAB-1EEBB,U+1EEF0-1EEF1;
}
@font-face{
  font-family:'Cairo';
  font-style:normal;
  font-weight:400 800;
  font-display:swap;
  src:url('../assets/fonts/cairo-latin.woff2') format('woff2');
  unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,
    U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,
    U+2212,U+2215,U+FEFF,U+FFFD;
}
"""


TOKENS_CSS = """
:root{
  /* ── ألوان تُضبط من Telegram.themeParams (تُحدَّث من JS أيضاً) ── */
  --bd-bg:        var(--tg-theme-bg-color, #0f141a);
  --bd-surface:   var(--tg-theme-secondary-bg-color, #1a212a);
  --bd-surface-2: var(--tg-theme-section-separator-color, rgba(255,255,255,.08));
  --bd-text:      var(--tg-theme-text-color, #eef2f7);
  --bd-hint:      var(--tg-theme-hint-color, #93a4b8);
  --bd-link:      var(--tg-theme-link-color, #62bcf9);
  --bd-btn:       var(--tg-theme-button-color, var(--bd-brand));
  --bd-btn-text:  var(--tg-theme-button-text-color, #ffffff);
  --bd-danger:    #f85149;
  --bd-ok:        #3fb950;
  --bd-warn:      #e3a33d;

  /* ── هوية المجموعة (تُحقن حسب تصنيف البوت) ── */
  --bd-brand:     #3b82f6;
  --bd-brand-2:   #22d3ee;
  --bd-brand-soft:rgba(59,130,246,.14);
  --bd-brand-line:rgba(59,130,246,.42);

  /* ── مقاسات ومسافات ── */
  --bd-r-xs: 8px;
  --bd-r-sm: 10px;
  --bd-r-md: 14px;
  --bd-r-lg: 20px;
  --bd-r-pill: 999px;
  --bd-sp-1: 4px;
  --bd-sp-2: 8px;
  --bd-sp-3: 12px;
  --bd-sp-4: 16px;
  --bd-sp-5: 22px;
  --bd-sp-6: 30px;
  --bd-max: 560px;

  /* ── ظلال ── */
  --bd-shadow-1: 0 1px 2px rgba(0,0,0,.18), 0 4px 14px rgba(0,0,0,.10);
  --bd-shadow-2: 0 10px 32px rgba(0,0,0,.28);
  --bd-glow: 0 6px 26px var(--bd-brand-soft);

  /* ── الخط ── */
  --bd-font: 'Cairo','Tajawal','Segoe UI',Tahoma,Arial,sans-serif;
  --bd-fs-xs: 11.5px;
  --bd-fs-sm: 13px;
  --bd-fs-md: 15px;
  --bd-fs-lg: 19px;
  --bd-fs-xl: 24px;

  /* ── حركة ── */
  --bd-ease: cubic-bezier(.22,.8,.28,1);
  --bd-dur-1: 120ms;
  --bd-dur-2: 220ms;
  --bd-dur-3: 380ms;

  /* ── مناطق آمنة (iPhone notch / شريط Android) ── */
  --bd-safe-top: env(safe-area-inset-top, 0px);
  --bd-safe-bottom: env(safe-area-inset-bottom, 0px);
  --bd-banner-h: 0px;

  /* ── أسماء متوافقة مع الأنماط القديمة (app_defs) ── */
  --bg: var(--bd-bg);
  --surface: var(--bd-surface);
  --text: var(--bd-text);
  --hint: var(--bd-hint);
  --accent: var(--bd-btn);
  --btn-txt: var(--bd-btn-text);
  --link: var(--bd-link);
  --danger: var(--bd-danger);
  --ok: var(--bd-ok);
  --warn: var(--bd-warn);
  --radius: var(--bd-r-md);
}

/* خلفية فاتحة احتياطية عندما لا يزوّد تيليجرام بالثيم */
@media (prefers-color-scheme: light){
  :root{
    --bd-bg:        var(--tg-theme-bg-color, #f5f7fa);
    --bd-surface:   var(--tg-theme-secondary-bg-color, #ffffff);
    --bd-text:      var(--tg-theme-text-color, #101820);
    --bd-hint:      var(--tg-theme-hint-color, #5d6b7a);
    --bd-surface-2: var(--tg-theme-section-separator-color, rgba(0,0,0,.07));
  }
}
"""


BASE_CSS = """
*,*::before,*::after{ box-sizing:border-box; margin:0; padding:0;
  -webkit-tap-highlight-color:transparent; }
html,body{ min-height:100%; }
html{ background:var(--bd-bg); }
body{
  font-family:var(--bd-font);
  font-size:var(--bd-fs-md);
  line-height:1.75;
  color:var(--bd-text);
  background:
    radial-gradient(1200px 520px at 50% -220px, var(--bd-brand-soft), transparent 70%),
    var(--bd-bg);
  background-attachment:fixed;
  padding:calc(14px + var(--bd-safe-top)) 14px
          calc(28px + var(--bd-banner-h) + var(--bd-safe-bottom));
  transition:background-color var(--bd-dur-3) var(--bd-ease),
             color var(--bd-dur-3) var(--bd-ease);
  overflow-x:hidden;
  text-rendering:optimizeLegibility;
  -webkit-font-smoothing:antialiased;
}
.container{ max-width:var(--bd-max); margin:0 auto; }
a{ color:var(--bd-link); }

/* ── رأس التطبيق بهوية المجموعة ── */
.app-header{ position:relative; text-align:center; padding:20px 0 16px; }
.app-header::before{
  content:""; position:absolute; inset:-40px 0 auto; height:150px;
  background:radial-gradient(closest-side, var(--bd-brand-soft), transparent 78%);
  pointer-events:none; z-index:0;
}
.app-header .emoji{
  position:relative; z-index:1; display:inline-grid; place-items:center;
  width:76px; height:76px; font-size:40px; line-height:1;
  border-radius:26px;
  background:linear-gradient(145deg, var(--bd-brand-soft), transparent 70%),
             var(--bd-surface);
  border:1px solid var(--bd-brand-line);
  box-shadow:var(--bd-glow);
  animation:bd-pop var(--bd-dur-3) var(--bd-ease) both;
}
.app-header h1{
  position:relative; z-index:1; margin-top:12px;
  font-size:var(--bd-fs-xl); font-weight:800; letter-spacing:.2px;
}
.app-header p{ position:relative; z-index:1; color:var(--bd-hint);
  font-size:var(--bd-fs-sm); margin-top:2px; }

/* ── تذييل ── */
.app-footer{
  text-align:center; color:var(--bd-hint); font-size:var(--bd-fs-xs);
  margin-top:26px; line-height:2.1;
}
.app-footer a{ color:var(--bd-link); text-decoration:none; font-weight:700; }
"""


def build_tokens_css(tag: str = "", bot_id: str = "") -> str:
    """تجميع FONT + TOKENS مع حقن هوية المجموعة الصحيحة."""
    pal = group_palette(tag, bot_id)
    r, g, b = _hex_rgb(pal["brand"])
    override = (
        ":root{"
        f"--bd-brand:{pal['brand']};"
        f"--bd-brand-2:{pal['brand2']};"
        f"--bd-brand-soft:rgba({r},{g},{b},.15);"
        f"--bd-brand-line:rgba({r},{g},{b},.42);"
        "}"
    )
    return FONT_CSS + TOKENS_CSS + override + BASE_CSS


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
