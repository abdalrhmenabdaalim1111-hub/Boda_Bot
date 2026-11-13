# -*- coding: utf-8 -*-
"""
tools/ds_components.py — مكتبة مكونات Boda + الحركات

كل المكونات تعتمد Tokens من ``ds_tokens.py`` فقط، وتعمل فاتح/داكن.
الأسماء القديمة (card/btn/chip/result) محفوظة ومحسّنة حتى لا تنكسر
التطبيقات الحالية، مع مكونات جديدة (list/stat/segmented/sheet/skeleton).
"""

COMPONENTS_CSS = """
/* ══ بطاقات ══ */
.card{
  position:relative;
  background:var(--bd-surface);
  border:1px solid var(--bd-surface-2);
  border-radius:var(--bd-r-md);
  padding:var(--bd-sp-4);
  margin-bottom:var(--bd-sp-3);
  box-shadow:var(--bd-shadow-1);
}
.card::before{
  content:""; position:absolute; inset:0 auto auto 0;
  width:100%; height:3px; border-radius:var(--bd-r-md) var(--bd-r-md) 0 0;
  background:linear-gradient(90deg, var(--bd-brand), transparent 65%);
  opacity:.75;
}
.card h2,.card-title{ font-size:var(--bd-fs-md); font-weight:800;
  margin-bottom:var(--bd-sp-3); }
.card-sub{ color:var(--bd-hint); font-size:var(--bd-fs-sm); font-weight:400;
  margin:-8px 0 12px; line-height:1.8; }

/* ══ حقول الإدخال ══ */
.field{ margin-bottom:var(--bd-sp-3); }
.field > label,label{ display:block; font-size:var(--bd-fs-sm); font-weight:700;
  color:var(--bd-hint); margin:0 0 6px 2px; }
input[type=text],input[type=number],input[type=date],input[type=tel],
input[type=url],input[type=search],textarea,select{
  width:100%; padding:12px 14px;
  border:1.5px solid var(--bd-surface-2);
  border-radius:var(--bd-r-sm);
  background:var(--bd-bg); color:var(--bd-text);
  font-size:var(--bd-fs-md); font-family:inherit; outline:none;
  transition:border-color var(--bd-dur-2) var(--bd-ease),
             box-shadow var(--bd-dur-2) var(--bd-ease);
  -webkit-appearance:none; appearance:none;
}
input:focus,textarea:focus,select:focus{
  border-color:var(--bd-brand);
  box-shadow:0 0 0 3px var(--bd-brand-soft);
}
input::placeholder,textarea::placeholder{ color:var(--bd-hint); opacity:.7; }
textarea{ min-height:92px; resize:vertical; }
.field .help{ font-size:var(--bd-fs-xs); color:var(--bd-hint); margin-top:5px; }
.field.invalid input,.field.invalid textarea{ border-color:var(--bd-danger); }

/* ══ أزرار ══ */
.btn{
  display:flex; align-items:center; justify-content:center; gap:8px;
  width:100%; min-height:50px; border:none; cursor:pointer;
  background:linear-gradient(180deg, var(--bd-btn), color-mix(in srgb, var(--bd-btn) 82%, #000));
  color:var(--bd-btn-text);
  padding:13px 16px; border-radius:var(--bd-r-sm);
  font-size:15.5px; font-weight:800; font-family:inherit;
  margin-top:var(--bd-sp-3);
  box-shadow:0 6px 18px color-mix(in srgb, var(--bd-btn) 32%, transparent);
  transition:transform var(--bd-dur-1) var(--bd-ease),
             opacity var(--bd-dur-2) var(--bd-ease),
             filter var(--bd-dur-2) var(--bd-ease);
  touch-action:manipulation;
}
.btn:active{ transform:scale(.975); filter:brightness(.95); }
.btn:focus-visible{ outline:3px solid var(--bd-brand-soft); outline-offset:2px; }
.btn.secondary{ background:transparent; color:var(--bd-brand);
  border:1.5px solid var(--bd-brand-line); box-shadow:none; }
.btn.ghost{ background:var(--bd-surface-2); color:var(--bd-text); box-shadow:none; }
.btn.danger{ background:var(--bd-danger); box-shadow:none; }
.btn.small{ min-height:40px; padding:8px 14px; font-size:13.5px;
  width:auto; margin-top:0; border-radius:var(--bd-r-pill); }
.btn:disabled{ opacity:.5; cursor:not-allowed; transform:none; }
.btn.loading{ pointer-events:none; opacity:.8; }
.btn.loading::before{
  content:""; width:16px; height:16px; border-radius:50%;
  border:2px solid currentColor; border-top-color:transparent;
  animation:bd-spin .7s linear infinite;
}
.icon-btn{
  display:inline-grid; place-items:center; width:38px; height:38px;
  border:none; border-radius:50%; background:var(--bd-surface-2);
  color:var(--bd-text); cursor:pointer; font-size:17px;
}

/* ══ اختيارات سريعة ══ */
.chips{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.chip{
  padding:8px 14px; border-radius:var(--bd-r-pill);
  font-size:13.5px; font-weight:700; cursor:pointer; user-select:none;
  background:var(--bd-bg); color:var(--bd-text);
  border:1.5px solid var(--bd-surface-2);
  transition:background var(--bd-dur-1), color var(--bd-dur-1),
             border-color var(--bd-dur-1), transform var(--bd-dur-1);
}
.chip:active{ transform:scale(.96); }
.chip.active{ background:var(--bd-brand); color:#fff;
  border-color:var(--bd-brand); }

/* ══ تبويبات مقسّمة ══ */
.segmented{
  display:flex; gap:4px; padding:4px; border-radius:var(--bd-r-sm);
  background:var(--bd-bg); border:1px solid var(--bd-surface-2);
  margin-bottom:var(--bd-sp-3);
}
.segmented button{
  flex:1; padding:8px 10px; border:none; border-radius:calc(var(--bd-r-sm) - 3px);
  background:transparent; color:var(--bd-hint);
  font-family:inherit; font-weight:700; font-size:13px; cursor:pointer;
  transition:background var(--bd-dur-2), color var(--bd-dur-2);
}
.segmented button.active{ background:var(--bd-surface); color:var(--bd-text);
  box-shadow:var(--bd-shadow-1); }

/* ══ قوائم ══ */
.list{ display:flex; flex-direction:column; gap:8px; }
.list-item{
  display:flex; align-items:center; gap:12px;
  padding:12px 14px; border-radius:var(--bd-r-sm);
  background:var(--bd-surface); border:1px solid var(--bd-surface-2);
  transition:transform var(--bd-dur-1), border-color var(--bd-dur-2);
}
.list-item:active{ transform:scale(.99); border-color:var(--bd-brand-line); }
.list-item .li-icon{
  display:grid; place-items:center; flex:0 0 auto;
  width:44px; height:44px; border-radius:13px; font-size:21px;
  background:var(--bd-brand-soft);
}
.list-item .li-body{ flex:1; min-width:0; }
.list-item .li-body b{ display:block; font-size:14px; }
.list-item .li-body span{ display:block; color:var(--bd-hint);
  font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.list-item .li-chevron{ color:var(--bd-hint); font-size:20px; }

/* ══ إحصائيات ══ */
.stat-grid{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px;
  margin-top:12px; }
.stat{
  background:var(--bd-bg); border:1px solid var(--bd-surface-2);
  border-radius:var(--bd-r-sm); padding:10px 8px; text-align:center;
}
.stat b{ display:block; font-size:18px; font-weight:800; }
.stat span{ font-size:11px; color:var(--bd-hint); }
.stat.accent b{ color:var(--bd-brand); }

/* ══ شعارات/وسوم ══ */
.badge{
  display:inline-flex; align-items:center; gap:4px;
  padding:2px 9px; border-radius:var(--bd-r-pill);
  font-size:10.5px; font-weight:800;
  background:var(--bd-brand-soft); color:var(--bd-brand);
  vertical-align:middle;
}
.badge.ok{ background:rgba(63,185,80,.14); color:var(--bd-ok); }
.badge.warn{ background:rgba(227,163,61,.16); color:var(--bd-warn); }
.badge.muted{ background:var(--bd-surface-2); color:var(--bd-hint); }

/* ══ شريط تقدم ══ */
.progress{ height:8px; border-radius:var(--bd-r-pill);
  background:var(--bd-surface-2); overflow:hidden; }
.progress > i{ display:block; height:100%; width:0;
  border-radius:inherit; background:linear-gradient(90deg, var(--bd-brand), var(--bd-brand-2));
  transition:width var(--bd-dur-3) var(--bd-ease); }
.progress.indeterminate > i{ width:38%; animation:bd-indeterminate 1.2s var(--bd-ease) infinite; }

/* ══ هياكل تحميل ══ */
.skeleton{
  border-radius:var(--bd-r-sm); min-height:16px;
  background:linear-gradient(100deg, var(--bd-surface-2) 30%,
             var(--bd-surface) 50%, var(--bd-surface-2) 70%);
  background-size:220% 100%;
  animation:bd-shimmer 1.35s linear infinite;
}
.skeleton.lines > *{ height:12px; margin-bottom:8px; }

/* ══ حالة فراغ ══ */
.empty{ text-align:center; padding:26px 16px; color:var(--bd-hint); }
.empty .big{ font-size:38px; margin-bottom:6px; }
.empty b{ display:block; color:var(--bd-text); margin-bottom:3px; }

/* ══ نتيجة ══ */
.result{
  margin-top:14px; padding:16px; border-radius:var(--bd-r-md);
  background:var(--bd-bg);
  border:1.5px dashed var(--bd-brand-line);
  font-size:15px; line-height:2; display:none; word-break:break-word;
}
.result.show{ display:block; animation:bd-fade-up var(--bd-dur-3) var(--bd-ease) both; }
.result-title{ display:flex; align-items:center; gap:8px; font-weight:800;
  font-size:16px; margin-bottom:8px; color:var(--bd-brand); }
.result-actions{ display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }
.result-actions .btn{ margin-top:0; flex:1; min-width:130px; }

/* ══ ورقة سفلية ══ */
.sheet-backdrop{
  position:fixed; inset:0; z-index:150; display:none;
  background:rgba(0,0,0,.55); backdrop-filter:blur(4px);
}
.sheet-backdrop.show{ display:block; animation:bd-fade var(--bd-dur-2) both; }
.sheet{
  position:fixed; inset:auto 0 0; z-index:151;
  max-width:var(--bd-max); margin:0 auto;
  background:var(--bd-surface);
  border-radius:var(--bd-r-lg) var(--bd-r-lg) 0 0;
  padding:20px 18px calc(20px + var(--bd-safe-bottom));
  box-shadow:var(--bd-shadow-2);
  transform:translateY(105%);
  transition:transform var(--bd-dur-3) var(--bd-ease);
}
.sheet.show{ transform:translateY(0); }
.sheet .grabber{ width:42px; height:4px; border-radius:99px;
  background:var(--bd-surface-2); margin:0 auto 14px; }

/* ══ توست ══ */
#toast{
  position:fixed; left:50%; bottom:calc(24px + var(--bd-banner-h) + var(--bd-safe-bottom));
  transform:translate(-50%,18px); z-index:300;
  background:var(--bd-text); color:var(--bd-bg);
  padding:10px 20px; border-radius:var(--bd-r-pill);
  font-size:13.5px; font-weight:700; opacity:0; pointer-events:none;
  transition:opacity var(--bd-dur-2), transform var(--bd-dur-2);
  max-width:88vw; text-align:center;
}
#toast.show{ opacity:1; transform:translate(-50%,0); }

/* ══ إعلان البانر السفلي (ثابت) ══ */
.ad-banner{
  position:fixed; inset:auto 0 0; z-index:120;
  display:none; align-items:center; gap:10px;
  padding:9px 12px calc(9px + var(--bd-safe-bottom));
  background:color-mix(in srgb, var(--bd-surface) 94%, transparent);
  border-top:1px solid var(--bd-brand-line);
  box-shadow:0 -8px 26px rgba(0,0,0,.22);
  backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
}
.ad-banner.show{ display:flex; animation:bd-slide-up var(--bd-dur-3) var(--bd-ease) both; }
.ad-banner .ad-icon{ font-size:19px; flex:0 0 auto; }
.ad-banner .ad-text{ flex:1; min-width:0; font-size:12.5px; line-height:1.6; }
.ad-banner .ad-text a{ color:var(--bd-link); font-weight:800; text-decoration:none; }
.ad-banner .ad-close{
  flex:0 0 auto; width:28px; height:28px; border:none; border-radius:50%;
  background:var(--bd-surface-2); color:var(--bd-hint);
  font-size:14px; cursor:pointer; line-height:1;
}
.ad-banner .ad-label{
  font-size:9px; letter-spacing:.8px; color:var(--bd-hint);
  border:1px solid var(--bd-surface-2); border-radius:4px;
  padding:0 4px; margin-inline-start:4px; vertical-align:middle;
}

/* ══ الإعلان البيني — يظهر بعد النتيجة فقط ══ */
#sponsor-overlay{
  position:fixed; inset:0; z-index:200; display:none;
  background:rgba(0,0,0,.74); backdrop-filter:blur(6px);
  align-items:center; justify-content:center; padding:20px;
}
#sponsor-overlay.show{ display:flex; animation:bd-fade var(--bd-dur-2) both; }
.sponsor-card{
  background:var(--bd-surface); border-radius:var(--bd-r-lg);
  padding:24px 20px; max-width:340px; width:100%; text-align:center;
  animation:bd-pop var(--bd-dur-3) var(--bd-ease) both;
  border:1.5px solid var(--bd-brand-line); box-shadow:var(--bd-shadow-2);
}
.sponsor-card .sp-badge{
  display:inline-block; font-size:10.5px; letter-spacing:1.6px; font-weight:800;
  color:var(--bd-warn); border:1px solid var(--bd-warn);
  padding:3px 12px; border-radius:var(--bd-r-pill); margin-bottom:12px;
}
.sponsor-card h3{ font-size:18px; margin-bottom:6px; }
.sponsor-card p{ color:var(--bd-hint); font-size:13.5px; line-height:1.85;
  margin-bottom:14px; }
.sponsor-card .skip{
  display:block; margin-top:12px; color:var(--bd-hint);
  font-size:12.5px; cursor:pointer; text-decoration:underline;
  background:none; border:none; font-family:inherit; width:100%;
}
.sponsor-card .skip:disabled{ opacity:.55; cursor:default; text-decoration:none; }

/* ══ أدوات مساعدة ══ */
.row{ display:flex; gap:8px; align-items:center; }
.row.between{ justify-content:space-between; }
.stack{ display:flex; flex-direction:column; gap:8px; }
.muted{ color:var(--bd-hint); }
.center{ text-align:center; }
.mt-2{ margin-top:8px; } .mt-3{ margin-top:12px; } .mt-4{ margin-top:16px; }
.mb-0{ margin-bottom:0; }
.sr-only{
  position:absolute; width:1px; height:1px; padding:0; margin:-1px;
  overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0;
}
"""


