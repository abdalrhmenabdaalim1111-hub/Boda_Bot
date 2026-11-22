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
import html as _html

from design_system import build_css, brand, SDK_JS

# توافق خلفي مع أي استيراد قديم
COMMON_CSS = build_css()
COMMON_JS = SDK_JS

SHELL_CSS = """
.app-group{display:inline-block;margin-top:6px;font-size:10.5px;font-weight:800;
  color:var(--bd-brand);background:var(--bd-brand-soft);border:1px solid var(--bd-brand-line);
  padding:3px 10px;border-radius:999px;}
.footer-links{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:8px;}
.footer-link{display:inline-flex;align-items:center;gap:5px;padding:6px 11px;border-radius:999px;
  background:var(--bd-surface-2);color:var(--bd-text);font-size:11.5px;font-weight:700;
  text-decoration:none;border:none;cursor:pointer;font-family:inherit;}
.footer-link:active{transform:scale(.96);}
.footer-brand{opacity:.7;}
/* مساحة آمنة للبانر الثابت أسفل الشاشة حتى لا يغطي محتوى التطبيق */
body.boda-app{padding-bottom:calc(var(--bd-banner-h, 0px) + 6px);}
.boda-app .container{padding-bottom:calc(var(--bd-banner-h, 0px) + 10px);}
.ad-banner{background:color-mix(in srgb,var(--bd-surface) 96%,transparent);}
.ad-banner .ad-text{font-size:12px;line-height:1.7;}
.ad-banner .ad-text a{color:var(--bd-link);font-weight:800;text-decoration:none;}
/* وميض قصير قبل إعلان الفيديو (Flashing Ads) */
body.ad-flash::after{content:"";position:fixed;inset:0;z-index:180;pointer-events:none;
  background:radial-gradient(circle,rgba(255,255,255,.85),rgba(234,179,8,.35) 60%,transparent 75%);
  animation:bd-adflash .28s ease-out both;}
@keyframes bd-adflash{0%{opacity:0}35%{opacity:1}100%{opacity:0}}
#recent-apps{display:flex;gap:6px;justify-content:center;flex-wrap:wrap;margin:6px 0 10px;}
#recent-apps .recent{display:inline-flex;align-items:center;gap:4px;padding:4px 9px;border-radius:999px;
  background:var(--bd-surface-2);color:var(--bd-text);font-size:10.5px;text-decoration:none;}
"""


