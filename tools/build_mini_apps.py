# -*- coding: utf-8 -*-
"""
tools/build_mini_apps.py — مولّد التطبيقات المصغّرة والمتجر

يبني في webroot/ (جاهز للرفع على GitHub Pages):
  index.html          → صفحة تحويل سريعة للمتجر
  store/index.html    → 🏪 متجر تطبيقات بودة كتطبيق مصغّر (تصفح/بحث/إحصائيات)
  data/stats.json     → إحصائيات حية من قاعدة البيانات + الأحداث
  <bot_id>/index.html → تطبيق كل بوت (تفاعلي أو صفحة تعريفية)

الإعلانات: تُقرأ من Data/ads_config.json وتُدمج داخل كل تطبيق.
الاستخدام:  python tools/build_mini_apps.py [--out webroot] [--no-store]
"""
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app_template import build_html          # noqa: E402
from app_defs import APPS                    # noqa: E402

ROOT   = Path(__file__).parent.parent
DATA   = ROOT / "Data"
DB     = DATA / "boda_bot.db"
EVENTS = DATA / "events.jsonl"
ADS    = DATA / "ads_config.json"
REG    = ROOT / "bots_registry.json"

STORE_URL   = "https://t.me/BodaStoreeBot"
DEV_EVENT_DAYS = 30

# قاعدة موقع التطبيقات (من .env: MINIAPPS_BASE_URL) لبناء وسوم Open Graph
MINIAPPS_BASE = ""
try:
    from dotenv import load_dotenv  # noqa: E402
    load_dotenv(ROOT / ".env")
    MINIAPPS_BASE = os.getenv("MINIAPPS_BASE_URL", "").strip().rstrip("/")
except Exception:
    pass


# ── الإعلانات من ads_config.json و monetag_config.json ─────────────────────────
def build_ads_cfg(bot_id: str = None) -> dict:
    cfg = {}
    try:
        cfg = json.loads(ADS.read_text(encoding="utf-8"))
    except Exception:
        pass

    # تحميل إعدادات Monetag المخصصة لكل تطبيق
    monetag_cfg = {}
    monetag_file = DATA / "monetag_config.json"
    if monetag_file.exists():
        try:
            m_all = json.loads(monetag_file.read_text(encoding="utf-8"))
            if bot_id and bot_id in m_all.get("bots", {}):
                b_cfg = m_all["bots"][bot_id]
                if b_cfg.get("has_custom_ads") and b_cfg.get("active", True):
                    monetag_cfg = b_cfg
            if not monetag_cfg and m_all.get("global_default", {}).get("enabled"):
                monetag_cfg = m_all["global_default"]
        except Exception:
            pass

    banner = sponsor = None
    every = 3

    # إعداد راعي Monetag (Direct Link)
    direct_link = monetag_cfg.get("direct_link", "").strip()
    if direct_link:
        sponsor = {
            "title": "🌟 راعي التطبيق الرسمي (Monetag)",
            "text": "استكشف العرض الحصري المدعوم من شركائنا بضغطة واحدة!",
            "url": direct_link,
            "button": "🔥 مشاهدة العرض الآن",
        }
        every = int(monetag_cfg.get("frequency", 3))
    else:
        b = cfg.get("button_ad", {})
        if b.get("enabled"):
            sponsor = {
                "title": b.get("button_text", "🌟 متجر تطبيقات بودا"),
                "text": "أقوى البوتات والتطبيقات مجاناً — جرّب المتجر الآن!",
                "url": b.get("url", STORE_URL),
                "button": "🏪 زيارة المتجر",
            }

    f = cfg.get("footer_ad", {})
    if f.get("enabled"):
        every = max(2, int(f.get("frequency", every)))
        banner = {"icon": "📢", "html": f.get("text", "").strip()}

    script_url = monetag_cfg.get("script_url", "").strip()
    zone_id = monetag_cfg.get("zone_id", "").strip()
    if not script_url and zone_id:
        script_url = f"https://thubanoa.com/1?z={zone_id}"

    return {
        "banner": banner,
        "sponsor": sponsor,
        "every": every,
        "monetag_script": script_url,
        "monetag_zone": zone_id,
        "has_monetag": bool(direct_link or zone_id or script_url)
    }


