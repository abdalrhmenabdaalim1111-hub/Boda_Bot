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

# Windows cp1252 guard: when stdout is a pipe (tests/CI), Python falls back to
# cp1252 which cannot encode Arabic/emoji output — force UTF-8 (PLAN_V3 risk).
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from app_template import build_html          # noqa: E402
from app_defs import APPS                    # noqa: E402
from Bots_Folder.store_catalog import (      # noqa: E402
    visible_bots,
)

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

# قاعدة الموقع الرئيسي لملفات SEO (sitemap/robots) — نفس نطاق الصفحات الموحدة
PAGES_BASE = (MINIAPPS_BASE or
              "https://abdalrhmenabdaalim1111-hub.github.io/Boda_Bot").rstrip("/")


# ── الإعلانات من ads_config.json و monetag_config.json ─────────────────────────
def build_ads_cfg(bot_id: str = None) -> dict:
    """Build ads configuration for a bot from ads_config.json and monetag_config.json."""
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

    result = {
        "banner": banner,
        "sponsor": sponsor,
        "every": every,
        "monetag_script": script_url,
        "monetag_zone": zone_id,
        "has_monetag": bool(direct_link or zone_id or script_url),
        "ads": [],
    }

    # إعلانات bibliothèque (ال DB مصدر الحقيقة) حسب الفتحية للبوت هذا
    try:
        from control_center.ads.model import get_ad_library
        from control_center.ads.resolver import resolve_ads_for_bot
        lib = get_ad_library()
        ads = resolve_ads_for_bot(bot_id or "", "", library=lib)
        for ad in ads:
            if ad.snippet:
                result["ads"].append({
                    "slot": ad.slot,
                    "ad_id": ad.ad_id,
                    "snippet": ad.snippet,
                    "zone_id": ad.zone_id,
                    "name": ad.name,
                    "format": ad.format,
                    "enabled": bool(ad.enabled),
                })
    except Exception:
        pass

    return result


# ── الإحصائيات من قاعدة البيانات + الأحداث ──────────────────────────────────
def collect_stats() -> dict:
    """Collect usage stats from DB and events log."""
    stats = {"generated_at": datetime.now().isoformat(timespec="seconds"),
             "bots": {}, "total_users": 0, "events": {}}
    try:
        con = sqlite3.connect(DB)
        rows = con.execute(
            "SELECT bot_name, COUNT(DISTINCT user_id), SUM(usage_count) "
            "FROM users GROUP BY bot_name").fetchall()
        stats["active_bots"] = sorted(
            [{"bot": b, "users": int(u or 0), "uses": int(s or 0)}
             for b, u, s in rows if u], key=lambda x: -x["users"])[:20]
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
        # إحصاءات الإعلانات (Monetag + البوتات المتخذفات بواسطة النظام)
        ads_stats = {"impressions": 0, "clicks": 0, "ctr_percent": 0.0,
                     "active_ads": 0, "ad_bots": [], "per_bot": {}}
        con2 = sqlite3.connect(DB)
        try:
            rows = con2.execute(
                "SELECT bot_name, SUM(impressions) AS im, SUM(clicks) AS cl "
                "FROM monetag_ad_stats WHERE bot_name IS NOT NULL GROUP BY bot_name "
                "ORDER BY im DESC").fetchall()
            for bot, im, cl in rows:
                if not bot or bot == "nonexistent":
                    continue
                im_i, cl_i = int(im or 0), int(cl or 0)
                if im_i or cl_i:
                    ads_stats["impressions"] += im_i
                    ads_stats["clicks"] += cl_i
                    ads_stats["ad_bots"].append(bot)
                    ads_stats["per_bot"][bot] = {
                        "impressions": im_i,
                        "clicks": cl_i,
                        "ctr_percent": round((cl_i * 100.0) / max(im_i, 1), 2) if im_i else 0.0,
                    }
            if rows and sum(1 for r in rows if r[1]) > 0:
                ads_stats["ctr_percent"] = round(
                    (sum((r[2] or 0) for r in rows) / sum((r[1] or 0) for r in rows)) * 100, 2)
        except Exception:
            pass
        try:
            row = con2.execute(
                "SELECT COUNT(*) FROM ads WHERE enabled=1").fetchone()
            if row:
                ads_stats["active_ads"] = int(row[0] or 0)
        except Exception:
            pass
        stats["ads"] = ads_stats
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
    """Build landing page body for bots without interactive app."""
    emoji = app.get("emoji", "🤖")
    name = app.get("name", "")
    desc = app.get("description") or app.get("short_desc") or ""
    features = app.get("features") or []
    features_html = "".join(f"<li>{f}</li>" for f in features)
    body = f"""
<div class="card" style="text-align:center">
  <div style="font-size:64px">{emoji}</div>
  <h2 style="margin:10px 0">{name}</h2>
  <p style="color:var(--hint);line-height:2;font-size:14px">{desc}</p>
  {f'<ul class="feat-list" style="text-align:start">{features_html}</ul>' if features_html else ''}
  <p style="font-size:13.5px;line-height:2">هذا البوت يعمل بالكامل عبر المحادثة.<br>
  <b>النسخة التفاعلية قيد التطوير</b> — افتح البوت الآن واستمتع!</p>
  <button class="btn" onclick="location.href='https://t.me/{username}'">🤖 فتح البوت في تيليجرام</button>
</div>"""
    js = "Boda.track('app_open',{detail:'landing'});"
    return body, js