def build_html(*, bot_id: str, emoji: str, title: str, subtitle: str,
               body_html: str, app_js: str, app_css: str = "",
               api_base: str = "", ads_cfg: dict | None = None,
               ad_markers: list | None = None,
               share_url: str = "https://t.me/BodaStoreeBot",
               back_url: str = "", page_url: str = "",
               group: str = "", lang: str = "ar",
               user_id: int = 0, session_id: str = "") -> str:
    """تجميع صفحة تطبيق كاملة من القالب + أجزاء التطبيق.

    group: وسم/تصنيف البوت (مثل "أدوات 🛠️") لاختيار هوية المجموعة.
    """
    # أفعّل بانر المتجر الثابت أسفل التطبيق، وأوقف الراعي البيني حتى لا يتعارض
    # مع إعلانات الفيديو (Monetag) التي تُشغّلها التطبيقات بأنفسها.
    ads_data = dict(ads_cfg or {})
    ads_data["sponsor"] = None
    ads_data["every"] = 999
    # منع إغلاق وسم <script> داخل بيانات الإعلانات المُحقونة ( snippets تحتوي </script> )
    ads_json = _json.dumps(ads_data, ensure_ascii=False).replace("</", "<\\/")
    pal = brand(tag=group, bot_id=bot_id)

    css = build_css(tag=group, bot_id=bot_id) + "\n" + app_css + "\n" + SHELL_CSS
    share_attr = f"Boda.share('جرّب هذا البوت — Boda','{share_url}')"
    share_attr = _html.escape(share_attr, quote=False)
    monetag_tag = ""

    # ── فافيكون SVG مدمج (بدون طلب شبكة) ──
    favicon = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
               f"<text x='0' y='26' font-size='26'>{emoji}</text></svg>").replace(
               "<", "%3C").replace(">", "%3E").replace(" ", "%20").replace("'", "%27")
    full_desc = str(subtitle)[:150]

    og = ""
    if page_url:
        og = (f'<meta property="og:type" content="website">\n'
              f'<meta property="og:site_name" content="متجر تطبيقات بودة">\n'
              f'<meta property="og:url" content="{page_url}">\n'
              f'<meta property="og:title" content="{emoji} {title} — Boda">\n'
              f'<meta property="og:description" content="{full_desc}">\n'
              f'<meta name="twitter:card" content="summary">\n'
              f'<meta name="twitter:title" content="{emoji} {title} — Boda">\n'
              f'<meta name="twitter:description" content="{full_desc}">\n')
    apple_meta = ("<meta name=\"apple-mobile-web-app-capable\" content=\"yes\">\n"
                  "<meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">\n")
    canonical = f'<link rel="canonical" href="{page_url}">\n' if page_url else ""

    result = f"""<!DOCTYPE html>
<html dir="rtl" lang="{lang}" data-group="{pal['group']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="description" content="{full_desc}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="{pal['brand']}">
<meta name="format-detection" content="telephone=no">
<meta name="robots" content="index,follow">
{apple_meta}
<link rel="icon" href="{favicon}">
<link rel="preload" href="../assets/fonts/cairo-arabic.woff2" as="font"
      type="font/woff2" crossorigin>
<link rel="preload" href="../assets/fonts/cairo-latin.woff2" as="font"
      type="font/woff2" crossorigin>
{og}{canonical}<title>{emoji} {title} — Boda</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
{monetag_tag}<style>{css}</style>
</head>
<body class="boda-app" data-bot="{bot_id}" data-group="{pal['group']}">
<div class="container">
  <header class="app-header">
    <span class="emoji" aria-hidden="true">{emoji}</span>
    <h1>{title}</h1>
    <p>{subtitle}</p>
    {f'<span class="app-group">{group}</span>' if group else ''}
  </header>

  <main id="app">
{body_html}
  </main>

  <footer class="app-footer">
    <div id="recent-apps" aria-label="آخر التطبيقات المستخدمة"></div>
    <div class="footer-links">
      <button type="button" class="footer-link" onclick="{share_attr}">📤 مشاركة</button>
      <a class="footer-link" href="https://t.me/BodaStoreeBot">💬 الدعم</a>
    </div>
    <div class="footer-brand">Powered by Boda Bot System</div>
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
<script>
/* Flashing Ads + Recent Actions — مشترك لكل التطبيقات */
(function(){{
  try{{
    if(typeof window.showAd==='function'){{
      var _ad=window.showAd;
      window.showAd=function(){{
        document.body.classList.add('ad-flash');
        setTimeout(function(){{ document.body.classList.remove('ad-flash'); try{{ _ad(); }}catch(e){{}} }}, 260);
      }};
    }}
  }}catch(e){{}}
  try{{
    var key='boda_recent_apps', cur=window.__BODA_BOT_ID__||'{bot_id}';
    var arr=JSON.parse(localStorage.getItem(key)||'[]').filter(function(x){{return x!==cur;}});
    arr.unshift(cur); localStorage.setItem(key, JSON.stringify(arr.slice(0,4)));
    var box=document.getElementById('recent-apps');
    if(box && arr.length>1){{
      box.innerHTML='<span style="color:var(--hint);font-size:10px">آخر التطبيقات:</span>'+
        arr.slice(1,4).map(function(id){{return '<a class="recent" href="../'+id+'/">'+id+'</a>';}}).join('');
    }}
  }}catch(e){{}}
}})();
</script>
<script>
/* Internal Promotion Banner — مشترك لكل التطبيقات */
(function(){{
  const BOT_ID = "{bot_id}";
  const USER_ID = "{user_id or 0}";
  const SESSION_ID = "{session_id or ''}";
  const PROMO_SCRIPT = document.createElement('script');
  PROMO_SCRIPT.src = "../shared/promo-banner.js";
  PROMO_SCRIPT.dataset.botId = BOT_ID;
  PROMO_SCRIPT.dataset.userId = USER_ID;
  PROMO_SCRIPT.dataset.sessionId = SESSION_ID;
  document.head.appendChild(PROMO_SCRIPT);
}})();
</script>
<noscript>هذا التطبيق يتطلب JavaScript للعمل.</noscript>
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