# ── الإحصائيات من قاعدة البيانات + الأحداث ──────────────────────────────────
def collect_stats() -> dict:
    stats = {"generated_at": datetime.now().isoformat(timespec="seconds"),
             "bots": {}, "total_users": 0, "events": {}}
    try:
        con = sqlite3.connect(DB)
        rows = con.execute(
            "SELECT bot_name, COUNT(DISTINCT user_id), SUM(usage_count) "
            "FROM users GROUP BY bot_name").fetchall()
        for bot, users, uses in rows:
            stats["bots"][bot] = {"users": users or 0, "uses": uses or 0}
            stats["total_users"] += users or 0
        # آخر 30 يوماً: مستخدمو كل بوت
        cutoff = (datetime.now() - timedelta(days=DEV_EVENT_DAYS)).strftime("%Y-%m-%d")
        rows = con.execute(
            "SELECT bot_name, COUNT(DISTINCT user_id) FROM users "
            "WHERE last_seen >= ? GROUP BY bot_name", (cutoff,)).fetchall()
        for bot, active in rows:
            stats["bots"].setdefault(bot, {})["active_30d"] = active
        con.close()
    except Exception:
        pass

    try:
        ev = Counter()
        if EVENTS.exists():
            with open(EVENTS, encoding="utf-8") as fh:
                for line in fh.readlines()[-5000:]:
                    try:
                        e = json.loads(line)
                        ev[f"{e.get('event')}:{e.get('bot')}"] += 1
                    except Exception:
                        continue
        stats["events"] = dict(ev.most_common(100))
    except Exception:
        pass

    return stats


# ── صفحة تعريفية للبوتات بلا تطبيق تفاعلي بعد ────────────────────────────────
def landing_body(app: dict, username: str) -> tuple[str, str]:
    emoji = app.get("emoji", "🤖")
    name = app.get("name", "")
    desc = app.get("short_desc") or app.get("description") or ""
    body = f"""
<div class="card" style="text-align:center">
  <div style="font-size:64px">{emoji}</div>
  <h2 style="margin:10px 0">{name}</h2>
  <p style="color:var(--hint);line-height:2;font-size:14px">{desc}</p>
  <p style="font-size:13.5px;line-height:2">هذا البوت يعمل بالكامل عبر المحادثة.<br>
  <b>النسخة التفاعلية قيد التطوير</b> — افتح البوت الآن واستمتع!</p>
  <button class="btn" onclick="location.href='https://t.me/{username}'">🤖 فتح البوت في تيليجرام</button>
</div>"""
    js = "Boda.track('app_open',{detail:'landing'});"
    return body, js


# ── بناء صفحة تطبيق واحد ─────────────────────────────────────────────────────
def render_app(app: dict, ads_cfg: dict, api_base: str, username: str) -> str:
    bot_id = app["id"]
    app_def = APPS.get(bot_id)
    interactive = bool(app_def and app_def.get("interactive"))
    if app_def:
        body = app_def["body"]
        js   = app_def["js"]
        css  = app_def.get("css", "")
        title    = app_def["title"]
        subtitle = app_def["subtitle"]
    else:
        body, js = landing_body(app, username)
        css = ""
        title    = app.get("name", bot_id)
        subtitle = app.get("short_desc", "تطبيق مصغّر داخل تيليجرام")

    share = f"https://t.me/{username}"
    return build_html(
        bot_id=bot_id, emoji=app.get("emoji", "🤖"),
        title=title, subtitle=subtitle,
        body_html=body, app_js=js, app_css=css,
        api_base=api_base, ads_cfg=ads_cfg,
        share_url=share, back_url="../store/",
        page_url=f"{MINIAPPS_BASE}/{bot_id}/" if MINIAPPS_BASE else "")


# ── المتجر كتطبيق مصغّر ──────────────────────────────────────────────────────
STORE_CSS = """
.cats { display:flex; gap:8px; overflow-x:auto; padding-bottom:6px; margin-bottom:12px; }
.cats::-webkit-scrollbar { display:none; }
.cat { flex-shrink:0; padding:8px 14px; border-radius:999px; font-size:13.5px;
  cursor:pointer; background:var(--surface); border:1.5px solid var(--hint); }
.cat.active { background:var(--accent); color:var(--btn-txt); border-color:var(--accent); }
.search { width:100%; padding:12px 16px; border-radius:999px; border:1.5px solid transparent;
  background:var(--surface); color:var(--text); font-size:15px; outline:none; margin-bottom:4px; }
.search:focus { border-color:var(--accent); }
.app-card { display:flex; gap:12px; align-items:center; background:var(--surface);
  border-radius:14px; padding:14px; margin-bottom:10px; cursor:pointer;
  transition:transform .15s; border:1.5px solid transparent; }
.app-card:active { transform:scale(.98); border-color:var(--accent); }
.app-card .ic { font-size:34px; width:56px; height:56px; display:flex; align-items:center;
  justify-content:center; background:var(--bg); border-radius:13px; flex-shrink:0; }
.app-card .info { flex:1; min-width:0; }
.app-card h3 { font-size:15px; margin-bottom:3px; }
.app-card p { color:var(--hint); font-size:12.5px; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }
.app-card .meta { color:var(--link); font-size:11.5px; margin-top:4px; }
.badge-new { background:var(--warn); color:#111; font-size:10px; font-weight:800;
  padding:2px 8px; border-radius:999px; margin-inline-start:6px; vertical-align:middle; }
.badge-soon { background:var(--hint); color:var(--bg); font-size:10px; font-weight:800;
  padding:2px 8px; border-radius:999px; margin-inline-start:6px; vertical-align:middle; }
.app-card.soon { opacity:.55; }
.hero { background:linear-gradient(135deg,rgba(82,136,193,.25),rgba(82,136,193,.08));
  border:1px solid rgba(82,136,193,.4); border-radius:16px; padding:18px;
  text-align:center; margin-bottom:14px; }
.hero .big { font-size:34px; }
.hero h2 { margin:6px 0 2px; }
.hero p { color:var(--hint); font-size:13px; }
.stat-row { display:flex; gap:8px; margin-top:12px; }
.stat { flex:1; background:var(--bg); border-radius:11px; padding:10px 6px; }
.stat b { font-size:17px; display:block; }
.stat span { font-size:11px; color:var(--hint); }
"""