# ── بناء صفحة تطبيق واحد ─────────────────────────────────────────────────────
def render_app(app: dict, ads_cfg: dict, api_base: str, username: str) -> str:
    """Render a single app page."""
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
        group=app.get("tag", ""),
        page_url=f"{MINIAPPS_BASE}/{bot_id}/" if MINIAPPS_BASE else "")


# ── المتجر كتطبيق مصغّر ──────────────────────────────────────────────────────
STORE_CSS = """
.store-hero{position:relative;overflow:hidden;border-radius:20px;padding:20px 18px;
  background:linear-gradient(135deg,rgba(234,179,8,.22),rgba(249,115,22,.10) 45%,transparent 80%),
             var(--bd-surface);
  border:1px solid rgba(234,179,8,.32);margin-bottom:14px;}
.store-hero::after{content:"";position:absolute;inset:auto -30px -60px auto;width:160px;height:160px;
  background:radial-gradient(circle,rgba(234,179,8,.28),transparent 70%);pointer-events:none;}
.store-hero .kicker{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;font-weight:800;
  color:var(--bd-warn);background:rgba(234,179,8,.12);border:1px solid rgba(234,179,8,.35);
  padding:4px 10px;border-radius:999px;margin-bottom:8px;}
.store-hero h2{font-size:21px;line-height:1.5;margin:0 0 4px;}
.store-hero p{color:var(--bd-hint);font-size:12.5px;line-height:1.9;margin:0;}
.store-hero .stat-row{display:flex;gap:8px;margin-top:14px;}
.store-hero .stat{flex:1;background:rgba(0,0,0,.16);border:1px solid var(--bd-surface-2);
  border-radius:12px;padding:8px 4px;text-align:center;}
.store-hero .stat b{display:block;font-size:17px;line-height:1.3;}
.store-hero .stat span{font-size:10.5px;color:var(--bd-hint);}
.search-wrap{position:relative;margin:4px 0 12px;}
.search-wrap .ic{position:absolute;inset-inline-start:14px;top:50%;transform:translateY(-50%);
  font-size:15px;opacity:.7;pointer-events:none;}
.search-wrap input{width:100%;padding:13px 42px 13px 14px;border-radius:999px;
  border:1.5px solid var(--bd-surface-2);background:var(--bd-surface);color:var(--bd-text);
  font-size:14px;font-family:inherit;outline:none;transition:border-color .2s,box-shadow .2s;}
.search-wrap input:focus{border-color:var(--bd-brand);box-shadow:0 0 0 3px var(--bd-brand-soft);}
.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:18px 2px 9px;}
.section-head h3{font-size:15px;margin:0;}
.section-head span{font-size:11px;color:var(--bd-hint);}
.cats{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px;scrollbar-width:none;}
.cats::-webkit-scrollbar{display:none;}
.cat{flex-shrink:0;display:inline-flex;align-items:center;gap:6px;padding:8px 13px;border-radius:999px;
  font-size:12.5px;font-weight:700;cursor:pointer;background:var(--bd-surface);
  border:1.5px solid var(--bd-surface-2);color:var(--bd-text);
  transition:transform .12s,border-color .2s,background .2s;}
.cat:active{transform:scale(.96);}
.cat.active{background:var(--bd-brand);border-color:var(--bd-brand);color:#fff;}
.cat .n{font-size:10.5px;opacity:.75;}
.featured{display:flex;gap:10px;overflow-x:auto;padding:2px 2px 8px;
  scroll-snap-type:x mandatory;scrollbar-width:none;}
.featured::-webkit-scrollbar{display:none;}
.feat-card{flex:0 0 190px;scroll-snap-align:start;background:var(--bd-surface);
  border:1px solid var(--bd-surface-2);border-radius:16px;padding:13px;cursor:pointer;
  position:relative;overflow:hidden;transition:transform .15s,border-color .2s;}
.feat-card:active{transform:scale(.98);}
.feat-card::before{content:"";position:absolute;inset:0 auto auto 0;width:100%;height:3px;
  background:linear-gradient(90deg,var(--bd-warn),transparent 70%);opacity:.8;}
.feat-card .e{font-size:30px;line-height:1;margin-bottom:8px;}
.feat-card h4{font-size:13.5px;margin:0 0 4px;line-height:1.5;}
.feat-card p{font-size:11px;color:var(--bd-hint);line-height:1.7;margin:0;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.feat-card .go{margin-top:9px;font-size:11px;font-weight:800;color:var(--bd-link);}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:9px;}
.app-card{display:flex;flex-direction:column;gap:6px;background:var(--bd-surface);
  border:1px solid var(--bd-surface-2);border-radius:15px;padding:12px;cursor:pointer;
  transition:transform .15s,border-color .2s;position:relative;overflow:hidden;}
.app-card:active{transform:scale(.98);border-color:var(--bd-brand-line);}
.app-card .top{display:flex;align-items:center;justify-content:space-between;gap:6px;}
.app-card .ic{font-size:27px;width:44px;height:44px;display:grid;place-items:center;
  background:var(--bd-bg);border-radius:12px;flex-shrink:0;}
.app-card .cat-tag{font-size:9.5px;font-weight:800;color:var(--bd-hint);background:var(--bd-bg);
  border:1px solid var(--bd-surface-2);padding:2px 7px;border-radius:999px;white-space:nowrap;}
.app-card h3{font-size:13px;margin:0;line-height:1.5;}
.app-card p{font-size:11px;color:var(--bd-hint);line-height:1.65;margin:0;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.app-card .meta{font-size:10px;color:var(--bd-link);margin-top:auto;padding-top:4px;}
.badge-feat{position:absolute;inset-inline-end:10px;top:10px;font-size:9px;font-weight:800;
  color:#111;background:var(--bd-warn);padding:2px 7px;border-radius:999px;}
.empty{text-align:center;color:var(--bd-hint);padding:30px 10px;font-size:13px;}
.ads-bot{display:flex;flex-direction:column;gap:6px;background:var(--bd-surface);
  border:1.5px solid rgba(234,179,8,.4);border-radius:15px;padding:12px;cursor:pointer;
  transition:transform .15s,border-color .2s;}
.ads-bot:active{transform:scale(.98);}
.ads-bot .ic{font-size:26px;width:40px;height:40px;display:grid;place-items:center;
  background:var(--bd-bg);border-radius:12px;}
.ads-bot h3{font-size:13px;margin:6px 0 2px;line-height:1.5;}
.ads-bot p{font-size:10.5px;color:var(--bd-hint);line-height:1.6;margin:0;}
.stat.ctr{color:var(--bd-brand);font-weight:800;}
.ad-table{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-top:8px;}
.ad-table .ad-card{display:flex;flex-direction:column;gap:3px;background:var(--bd-surface);
  border:1.5px solid rgba(234,179,8,.35);border-radius:12px;padding:9px 10px;}
.ad-table .ad-card b{font-size:12.5px;line-height:1.4;}
.ad-table .ad-card span{font-size:10px;color:var(--bd-hint);}
.feat-card:hover{transform:scale(1.02);}
.app-card:hover{transform:scale(1.02);}
.sub-card{display:flex;align-items:center;gap:10px;background:var(--bd-surface);
  border:1px solid var(--bd-brand-line);border-radius:14px;padding:12px;margin:14px 0 0;}
.sub-card .ic{font-size:22px;flex:0 0 auto;}
.sub-card .tx{flex:1;min-width:0;}
.sub-card b{font-size:12px;display:block;margin-bottom:2px;}
.sub-card p{font-size:10.5px;color:var(--bd-hint);line-height:1.6;margin:0;}
.sub-card .btn{width:auto;min-height:34px;margin:0;padding:6px 12px;font-size:11px;flex:0 0 auto;}
.sub-card .x{background:none;border:none;color:var(--bd-hint);font-size:15px;cursor:pointer;padding:2px;}
.sheet .sheet-head{display:flex;gap:12px;align-items:center;margin-bottom:10px;}
.sheet .sheet-emoji{font-size:38px;width:58px;height:58px;display:grid;place-items:center;
  background:var(--bd-bg);border-radius:15px;flex-shrink:0;}
.sheet .sheet-head h3{font-size:17px;margin:0 0 2px;line-height:1.5;}
.sheet .sheet-head span{font-size:11px;color:var(--bd-hint);}
.sheet .sheet-desc{font-size:12.5px;line-height:1.95;color:var(--bd-text);margin:0 0 10px;}
.sheet .feat-list{list-style:none;padding:0;margin:0 0 12px;display:grid;gap:5px;}
.sheet .feat-list li{font-size:11.5px;line-height:1.7;color:var(--bd-hint);}
.sheet .feat-list li::before{content:"✓";color:var(--bd-ok);font-weight:800;margin-inline-end:6px;}
.sheet .sheet-stats{display:flex;gap:8px;margin-bottom:10px;}
.sheet .sheet-stats .s{flex:1;background:var(--bd-bg);border-radius:10px;padding:7px;text-align:center;}
.sheet .sheet-stats b{display:block;font-size:14px;}
.sheet .sheet-stats span{font-size:9.5px;color:var(--bd-hint);}
.sheet .sheet-actions{display:grid;gap:7px;}
.sheet .sheet-actions .btn{min-height:44px;font-size:13px;margin:0;}
.sheet .sheet-actions .row{display:grid;grid-template-columns:1fr 1fr;gap:7px;}
"""

