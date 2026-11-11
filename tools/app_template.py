# -*- coding: utf-8 -*-
"""
tools/app_template.py — القالب المشترك لكل التطبيقات المصغّرة

يعتمد الآن على نظام التصميم الموحد في:
  • ``ds_tokens.py``     — الألوان/الخط/المسافات/الحركة + هوية كل مجموعة
  • ``ds_components.py`` — مكتبة المكونات (أزرار/بطاقات/حقول/نتائج…)
  • ``ds_sdk.py``        — Telegram SDK + الإعلانات + التتبع

عقد الاستخدام لم يتغيّر: ``build_html(bot_id=..., body_html=..., app_js=...)``
لذلك كل التطبيقات الحالية تعمل دون تعديل.
"""
import json as _json

from design_system import build_css, brand, SDK_JS

# توافق خلفي مع أي استيراد قديم
COMMON_CSS = build_css()
COMMON_JS = SDK_JS


def build_html(*, bot_id: str, emoji: str, title: str, subtitle: str,
               body_html: str, app_js: str, app_css: str = "",
               api_base: str = "", ads_cfg: dict | None = None,
               ad_markers: list | None = None,
               share_url: str = "https://t.me/BodaStoreeBot",
               back_url: str = "", page_url: str = "",
               group: str = "", lang: str = "ar") -> str:
    """تجميع صفحة تطبيق كاملة من القالب + أجزاء التطبيق.

    group: وسم/تصنيف البوت (مثل "أدوات 🛠️") لاختيار هوية المجموعة.
    """
    ads_data = ads_cfg or {"banner": None, "sponsor": None, "every": 3}
    ads_json = _json.dumps(ads_data, ensure_ascii=False)
    pal = brand(tag=group, bot_id=bot_id)

    css = build_css(tag=group, bot_id=bot_id) + "\n" + app_css
    back_link = (f'<a href="{back_url}">🏠 الصفحة الرئيسية</a> · '
                 if back_url else "")
    monetag_tag = ""
    if ads_data.get("monetag_script"):
        monetag_tag = f'<script src="{ads_data["monetag_script"]}"></script>\n'

    # ── فافيكون SVG مدمج (بدون طلب شبكة) ──
    favicon = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
               f"<text x='0' y='26' font-size='26'>{emoji}</text></svg>").replace(
               "<", "%3C").replace(">", "%3E").replace(" ", "%20").replace("'", "%27")
    full_desc = str(subtitle)[:150]

    og = ""
    if page_url:
        og = (f'<meta property="og:type" content="website">\n'
              f'<meta property="og:url" content="{page_url}">\n'
              f'<meta property="og:title" content="{emoji} {title} — Boda">\n'
              f'<meta property="og:description" content="{full_desc}">\n'
              f'<meta name="twitter:card" content="summary">\n'
              f'<meta name="twitter:title" content="{emoji} {title} — Boda">\n'
              f'<meta name="twitter:description" content="{full_desc}">\n')

    result = f"""<!DOCTYPE html>
<html dir="rtl" lang="{lang}" data-group="{pal['group']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="description" content="{full_desc}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="{pal['brand']}">
<meta name="format-detection" content="telephone=no">
<link rel="icon" href="{favicon}">
<link rel="preload" href="../assets/fonts/cairo-arabic.woff2" as="font"
      type="font/woff2" crossorigin>
<link rel="preload" href="../assets/fonts/cairo-latin.woff2" as="font"
      type="font/woff2" crossorigin>
{og}<title>{emoji} {title} — Boda</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
{monetag_tag}<style>{css}</style>
</head>
<body class="boda-app" data-bot="{bot_id}" data-group="{pal['group']}">
<div class="container">
  <header class="app-header">
    <span class="emoji" aria-hidden="true">{emoji}</span>
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </header>

  <main id="app">
{body_html}
  </main>

  <footer class="app-footer">
    {back_link}<a href="https://t.me/BodaStoreeBot">🏪 متجر تطبيقات بودا</a><br>
    Powered by Boda Bot System
  </footer>
</div>
<div id="toast" role="status" aria-live="polite"></div>
<script>
window.__BODA_BOT_ID__   = "{bot_id}";
window.__BODA_GROUP__    = "{pal['group']}";
window.__BODA_BRAND__    = "{pal['brand']}";
window.__BODA_API__      = "{api_base}";
window.__BODA_SHARE__    = "{share_url}";
window.__BODA_ADS__      = {ads_json};
</script>
<script>{SDK_JS}</script>
<script>{app_js}</script>
</body>
</html>"""

    # ── حقن علامات الإعلانات (Phase A1) ─────────────────────────────────
    if ad_markers:
        try:
            import sys as _sys
            from pathlib import Path as _P
            _sys.path.insert(0, str(_P(__file__).parent.parent))
            from control_center.ads.injector import inject_markers as _inj
            _blocks = []
            for m in ad_markers:
                if isinstance(m, (tuple, list)) and len(m) >= 3:
                    _blocks.append((str(m[0]), str(m[1]), str(m[2])))
            if _blocks:
                result = _inj(result, _blocks)
        except Exception:
            pass

    return result
