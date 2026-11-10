# -*- coding: utf-8 -*-
"""
tools/dashboard_template.py — مولّد صفحة لوحة التحليلات (Dashboard)

ينتج صفحة HTML مستقلة (بلا أي اعتماد خارجي) تعرض مؤشرات النظام:
المستخدمون، النشطون (DAU/WAU/MAU)، قمع بوابة الشبكة، أعلى البوتات،
وإحصائيات الإعلانات.

تُحقن في ``webroot/dashboard/index.html`` بواسطة ``tools/build_mini_apps.py``
وتُخدم من ``api_server.py`` على المسار ``/dashboard``.

مفتاح تخزين الـ API محلياً: ``boda_api_key`` (localStorage).
"""
from __future__ import annotations

import json


def build_dashboard(api_base: str = "") -> str:
    """Return the full HTML of the analytics dashboard."""
    api = json.dumps(api_base or "")
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="dark light">
<title>📊 لوحة التحليلات — Boda Bot System</title>
<style>
  :root {{
    --bg:#0f1720; --surface:#16212e; --surface2:#1d2937; --text:#e6edf3;
    --hint:#93a4b8; --accent:#4d94ff; --ok:#2ecc71; --warn:#f5a623; --err:#ff5c5c;
    --border:rgba(255,255,255,.09);
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; padding:16px; background:var(--bg); color:var(--text);
    font-family:"Segoe UI",Tahoma,system-ui,-apple-system,sans-serif;
    font-size:14px; line-height:1.7;
  }}
  .wrap {{ max-width:1180px; margin:0 auto; }}
  header {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center;
           justify-content:space-between; margin-bottom:18px; }}
  h1 {{ font-size:20px; margin:0; }}
  .sub {{ color:var(--hint); font-size:12.5px; }}
  .bar {{ display:flex; gap:8px; flex-wrap:wrap; }}
  input, button {{
    background:var(--surface); color:var(--text); border:1px solid var(--border);
    border-radius:10px; padding:9px 12px; font-family:inherit; font-size:13px;
  }}
  input {{ min-width:230px; }}
  button {{ cursor:pointer; }}
  button.primary {{ background:var(--accent); color:#fff; border-color:transparent; }}
  button:hover {{ filter:brightness(1.12); }}
  .cards {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(168px,1fr));
           margin-bottom:18px; }}
  .card {{ background:var(--surface); border:1px solid var(--border); border-radius:14px;
          padding:14px 16px; }}
  .card .v {{ font-size:26px; font-weight:700; }}
  .card .l {{ color:var(--hint); font-size:12px; }}
  .card .t {{ color:var(--accent); font-size:11px; }}
  .grid {{ display:grid; gap:14px; grid-template-columns:1.4fr 1fr; }}
  @media (max-width:860px) {{ .grid {{ grid-template-columns:1fr; }} }}
  .panel {{ background:var(--surface); border:1px solid var(--border);
           border-radius:14px; padding:14px 16px; margin-bottom:14px; }}
  .panel h2 {{ font-size:14px; margin:0 0 10px; color:var(--hint);
               font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:right; padding:7px 8px; border-bottom:1px solid var(--border); }}
  th {{ color:var(--hint); font-weight:600; font-size:12px; }}
  .bar-track {{ background:var(--surface2); height:8px; border-radius:6px;
                overflow:hidden; min-width:80px; }}
  .bar-fill {{ height:100%; background:linear-gradient(90deg,var(--accent),#7db8ff); }}
  .row {{ display:flex; align-items:center; gap:8px; }}
  .muted {{ color:var(--hint); }}
  .err {{ color:var(--err); }}
  .ok {{ color:var(--ok); }}
  .foot {{ color:var(--hint); font-size:11.5px; text-align:center; margin-top:20px; }}
  .note {{ background:var(--surface2); border:1px solid var(--border);
           border-radius:10px; padding:10px 12px; font-size:12.5px;
           color:var(--hint); margin-bottom:14px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>📊 لوحة التحليلات</h1>
      <div class="sub">نظرة حية على نمو البوتات — Boda Bot System</div>
    </div>
    <div class="bar">
      <input id="key" type="password" placeholder="مفتاح API (X-API-Key) — اختياري محلياً">
      <button id="save" class="primary">🔑 حفظ المفتاح</button>
      <button id="refresh">🔄 تحديث</button>
    </div>
  </header>

  <div class="note">
    البيانات تُقرأ من <code>/api/overview</code> و<code>/api/stats</code>.
    من خارج جهازك أدخل مفتاح <code>API_SERVER_KEY</code> في الحقل أعلاه
    (يُحفظ محلياً في المتصفح تحت المفتاح <code>boda_api_key</code>).
  </div>

  <div class="cards" id="cards"></div>

  <div class="grid">
    <div>
      <div class="panel">
        <h2>أعلى البوتات (عدد المستخدمين)</h2>
        <div id="topbots"><span class="muted">جارٍ التحميل…</span></div>
      </div>
      <div class="panel">
        <h2>قمع بوابة الشبكة</h2>
        <div id="funnel"><span class="muted">جارٍ التحميل…</span></div>
      </div>
    </div>
    <div>
      <div class="panel">
        <h2>نشاط المستخدمين</h2>
        <div id="activity"><span class="muted">جارٍ التحميل…</span></div>
      </div>
      <div class="panel">
        <h2>إحصائيات الإعلانات</h2>
        <div id="ads"><span class="muted">جارٍ التحميل…</span></div>
      </div>
    </div>
  </div>

  <div class="foot">Generated by tools/build_mini_apps.py · Boda Bot System</div>
</div>

<script>
(function () {{
  const API_BASE = {api};
  const KEY_STORE = 'boda_api_key';

  function apiKey() {{
    try {{ return localStorage.getItem(KEY_STORE) || ''; }} catch (e) {{ return ''; }}
  }}
  function headers() {{
    const h = {{ 'Content-Type': 'application/json' }};
    const k = apiKey();
    if (k) h['X-API-Key'] = k;
    return h;
  }}
  async function get(path) {{
    const res = await fetch(API_BASE + path, {{ headers: headers() }});
    if (!res.ok) throw new Error(path + ' → HTTP ' + res.status);
    return res.json();
  }}

  function esc(s) {{
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({{
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
  }}

  function card(v, l, t) {{
    return '<div class="card"><div class="v">' + esc(v) + '</div>' +
           '<div class="l">' + esc(l) + '</div>' +
           (t ? '<div class="t">' + esc(t) + '</div>' : '') + '</div>';
  }}

  function renderOverview(ov) {{
    if (!ov || ov.error) {{
      document.getElementById('cards').innerHTML =
        '<div class="card"><div class="v err">—</div><div class="l">' +
        esc((ov && ov.error) || 'تعذر تحميل البيانات') + '</div></div>';
      return;
    }}
    const u = ov.users || {{}};
    const f = ov.funnel || {{}};
    document.getElementById('cards').innerHTML = [
      card(u.total || 0, 'إجمالي المستخدمين'),
      card(u.dau || 0, 'نشط اليوم (DAU)'),
      card(u.wau || 0, 'نشط الأسبوع (WAU)'),
      card(u.mau || 0, 'نشط الشهر (MAU)'),
      card((ov.retention_dau_mau_percent || 0) + '%', 'الالتصاق DAU/MAU'),
      card((ov.referrals || {{}}).total || 0, 'الإحالات')
    ].join('');

    const tops = ov.top_bots || [];
    const max = tops.reduce((m, b) => Math.max(m, b.users || 0), 0) || 1;
    document.getElementById('topbots').innerHTML = tops.length ? (
      '<table><thead><tr><th>البوت</th><th>المستخدمون</th><th>نشط 30 يوم</th><th></th></tr></thead><tbody>' +
      tops.map(b => '<tr><td>' + esc(b.bot_name) + '</td><td>' + (b.users || 0) +
        '</td><td>' + (b.active_30d || 0) + '</td><td><div class="row">' +
        '<div class="bar-track" style="flex:1"><div class="bar-fill" style="width:' +
        Math.round((b.users || 0) * 100 / max) + '%"></div></div></div></td></tr>').join('') +
      '</tbody></table>'
    ) : '<span class="muted">لا توجد بيانات بعد</span>';

    const steps = [
      ['مستخدمون', f.users || 0, 100],
      ['معيَّنون على الشبكة', f.assigned || 0, f.assigned_percent || 0],
      ['فعّلوا الشبكة', f.activated || 0, f.activated_percent || 0]
    ];
    document.getElementById('funnel').innerHTML = steps.map(s =>
      '<div style="margin-bottom:8px"><div class="row" style="justify-content:space-between">' +
      '<span>' + esc(s[0]) + '</span><b>' + s[1] + '</b></div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:' +
      (typeof s[2] === 'number' ? s[2] : 0) + '%"></div></div></div>').join('');

    document.getElementById('activity').innerHTML =
      '<table><tbody>' +
      '<tr><td class="muted">DAU</td><td><b>' + (u.dau || 0) + '</b></td></tr>' +
      '<tr><td class="muted">WAU</td><td><b>' + (u.wau || 0) + '</b></td></tr>' +
      '<tr><td class="muted">MAU</td><td><b>' + (u.mau || 0) + '</b></td></tr>' +
      '<tr><td class="muted">مستخدمون فريدون</td><td><b>' + (u.distinct_users || 0) + '</b></td></tr>' +
      '</tbody></table>';
  }}

  function renderStats(st) {{
    if (!st || st.error) {{
      document.getElementById('ads').innerHTML =
        '<span class="muted">تعذر تحميل الإحصائيات</span>';
      return;
    }}
    const rows = st.bots_stats || [];
    document.getElementById('ads').innerHTML = rows.length ? (
      '<table><thead><tr><th>البوت</th><th>رسائل</th><th>أخطاء</th></tr></thead><tbody>' +
      rows.slice(0, 12).map(r =>
        '<tr><td>' + esc(r.bot_name) + '</td><td>' + (r.total_messages || 0) +
        '</td><td>' + (r.total_errors || 0) + '</td></tr>').join('') +
      '</tbody></table>'
    ) : '<span class="muted">لا توجد بيانات استخدام بعد</span>';
  }}

  async function refresh() {{
    try {{
      const [ov, st] = await Promise.all([get('/api/overview'), get('/api/stats')]);
      renderOverview(ov);
      renderStats(st);
    }} catch (e) {{
      document.getElementById('cards').innerHTML =
        '<div class="card"><div class="v err">—</div><div class="l">' +
        esc(e.message) + '</div></div>';
    }}
  }}

  document.getElementById('save').addEventListener('click', function () {{
    try {{ localStorage.setItem(KEY_STORE, document.getElementById('key').value); }} catch (e) {{}}
    refresh();
  }});
  document.getElementById('refresh').addEventListener('click', refresh);
  try {{ document.getElementById('key').value = apiKey(); }} catch (e) {{}}
  refresh();
  setInterval(refresh, 60000);
}})();
</script>
</body>
</html>"""


if __name__ == "__main__":
    print(build_dashboard())