STORE_JS = """
let APPS=[], CATS=[], stats={}, cat='all', q='';
let _searchTimer=0;
const byId=id=>APPS.find(a=>a.id===id);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>{n=+n||0;return n>=1000?(n/1000).toFixed(1)+'K':n;};
const CAT_ORDER=['daily','design','media','learn','fun','health','business'];

async function boot(){
  try{const r=await fetch('../data/stats.json');stats=await r.json();}catch(e){stats={};}
  try{const r=await fetch('../data/catalog.json');APPS=await r.json();}
  catch(e){APPS=window.__BODA_CATALOG__||[];}
  if(!Array.isArray(APPS))APPS=[];
  APPS.sort((a,b)=>(a.order||9999)-(b.order||9999));
  buildCats();render();
  const el=id=>document.getElementById(id);
  if(el('s-apps'))el('s-apps').textContent=APPS.length;
  if(el('s-users'))el('s-users').textContent=fmt(stats.total_users||0);
  const ads=stats.ads||{};
  if(el('s-ads'))el('s-ads').textContent=fmt((ads.ad_bots||[]).length);
  if(el('s-impressions'))el('s-impressions').textContent=fmt(ads.impressions||0);
  const ev=stats.events||{};
  if(el('s-opens'))el('s-opens').textContent=fmt(Object.entries(ev)
    .filter(([k])=>k.indexOf('app_open:')===0).reduce((s,x)=>s+(+x[1]||0),0));
  if(el('cat-hint'))el('cat-hint').textContent=CATS.length-1+' فئات';
  renderAds();
  renderAdsTable();
  const imp=ads.impressions||0, cl=ads.clicks||0;
  if(el('s-ctr'))el('s-ctr').textContent=imp?((cl*100/imp).toFixed(1)+'%'):'—';
  try{if(localStorage.getItem('boda_sub_dismiss')==='1')hideSub();}catch(e){}
}
function buildCats(){
  const map=new Map();
  APPS.forEach(a=>{
    const k=a.category_key||'daily';
    if(!map.has(k))map.set(k,{key:k,name:a.category||'أخرى',icon:a.category_icon||'📂',count:0});
    map.get(k).count++;
  });
  CATS=[{key:'all',name:'الكل',icon:'✨',count:APPS.length}]
    .concat(CAT_ORDER.filter(k=>map.has(k)).map(k=>map.get(k)));
  document.getElementById('cats').innerHTML=CATS.map(c=>
    '<span class="cat'+(c.key===cat?' active':'')+'" onclick="setCat(\\''+c.key+'\\',this)">'+
    c.icon+' '+esc(c.name)+' <span class="n">'+c.count+'</span></span>').join('');
}
function setCat(k,el){
  cat=k;
  document.querySelectorAll('.cat').forEach(x=>x.classList.remove('active'));
  if(el)el.classList.add('active');
  Boda.haptic('select');Boda.track('store_cat',{detail:k});
  render();
}
function renderFeatured(){
  const sec=document.getElementById('featured-sec'),box=document.getElementById('featured');
  if(!sec||!box)return;
  const list=APPS.filter(a=>a.featured).slice(0,8);
  if(!list.length||cat!=='all'||q){sec.style.display='none';return;}
  sec.style.display='';
  box.innerHTML=list.map(a=>
    '<div class="feat-card" onclick="openDetails(\\''+a.id+'\\')">'+
      '<div class="e">'+(a.emoji||'🤖')+'</div>'+
      '<h4>'+esc(a.name)+'</h4>'+
      '<p>'+esc(a.short_desc||a.description)+'</p>'+
      '<div class="go">عرض التفاصيل ←</div>'+
    '</div>').join('');
}
function fuzzy(q,s){
  if(!q)return true;
  const a=s.toLowerCase();
  if(a.indexOf(q)>=0)return true;
  const words=q.split(/\\s+/).filter(Boolean);
  return words.length>0 && words.every(w=>a.indexOf(w)>=0);
}
function render(){
  const query=q.trim().toLowerCase();
  const list=APPS.filter(a=>{
    const okCat=cat==='all'||a.category_key===cat;
    if(!okCat)return false;
    if(!query)return true;
    const hay=(a.name+' '+(a.short_desc||'')+' '+(a.description||'')+' '+
      (a.username||'')+' '+(a.features||[]).join(' ')).toLowerCase();
    return fuzzy(query,hay);
  });
  const title=document.getElementById('list-title');
  const count=document.getElementById('list-count');
  if(title)title.textContent=cat==='all'?'كل البوتات':((CATS.find(c=>c.key===cat)||{}).name||'البوتات');
  if(count)count.textContent=list.length+' بوت';
  const box=document.getElementById('list');
  if(!box)return;
  box.innerHTML=list.length?list.map(a=>{
    const st=(stats.bots||{})[a.id]||{};
    return '<div class="app-card" onclick="openDetails(\\''+a.id+'\\')">'+
      (a.featured?'<span class="badge-feat">مميز</span>':'')+
      '<div class="top"><div class="ic">'+(a.emoji||'🤖')+'</div>'+
      '<span class="cat-tag">'+(a.category_icon||'')+' '+esc(a.category||'')+'</span></div>'+
      '<h3>'+esc(a.name)+'</h3>'+
      '<p>'+esc(a.short_desc||a.description)+'</p>'+
      '<div class="meta">'+(st.users?('👥 '+fmt(st.users)+' مستخدم'):'✨ جديد')+
        (st.active_30d?(' · 🔥 '+fmt(st.active_30d)+' نشط'):'')+'</div>'+
    '</div>';
  }).join(''):'<div class="empty">🔍 لا توجد نتائج مطابقة</div>';
  renderFeatured();
}
function renderAds(){
  const box=document.getElementById('ads-list');
  const count=document.getElementById('ads-count');
  if(!box)return;
  const ids=(stats.ads&&stats.ads.ad_bots)||[];
  count.textContent=ids.length+' بوت';
  box.innerHTML=ids.length?ids.map(id=>{
    const a=byId(id);
    if(!a)return '';
    const st=(stats.bots||{})[id]||{};
    return '<div class="ads-bot" onclick="openTg(\\''+a.url+'\\')">'+
      '<div class="ic">'+(a.emoji||'📺')+'</div>'+
      '<h3>'+esc(a.name)+'</h3>'+
      '<p>'+(a.short_desc||a.description)+'<br>👥 '+(st.users?fmt(st.users)+' مستخدم':'')+'</p>'+
    '</div>';
  }).join(''):'<p style="color:var(--bd-hint);padding:20px 0;text-align:center;font-size:13px">📺 لا توجد بوتات تُجري الاعلانات بعد</p>';
}
function renderAdsTable(){
  const box=document.getElementById('ads-table');
  if(!box)return;
  const ids=(stats.ads&&stats.ads.ad_bots)||[];
  if(!ids.length){ box.innerHTML='<div class="empty">📺 لا توجد بوتات تُجري الاعلانات بعد</div>'; return; }
  box.innerHTML=ids.map(id=>{
    const a=byId(id);
    if(!a)return '';
    const st=(stats.bots||{})[id]||{};
    const adb=(stats.ads&&stats.ads.per_bot&&stats.ads.per_bot[id])||{impressions:0,clicks:0,ctr_percent:0};
    const ctr=adb.impressions?(adb.ctr_percent+'%'):'—';
    return '<div class="ad-card">'+
      '<b>'+(a.name||id)+'</b>'+
      '<span>👥 '+(st.users?fmt(st.users):0)+' · 🚀 '+(st.active_30d?fmt(st.active_30d):0)+' · CTR '+ctr+'</span>'+
    '</div>';
  }).join('');
}
function openDetails(id){
  const a=byId(id);if(!a)return;
  Boda.haptic('light');Boda.track('store_view_bot',{detail:id});
  const st=(stats.bots||{})[id]||{};
  const feats=(a.features||[]).map(f=>'<li>'+esc(f)+'</li>').join('');
  const username=String(a.username||'').replace(/^@/,'');
  document.getElementById('sheetBody').innerHTML=
    '<div class="grabber"></div>'+
    '<div class="sheet-head"><div class="sheet-emoji">'+(a.emoji||'🤖')+'</div>'+
      '<div><h3>'+esc(a.name)+'</h3><span>'+(a.category_icon||'')+' '+esc(a.category||'')+
      (username?' · @'+esc(username):'')+'</span></div></div>'+
    '<p class="sheet-desc">'+esc(a.description||a.short_desc)+'</p>'+
    (feats?'<ul class="feat-list">'+feats+'</ul>':'')+
    '<div class="sheet-stats">'+
      '<div class="s"><b>'+(st.users?fmt(st.users):'—')+'</b><span>مستخدم</span></div>'+
      '<div class="s"><b>'+(st.active_30d?fmt(st.active_30d):'—')+'</b><span>نشط شهرياً</span></div>'+
      '<div class="s"><b>'+(a.has_app?'✓':'—')+'</b><span>تطبيق</span></div>'+
    '</div>'+
    '<div class="sheet-actions">'+
      '<button class="btn" onclick="openTg(\\''+a.url+'\\')">🚀 افتح البوت في تيليجرام</button>'+
      (a.has_app?'<a class="btn secondary" href="../'+a.web+'">📱 جرّب التطبيق المصغّر</a>':'')+
      '<div class="row">'+
        '<button class="btn ghost" onclick="shareApp(\\''+a.id+'\\')">📤 مشاركة</button>'+
        '<button class="btn ghost" onclick="closeSheet()">✕ إغلاق</button>'+
      '</div>'+
    '</div>';
  document.getElementById('sheet').classList.add('show');
  document.getElementById('sheetBody').classList.add('show');
}
function closeSheet(){
  document.getElementById('sheet').classList.remove('show');
  document.getElementById('sheetBody').classList.remove('show');
}
function shareApp(id){
  const a=byId(id);if(!a)return;
  const feats=(a.features||[]).slice(0,2).map(f=>' - '+f).join(' | ');
  const text='🚀 جرّب '+a.name+' — '+(a.short_desc||'')+' | '+feats+' | 🔗 t.me/'+String(a.username||'').replace(/^@/,'');
  Boda.share(text,a.url);
}
function openTg(url){
  Boda.haptic('light');
  try{if(Boda.tg&&Boda.tg.openTelegramLink)Boda.tg.openTelegramLink(url);else location.href=url;}
  catch(e){location.href=url;}
}
function dismissSub(){
  try{localStorage.setItem('boda_sub_dismiss','1');}catch(e){}
  hideSub();
}
function hideSub(){const el=document.getElementById('subCard');if(el)el.style.display='none';}

document.addEventListener('DOMContentLoaded',function(){
  const input=document.querySelector('.search-wrap input');
  if(input)input.addEventListener('input',function(e){
    q=e.target.value.trim();
    clearTimeout(_searchTimer);
    _searchTimer=setTimeout(render,120);
  });
});
boot();
"""