STORE_JS = """
let APPS=[], CATS={}, stats={}, cat='الكل', q='';
const urlp=new URLSearchParams(location.search);
const CATEGORIZED = urlp.get('web')==='1';   // فتح كصفحة ويب يعرض كل التطبيقات

async function boot(){
  try { const r=await fetch('../data/stats.json'); stats=await r.json(); } catch(e){}
  try {
    const r=await fetch('../data/catalog.json');
    APPS=await r.json();
  } catch(e) { APPS=[]; }
  buildCats(); render();
  document.getElementById('s-users').textContent = fmt((stats.total_users||0));
  document.getElementById('s-apps').textContent  = APPS.length;
  const ev=stats.events||{};
  document.getElementById('s-opens').textContent = fmt(Object.entries(ev)
    .filter(([k])=>k.startsWith('app_open:')).reduce((s,[,v])=>s+v,0));
}
function fmt(n){ n=+n||0; return n>=1000?(n/1000).toFixed(1)+'K':n; }
function buildCats(){
  const box=document.getElementById('cats'); const set=new Set(APPS.map(a=>a.tag||'أخرى'));
  CATS=['الكل',...[...set].sort()];
  box.innerHTML=CATS.map(c=>'<span class="cat'+(c===cat?' active':'')+'" onclick="setCat(\\''+c+'\\',this)">'+c+'</span>').join('');
}
function setCat(c,el){ cat=c; document.querySelectorAll('.cat').forEach(x=>x.classList.remove('active'));
  el.classList.add('active'); render(); }
function render(){
  const list=APPS.filter(a=>(cat==='الكل'||a.tag===cat)&&
    (!q||(a.name+' '+a.short_desc+' '+(a.username||'')).toLowerCase().includes(q.toLowerCase())));
  // الظاهر أولاً، والمخفي (قريباً) آخراً
  list.sort((x,y)=>(x.hidden?1:0)-(y.hidden?1:0));
  document.getElementById('list').innerHTML = list.length? list.map(a=>{
    const st=(stats.bots||{})[a.id]||{};
    const isNew=a.added_date && !a.hidden && (Date.now()-new Date(a.added_date))<30*864e5;
    return '<div class="app-card'+(a.hidden?' soon':'')+'" onclick="openApp(\\''+a.url+'\\',\\''+a.web+'\\')">'+
      '<div class="ic">'+a.emoji+'</div>'+
      '<div class="info"><h3>'+a.name+(isNew?'<span class="badge-new">جديد</span>':'')+
        (a.hidden?'<span class="badge-soon">قريباً</span>':'')+'</h3>'+
      '<p>'+(a.description||a.short_desc)+'</p>'+
      '<div class="meta">'+(a.username?'<b dir="ltr">'+a.username+'</b> · ':'')+'👥 '+
        (st.users?st.users+' مستخدم':'جديد على المنصة')+
        (st.active_30d?' · 🔥 '+st.active_30d+' نشط هذا الشهر':'')+'</div></div>'+
      '<div style="color:var(--hint);font-size:20px">‹</div></div>';
  }).join('') : '<p style="text-align:center;color:var(--hint);padding:30px 0">🔍 لا نتائج</p>';
}
function openApp(url, web){
  Boda.haptic('light'); Boda.track('store_open',{detail:web||url});
  try{ Boda.tg.openTelegramLink(url); }catch(e){ location.href=url; }
}
document.querySelector('.search').addEventListener('input',e=>{ q=e.target.value; render(); });
boot();
"""