MOTION_CSS = """
@keyframes bd-pop{
  from{ opacity:0; transform:scale(.86); }
  to{ opacity:1; transform:scale(1); }
}
@keyframes bd-fade{ from{ opacity:0; } to{ opacity:1; } }
@keyframes bd-fade-up{
  from{ opacity:0; transform:translateY(10px); }
  to{ opacity:1; transform:none; }
}
@keyframes bd-slide-up{
  from{ opacity:0; transform:translateY(24px); }
  to{ opacity:1; transform:none; }
}
@keyframes bd-spin{ to{ transform:rotate(360deg); } }
@keyframes bd-shimmer{ to{ background-position:-220% 0; } }
@keyframes bd-indeterminate{
  0%{ transform:translateX(-110%); }
  100%{ transform:translateX(330%); }
}
@keyframes bd-pulse{
  0%,100%{ transform:scale(1); opacity:1; }
  50%{ transform:scale(1.06); opacity:.85; }
}
@keyframes bd-check{
  from{ stroke-dashoffset:24; }
  to{ stroke-dashoffset:0; }
}

/* ظهور متتابع للبطاقات — transform/opacity فقط */
.stagger > *{ animation:bd-fade-up var(--bd-dur-3) var(--bd-ease) both; }
.stagger > *:nth-child(1){ animation-delay:30ms; }
.stagger > *:nth-child(2){ animation-delay:80ms; }
.stagger > *:nth-child(3){ animation-delay:130ms; }
.stagger > *:nth-child(4){ animation-delay:180ms; }
.stagger > *:nth-child(5){ animation-delay:230ms; }
.stagger > *:nth-child(6){ animation-delay:280ms; }
.stagger > *:nth-child(7){ animation-delay:330ms; }
.stagger > *:nth-child(8){ animation-delay:380ms; }
.stagger > *:nth-child(n+9){ animation-delay:420ms; }

/* احترام تفضيل تقليل الحركة — إلزامي */
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{
    animation-duration:.001ms !important;
    animation-iteration-count:1 !important;
    transition-duration:.001ms !important;
    scroll-behavior:auto !important;
  }
  .result.show,.stagger > *{ animation:none !important; }
}
"""