def _catalog_entry(app: dict) -> dict:
    """بطاقة بوت واحدة داخل catalog.json — بدون بوت المتجر."""
    bot_id = app["id"]
    app_def = APPS.get(bot_id) or {}
    return {
        "id": bot_id,
        "emoji": app.get("emoji", "🤖"),
        "name": app.get("name", ""),
        "short_desc": app.get("short_desc", ""),
        "description": app.get("description", ""),
        "features": app.get("features") or [],
        "tag": app.get("tag", "أخرى"),
        "category": app.get("category", ""),
        "category_key": app.get("category_key", "daily"),
        "category_icon": app.get("category_icon", ""),
        "username": app.get("username", ""),
        "url": app.get("url", STORE_URL),
        "web": f"{bot_id}/",
        "featured": bool(app.get("featured")),
        "order": int(app.get("order", 9999) or 9999),
        "added_date": app.get("added_date", ""),
        "hidden": bool(app.get("hidden")),
        "has_app": bool(app_def.get("interactive")),
    }


def build_catalog(apps: list) -> list:
    """كتالوج المتجر: 33 بوتاً فقط — بوت المتجر مستبعد."""
    return [_catalog_entry(a) for a in visible_bots(apps)]


def render_store(catalog: list, ads_cfg: dict, api_base: str) -> str:
    """Render the store mini-app page."""
    cat_count = len({a.get("category_key") for a in catalog if a.get("category_key")})
    body = f"""
<link rel="preload" as="fetch" href="../data/catalog.json">
<link rel="preload" as="fetch" href="../data/stats.json">
<div class="store-hero">
  <div class="kicker">✨ منصة بودة</div>
  <h2>كل أدواتك الذكية… في مكان واحد</h2>
  <p>{len(catalog)} بوتاً وتطبيقاً مصغّراً في {cat_count} فئات — مرتبة، سريعة، وبدون إعلانات.</p>
  <div class="stat-row">
    <div class="stat"><b id="s-apps">—</b><span>بوت</span></div>
    <div class="stat"><b id="s-users">—</b><span>مستخدم</span></div>
    <div class="stat"><b id="s-ads">—</b><span>بوت اعلان</span></div>
    <div class="stat"><b id="s-impressions">—</b><span>اعرضات</span></div>
    <div class="stat ctr"><b id="s-ctr">—</b><span>CTR</span></div>
  </div>
</div>
<div class="search-wrap">
  <span class="ic">🔍</span>
  <input type="search" placeholder="ابحث بالاسم أو الوصف أو الميزة..." aria-label="بحث في المتجر">
</div>
<div id="featured-sec">
  <div class="section-head"><h3>⭐ بوتات مميزة</h3><span>اختيارات فريق بودة</span></div>
  <div class="featured" id="featured"></div>
</div>
<div id="ads-sec">
  <div class="section-head"><h3>📺 بوتات الاعلانات</h3><span id="ads-count"></span></div>
  <div class="grid" id="ads-list"></div>
  <div class="ad-table" id="ads-table"></div>
</div>
<div class="section-head"><h3>📂 تصفح حسب الفئة</h3><span id="cat-hint">—</span></div>
<div class="cats" id="cats"></div>
<div class="section-head"><h3 id="list-title">كل البوتات</h3><span id="list-count"></span></div>
<div id="list" class="grid"></div>
<div class="sub-card" id="subCard">
  <div class="ic">🔐</div>
  <div class="tx"><b>الوصول الكامل عبر الاشتراك</b>
    <p>اشترك في قناتي بودة وعبده، ثم فعّل الاشتراك من بوت المتجر.</p></div>
  <button class="btn" onclick="openTg('https://t.me/BodaStoreeBot?start=verify')">تحقق</button>
  <button class="x" onclick="dismissSub()" aria-label="إغلاق">×</button>
</div>
<div class="sheet-backdrop" id="sheet" onclick="closeSheet()">
  <div class="sheet" id="sheetBody" onclick="event.stopPropagation()"></div>
</div>"""
    catalog_json = json.dumps(catalog, ensure_ascii=False)
    return build_html(
        bot_id="store", emoji="🏪", title="متجر تطبيقات بودة",
        subtitle=f"{len(catalog)} بوتاً وتطبيقاً في {cat_count} فئات — بدون إعلانات",
        body_html=body, app_js=STORE_JS, app_css=STORE_CSS,
        api_base=api_base,
        ads_cfg={"banner": None, "sponsor": None, "every": 999},
        share_url=STORE_URL, group="متجر 🏪",
        page_url=f"{MINIAPPS_BASE}/store/" if MINIAPPS_BASE else "").replace(
        "window.__BODA_BOT_ID__   = \"store\";",
        "window.__BODA_BOT_ID__   = \"store\";\nwindow.__BODA_CATALOG__ = "
        + catalog_json + ";")