def render_store(apps: list, ads_cfg: dict, api_base: str) -> str:
    body = """
<div class="hero">
  <p>كل بوتاتك وتطبيقاتك — في مكان واحد ✨</p>
  <div class="stat-row">
    <div class="stat"><b id="s-apps">—</b><span>تطبيق</span></div>
    <div class="stat"><b id="s-users">—</b><span>مستخدم</span></div>
    <div class="stat"><b id="s-opens">—</b><span>فتح تطبيق</span></div>
  </div>
</div>
<input class="search" placeholder="🔍 ابحث عن بوت...">
<div class="cats" id="cats"></div>
<div id="list"></div>"""
    catalog = [{"id": a["id"], "emoji": a.get("emoji", "🤖"), "name": a.get("name", ""),
                "short_desc": a.get("short_desc", ""), "tag": a.get("tag", "أخرى"),
                "description": a.get("description", ""),
                "username": a.get("username", ""),
                "url": a.get("url", STORE_URL), "web": f"{a['id']}/",
                "added_date": a.get("added_date", ""),
                "hidden": bool(a.get("hidden"))}
               for a in apps]
    return build_html(
        bot_id="store", emoji="🏪", title="متجر تطبيقات بودة",
        subtitle="تصفح كل البوتات والتطبيقات المصغّرة",
        body_html=body, app_js=STORE_JS, app_css=STORE_CSS,
        api_base=api_base, ads_cfg={"banner": None, "sponsor": ads_cfg.get("sponsor"), "every": 99},
        share_url=STORE_URL,
        page_url=f"{MINIAPPS_BASE}/store/" if MINIAPPS_BASE else "").replace(
        "window.__BODA_BOT_ID__   = \"store\";",
        "window.__BODA_BOT_ID__   = \"store\";\nwindow.__BODA_CATALOG__ = "
        + json.dumps(catalog, ensure_ascii=False))


def main():
    out_dir = ROOT / "webroot"
    api_base = os.getenv("BODA_API_BASE", "").strip().rstrip("/")
    ads_cfg = build_ads_cfg()

    try:
        apps = json.loads(REG.read_text(encoding="utf-8"))
    except Exception:
        print("❌ تعذر قراءة bots_registry.json")
        return 1

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "data").mkdir(parents=True)

    # catalog.json — مصدر المتجر (نفس بنية النسخة المضمنة في store/index.html)
    catalog = [{"id": a["id"], "emoji": a.get("emoji", "🤖"), "name": a.get("name", ""),
                "short_desc": a.get("short_desc", ""), "tag": a.get("tag", "أخرى"),
                "description": a.get("description", ""),
                "username": a.get("username", ""),
                "url": a.get("url", STORE_URL), "web": f"{a['id']}/",
                "added_date": a.get("added_date", ""),
                "hidden": bool(a.get("hidden"))}
               for a in apps]
    (out_dir / "data" / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")

    # stats.json — من قاعدة البيانات
    stats = collect_stats()
    (out_dir / "data" / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    # كل تطبيق — بما فيها المخفية (المتجر يعرض الجميع مع وسم "قريباً" للمخفي)
    webapps_dir = ROOT / "webapps"
    webapps_dir.mkdir(exist_ok=True)
    n_interactive = 0
    for app in apps:
        if not app.get("id"):
            continue
        bid = app["id"]
        username = (app.get("username") or "").lstrip("@") or "BodaStoreeBot"
        app_ads = build_ads_cfg(bid)
        html = render_app(app, app_ads, api_base, username)
        if bid in APPS and APPS[bid].get("interactive"):
            n_interactive += 1
        d = out_dir / bid
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(html, encoding="utf-8")
        # نسخة ملف فردي في webapps/
        (webapps_dir / f"{bid}.html").write_text(html, encoding="utf-8")

    # المتجر
    (out_dir / "store").mkdir(exist_ok=True)
    (out_dir / "store" / "index.html").write_text(
        render_store(apps, ads_cfg, api_base), encoding="utf-8")

    # index الرئيسي → المتجر
    (out_dir / "index.html").write_text(
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=store/"></head>'
        '<body>جاري فتح المتجر...</body></html>', encoding="utf-8")

    # .nojekyll لـ GitHub Pages
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"✅ تم البناء في {out_dir.name}/")
    print(f"   📱 تطبيقات تفاعلية: {n_interactive}")
    print(f"   📄 صفحات بوتات: {sum(1 for a in apps if not a.get('hidden'))}")
    print(f"   👥 إجمالي المستخدمين المكتشفين: {stats['total_users']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