def write_seo_files(out_dir: Path, apps: list) -> None:
    """Generate sitemap.xml and robots.txt."""
    """توليد sitemap.xml و robots.txt لفهرسة أفضل في محركات البحث."""
    from xml.sax.saxutils import escape

    today = datetime.now().strftime("%Y-%m-%d")
    urls = [(f"{PAGES_BASE}/", "1.0", "daily"),
            (f"{PAGES_BASE}/store/", "0.9", "daily")]
    for a in apps:
        if a.get("id") and not a.get("hidden") and a["id"] != "store":
            urls.append((f"{PAGES_BASE}/{a['id']}/", "0.8", "weekly"))

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, prio, freq in urls:
        sitemap.append("  <url>")
        sitemap.append(f"    <loc>{escape(loc)}</loc>")
        sitemap.append(f"    <lastmod>{today}</lastmod>")
        sitemap.append(f"    <changefreq>{freq}</changefreq>")
        sitemap.append(f"    <priority>{prio}</priority>")
        sitemap.append("  </url>")
    sitemap.append("</urlset>")
    (out_dir / "sitemap.xml").write_text("\n".join(sitemap), encoding="utf-8")

    robots = ("User-agent: *\nAllow: /\n\n"
              f"Sitemap: {PAGES_BASE}/sitemap.xml\n")
    (out_dir / "robots.txt").write_text(robots, encoding="utf-8")


def main():
    """Main build function."""
    out_dir = ROOT / "webroot"
    api_base = os.getenv("BODA_API_BASE", "").strip().rstrip("/")
    ads_cfg = build_ads_cfg()

    try:
        apps = json.loads(REG.read_text(encoding="utf-8"))
    except Exception:
        print("❌ تعذر قراءة bots_registry.json")
        return 1

    # Marker-aware rebuild (D7): never wipe the whole webroot — preserve any
    # file or directory that carries ad markers or is not managed by us.
    # We only remove the paths this generator owns, then regenerate them.
    if out_dir.exists():
        for managed in ("data", "store", "index.html", "sitemap.xml",
                        "robots.txt", ".nojekyll"):
            target = out_dir / managed
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink(missing_ok=True)
        # إعادة إنشاء مجلدات البوتات مع الحفاظ على علامات الإعلانات والنسخ الاحتياطية (Carry-over)
        _preserved_markers = {}
        app_ids = {a["id"] for a in apps if a.get("id")}
        for child in list(out_dir.iterdir()):
            if child.is_dir() and child.name not in ("data", "store", "assets", "dashboard"):
                _old = child / "index.html"
                if _old.exists():
                    try:
                        from control_center.ads.injector import list_blocks as _lb
                        import re as _re
                        _old_text = _old.read_text(encoding="utf-8")
                        _carried = []
                        for _blk in _lb(_old_text):
                            _m = _re.search(
                                r"<!-- AD:BEGIN slot=" + _re.escape(_blk["slot"]) +
                                r" id=" + _re.escape(_blk["ad_id"]) + r" -->(.*?)"
                                r"<!-- AD:END slot=" + _re.escape(_blk["slot"]) + r" -->",
                                _old_text, _re.DOTALL)
                            if _m:
                                _carried.append((_blk["slot"], _blk["ad_id"], _m.group(1).strip()))
                        if _carried:
                            _preserved_markers[child.name] = _carried
                    except Exception:
                        pass
                if child.name not in app_ids:
                    shutil.rmtree(child, ignore_errors=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)

    # catalog.json — مصدر المتجر (33 بوتاً، بوت المتجر مستبعد)
    catalog = build_catalog(apps)
    (out_dir / "data" / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")

    # stats.json — من قاعدة البيانات
    stats = collect_stats()
    (out_dir / "data" / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    # كل تطبيق — بوت المتجر له صفحته الخاصة أدناه ولا يُولَّد داخل نفسه
    n_interactive = 0
    for app in apps:
        if not app.get("id") or app["id"] == "store":
            continue
        bid = app["id"]
        username = (app.get("username") or "").lstrip("@") or "BodaStoreeBot"
        app_ads = build_ads_cfg(bid)
        html = render_app(app, app_ads, api_base, username)
        if bid in APPS and APPS[bid].get("interactive"):
            n_interactive += 1
        d = out_dir / bid
        d.mkdir(exist_ok=True)
        # مرحلة 2: حقن علامات الإعلانات
        # 1. العلامات المحفوظة من الملف السابق للبوت
        _blocks = list(_preserved_markers.get(bid, []))
        _seen_slots = {b[0] for b in _blocks}
        # 2. علامات مكتبة الإعلانات (DB) للمسارات التي لم تُحجز
        try:
            from control_center.ads.model import get_ad_library
            from control_center.ads.resolver import resolve_ads_for_bot
            lib = get_ad_library()
            category = app.get("tag", "")
            ads = resolve_ads_for_bot(bid, category, library=lib)
            for ad in ads:
                if ad.snippet and ad.slot not in _seen_slots:
                    _blocks.append((ad.slot, ad.ad_id, ad.snippet))
                    _seen_slots.add(ad.slot)
        except Exception:
            pass
        if _blocks:
            try:
                from control_center.ads.injector import inject_markers as _inj
                html = _inj(html, _blocks)
            except Exception:
                pass
        (d / "index.html").write_text(html, encoding="utf-8")

    # المتجر
    (out_dir / "store").mkdir(exist_ok=True)
    (out_dir / "store" / "index.html").write_text(
        render_store(catalog, ads_cfg, api_base), encoding="utf-8")

    # لوحة التحليلات (Control Center dashboard) — صفحة مستقلة
    try:
        from dashboard_template import build_dashboard
        (out_dir / "dashboard").mkdir(exist_ok=True)
        (out_dir / "dashboard" / "index.html").write_text(
            build_dashboard(api_base), encoding="utf-8")
    except Exception as e:
        print(f"⚠️  تعذر توليد لوحة التحليلات: {e}")

    # index الرئيسي → المتجر
    (out_dir / "index.html").write_text(
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=store/"></head>'
        '<body>جاري فتح المتجر...</body></html>', encoding="utf-8")

    # .nojekyll لـ GitHub Pages
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    # SEO: sitemap.xml + robots.txt
    write_seo_files(out_dir, apps)

    print(f"✅ تم البناء في {out_dir.name}/")
    print(f"   📱 تطبيقات تفاعلية: {n_interactive}")
    print(f"   🏪 بوتات في المتجر: {len(catalog)}")
    print(f"   📄 صفحات بوتات: {sum(1 for a in apps if a.get('id') != 'store' and not a.get('hidden'))}")
    print(f"   🔍 خريطة الموقع: {1 + sum(1 for a in apps if a.get('id') != 'store' and not a.get('hidden'))} رابطًا")
    print(f"   👥 إجمالي المستخدمين المكتشفين: {stats['total_users']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
