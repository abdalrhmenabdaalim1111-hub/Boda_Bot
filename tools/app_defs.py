# -*- coding: utf-8 -*-
"""
tools/app_defs.py — منطق كل تطبيق مصغّر: (جسم الصفحة + JS التطبيق)

كل دفتر: APPS[bot_id] = dict(emoji, title, subtitle, body, js, css?, interactive=True)
التطبيقات غير المذكورة تحصل على صفحة "قريباً" أنيقة تلقائياً من المولّد.
"""

APPS = {}

# ═════════════════════════════════ أدوات ═════════════════════════════════════

APPS["currency"] = dict(
    emoji="💱", title="محول العملات الذكي", subtitle="أسعار صرف حية لأكثر من 100 عملة",
    interactive=True,
    body="""
<div class="card">
  <label>المبلغ</label>
  <input type="number" id="amount" placeholder="100" inputmode="decimal" value="100">
  <label>من</label>
  <select id="from"></select>
  <div class="chips" id="from-chips"></div>
  <label>إلى</label>
  <select id="to"></select>
  <div class="chips" id="to-chips"></div>
  <button class="btn" id="go" onclick="convert()">🔄 تحويل الآن</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
const POPULAR=['USD','EUR','GBP','EGP','SAR','AED','KWD','QAR','TRY','JPY'];
let RATES=null, cacheT=0;
async function loadRates(){
  if (RATES && Date.now()-cacheT < 600000) return RATES;   // كاش 10 دقائق
  document.getElementById('go').disabled=true; Boda.toast('⏳ تحميل الأسعار...');
  const r=await fetch('https://api.exchangerate-api.com/v4/latest/USD');
  RATES=(await r.json()).rates; cacheT=Date.now();
  document.getElementById('go').disabled=false; return RATES;
}
function fill(sel, chipsEl, excludeSel){
  const s=document.getElementById(sel), c=document.getElementById(chipsEl);
  const codes=Object.keys(RATES).sort(); s.innerHTML=codes.map(x=>'<option>'+x+'</option>').join('');
  const draw=()=>{ c.innerHTML=POPULAR.map(x=>
    '<span class="chip'+(s.value===x?' active':'')+'" onclick="setVal(\\''+sel+'\\',\\''+x+'\\')">'+x+'</span>').join(''); };
  s.onchange=draw; draw();
}
function setVal(sel,v){ document.getElementById(sel).value=v;
  document.getElementById(sel).dispatchEvent(new Event('change')); }
async function convert(){
  const amt=parseFloat(document.getElementById('amount').value);
  const from=document.getElementById('from').value, to=document.getElementById('to').value;
  if(!amt||amt<=0) return Boda.toast('⚠️ أدخل مبلغاً صحيحاً');
  Boda.haptic('light');
  const rates=await loadRates();
  const out=amt/rates[from]*rates[to], rate=(1/rates[from]*rates[to]);
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML=
    '<b style="font-size:20px">'+amt.toLocaleString()+' '+from+' = '+
    '<span style="color:var(--accent)">'+out.toLocaleString(undefined,{maximumFractionDigits:2})+' '+to+'</span></b>'+
    '<br><small style="color:var(--hint)">1 '+from+' = '+rate.toFixed(4)+' '+to+'</small>'+
    '<br><button class="btn secondary" style="margin-top:8px" onclick="Boda.copy(\\''+out.toFixed(2)+' '+to+'\\')">📋 نسخ النتيجة</button>';
  Boda.track('feature_use',{detail:'convert'});
}
loadRates().then(r=>{ fill('from','from-chips'); fill('to','to-chips');
  setVal('from','USD'); setVal('to','EGP'); });
""",
)

APPS["qrgen"] = dict(
    emoji="🔗", title="مولّد QR احترافي", subtitle="حوّل أي رابط أو نص إلى QR فوري",
    interactive=True,
    body="""
<div class="card">
  <label>النص أو الرابط</label>
  <textarea id="txt" placeholder="https://example.com"></textarea>
  <div class="chips">
    <span class="chip" onclick="preset('https://t.me/BodaStoreeBot')">🏪 متجرنا</span>
    <span class="chip" onclick="preset('WIFI:T:WPA;S:اسم_الشبكة;P:الباسورد;;')">📶 WiFi</span>
  </div>
  <label>الحجم</label>
  <div class="chips" id="size-chips">
    <span class="chip" data-s="220" onclick="pickSize(this)">صغير</span>
    <span class="chip active" data-s="300" onclick="pickSize(this)">متوسط</span>
    <span class="chip" data-s="380" onclick="pickSize(this)">كبير</span>
  </div>
  <button class="btn" onclick="gen()">⚡ توليد QR</button>
  <div class="result" id="res" style="text-align:center">
    <img id="qr" alt="QR" style="border-radius:12px;background:#fff;padding:8px;display:none">
  </div>
</div>
""",
    js="""
let SIZE=300;
function pickSize(el){ document.querySelectorAll('#size-chips .chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active'); SIZE=+el.dataset.s; }
function preset(v){ document.getElementById('txt').value=v; }
async function gen(){
  const txt=document.getElementById('txt').value.trim();
  if(!txt) return Boda.toast('⚠️ أدخل نصاً أولاً');
  Boda.haptic('light');
  const img=document.getElementById('qr');
  img.src='https://api.qrserver.com/v1/create-qr-code/?size='+SIZE+'x'+SIZE+
          '&margin=12&data='+encodeURIComponent(txt);
  img.style.display='inline-block';
  document.getElementById('res').className='result show';
  img.onload=()=>Boda.track('feature_use',{detail:'qr_generated'});
}
""",
)

APPS["cryptorate"] = dict(
    emoji="💰", title="أسعار العملات الرقمية", subtitle="BTC وETH وكل العملات لحظياً",
    interactive=True,
    body="""
<div class="card">
  <div id="list">⏳ جاري التحميل...</div>
  <button class="btn secondary" onclick="load(true)">🔄 تحديث الأسعار</button>
</div>
""",
    js="""
const COINS=['bitcoin','ethereum','binancecoin','solana','ripple','cardano','dogecoin','tether'];
const SYM={bitcoin:'₿',ethereum:'Ξ',binancecoin:'BNB',solana:'SOL',ripple:'XRP',cardano:'ADA',dogecoin:'DOGE',tether:'USDT'};
async function load(manual){
  const el=document.getElementById('list');
  if(manual){ el.innerHTML='⏳ تحديث...'; Boda.haptic('light'); }
  try{
    const r=await fetch('https://api.coingecko.com/api/v3/simple/price?ids='+COINS.join(',')+
      '&vs_currencies=usd&include_24hr_change=true');
    const d=await r.json();
    el.innerHTML=COINS.filter(c=>d[c]).map(c=>{
      const p=d[c].usd, ch=d[c].usd_24h_change||0;
      const up=ch>=0;
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-bottom:1px solid var(--hint)">'+
        '<span style="font-size:16px"><b>'+SYM[c]+'</b> '+c.charAt(0).toUpperCase()+c.slice(1)+'</span>'+
        '<span style="text-align:left"><b>$'+p.toLocaleString(undefined,{maximumFractionDigits:2})+'</b><br>'+
        '<small style="color:'+(up?'var(--ok)':'var(--danger)')+'">'+(up?'▲':'▼')+' '+Math.abs(ch).toFixed(2)+'%</small></span></div>';
    }).join('');
    Boda.track('feature_use',{detail:manual?'refresh':'view'});
  }catch(e){ el.innerHTML='⚠️ تعذر جلب الأسعار — تحقق من الاتصال'; }
}
load();
""",
)

APPS["safepass"] = dict(
    emoji="🔒", title="مولّد كلمات المرور", subtitle="كلمات مرور قوية محلياً 100% — لا تُرسل لأي خادم",
    interactive=True,
    body="""
<div class="card">
  <label>الطول: <span id="len-v">16</span> حرف</label>
  <input type="range" id="len" min="8" max="40" value="16" style="width:100%" oninput="document.getElementById('len-v').textContent=this.value">
  <div class="chips">
    <span class="chip active" id="c-up" onclick="tog('up')">A-Z</span>
    <span class="chip active" id="c-lo" onclick="tog('lo')">a-z</span>
    <span class="chip active" id="c-di" onclick="tog('di')">0-9</span>
    <span class="chip active" id="c-sy" onclick="tog('sy')">@#$</span>
  </div>
  <button class="btn" onclick="gen()">🎲 توليد كلمة مرور</button>
  <div class="result" id="res"></div>
  <div id="strength"></div>
</div>
""",
    js="""
const on={up:1,lo:1,di:1,sy:1};
function tog(k){ on[k]=!on[k]; document.getElementById('c-'+k).classList.toggle('active',!!on[k]); }
const SETS={up:'ABCDEFGHIJKLMNOPQRSTUVWXYZ',lo:'abcdefghijklmnopqrstuvwxyz',di:'0123456789',sy:'!@#$%^&*_-+=?'};
function gen(){
  let pool=''; Object.keys(on).forEach(k=>{ if(on[k]) pool+=SETS[k]; });
  if(!pool) return Boda.toast('⚠️ اختر مجموعة واحدة على الأقل');
  const n=+document.getElementById('len').value;
  const arr=new Uint32Array(n); crypto.getRandomValues(arr);
  const pw=[...arr].map(x=>pool[x%pool.length]).join('');
  Boda.haptic('success');
  const res=document.getElementById('res'); res.className='result show';
  res.innerHTML='<code style="font-size:16px;word-break:break-all">'+pw+'</code>'+
    '<button class="btn secondary" onclick="Boda.copy(\\''+pw+'\\')">📋 نسخ</button>';
  // قوة كلمة المرور: تشكيلة + طول
  let bits=n*Math.log2(pool.length);
  const lv=bits>100?['ممتازة 💪','var(--ok)']:bits>60?['قوية ✔','var(--ok)']:bits>40?['متوسطة ⚠','var(--warn)']:['ضعيفة ✖','var(--danger)'];
  document.getElementById('strength').innerHTML='<p style="color:'+lv[1]+';font-size:13px;margin-top:8px">القوة: '+lv[0]+' ('+Math.round(bits)+' bit)</p>';
  Boda.track('feature_use',{detail:'pw_'+n});
}
""",
)

APPS["shortlink"] = dict(
    emoji="✂️", title="مختصر الروابط", subtitle="حوّل الروابط الطويلة إلى روابط قصيرة أنيقة",
    interactive=True,
    body="""
<div class="card">
  <label>الرابط الطويل</label>
  <input type="text" id="url" placeholder="https://very-long-link.com/..." dir="ltr">
  <button class="btn" onclick="shorten()">✂️ اختصار</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
async function shorten(){
  const u=document.getElementById('url').value.trim();
  if(!/^https?:\\/\\//.test(u)) return Boda.toast('⚠️ أدخل رابطاً يبدأ بـ http');
  Boda.haptic('light');
  const res=document.getElementById('res');
  res.className='result show'; res.innerHTML='⏳ جاري الاختصار...';
  try{
    // is.gd API — مجاني بدون مفتاح
    const r=await fetch('https://is.gd/create.php?format=json&url='+encodeURIComponent(u));
    const d=await r.json();
    if(d.shorturl){
      res.innerHTML='<code dir="ltr">'+d.shorturl+'</code>'+
        '<div style="display:flex;gap:8px;margin-top:10px">'+
        '<button class="btn secondary" onclick="Boda.copy(\\''+d.shorturl+'\\')">📋 نسخ</button>'+
        '<button class="btn secondary" onclick="Boda.share(\'رابط قصير via متجر بودا\',\\''+d.shorturl+'\\')">📤 مشاركة</button></div>';
      Boda.track('feature_use',{detail:'shorten'});
    } else throw 0;
  }catch(e){ res.innerHTML='⚠️ فشل الاختصار — جرّب رابطاً آخر'; }
}
""",
)

# ═══════════════════════════════════ ترفيه ═══════════════════════════════════

APPS["lovecalculator"] = dict(
    emoji="❤️", title="حاسبة الحب", subtitle="اكتب اسماين وشوف نسبة التوافق 😄",
    interactive=True,
    body="""
<div class="card">
  <label>اسمك</label><input type="text" id="a" placeholder="مثال: أحمد">
  <label>اسم الحبيب/الحبيبة 💕</label><input type="text" id="b" placeholder="مثال: سارة">
  <button class="btn" onclick="calc()">💘 احسب النسبة</button>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
function calc(){
  const a=document.getElementById('a').value.trim(), b=document.getElementById('b').value.trim();
  if(!a||!b) return Boda.toast('⚠️ اكتب الاسمايين');
  Boda.haptic('light');
  // دالة ثابتة (نفس الاسمين = نفس النتيجة دائماً — مثل النسخة الأصلية)
  let h=0; const s=(a+'♥'+b).toLowerCase();
  for(let i=0;i<s.length;i++) h=(h*31+s.charCodeAt(i))>>>0;
  const pct=h%101;
  let msg = pct>=90?'💍 زواج قريب بإذن الله!':pct>=70?'💕 توافق رائع!':pct>=50?'😊 علاقة واعدة':pct>=30?'🤝 صداقة قوية':'😂 مفيش أمل 😅';
  // شريط تقدم متحرك
  const res=document.getElementById('res'); res.className='result show';
  res.innerHTML='<div style="font-size:44px;font-weight:800;color:var(--accent)">'+pct+'%</div>'+
    '<div style="background:var(--bg);border-radius:999px;height:12px;margin:10px 0;overflow:hidden">'+
    '<div style="width:'+pct+'%;height:100%;background:linear-gradient(90deg,var(--danger),var(--accent));border-radius:999px"></div></div>'+
    '<p>'+msg+'</p>'+
    '<button class="btn secondary" onclick="Boda.share(\'نسبة الحب بيني وبين... جرب حاسبة الحب 💌\',\'https://t.me/BodaLoveCalBot\')">📤 تحدى أصدقاءك</button>';
  Boda.track('feature_use',{detail:'love_'+(pct>=70)});
}
""",
)

APPS["mentalage"] = dict(
    emoji="🧠", title="اختبار العمر العقلي", subtitle="كم عمر عقلك الحقيقي؟ 10 أسئلة سريعة",
    interactive=True,
    body="""
<div class="card" id="quiz">
  <div id="q-box"></div>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
const QS=['أفضل لون عندك؟','يومك المثالي؟','الرياضيات؟','المشاريع المعلقة؟','قبل النوم بتفكر في؟','الأخبار تتابعها؟','جديد جرّبته آخر شهر؟','الخطة بتعملها؟','الموبايل عندك؟','المستقبل بالنسبة ليك؟'];
const OPT=[['🔴 الأحمر','🔵 الأزرق','🟢 الأخضر','🟡 الأصفر'],
  ['نوم وراحة','خروج وأصدقاء','قراءة وهدوء','شغل وتحدي'],
  ['أكرهها','عادية','بحلها للترفيه','أحبها'],
  ['مليش','قليلة','كتير 😅','مش محتاج — بكمّل فوراً'],
  ['ولا حاجة','الغد','الماضي','أفكار عشوائية'],
  ['لا','أحياناً','كل يوم','مصادر متعددة'],
  ['صفر','واحدة','٢-٣','أكتر من ٥'],
  ['أرتجّل','بسيطة','مفصّلة','جداول ومواعيد'],
  ['قديم وبسيط','حديث','فلاجشيب','أدوات ذكية كتير'],
  ['مخيف','غامض','تحدي','فرصة']];
let i=0, score=0;
const PTS=[[1,2,3,4],[1,3,2,4],[1,2,3,4],[1,3,2,4],[2,3,3,4],[1,2,3,4],[1,2,3,4],[1,2,3,4],[1,2,3,4],[1,2,3,4]];
function render(){
  document.getElementById('q-box').innerHTML=
    '<small style="color:var(--hint)">السؤال '+(i+1)+' من '+QS.length+'</small>'+
    '<h2 style="margin:8px 0">'+QS[i]+'</h2>'+
    OPT[i].map((o,k)=>'<button class="btn secondary" onclick="pick('+k+')">'+o+'</button>').join('');
}
function pick(k){
  score+=PTS[i][k]; Boda.haptic('light'); i++;
  if(i<QS.length) render(); else finish();
}
function finish(){
  const age=Math.max(12, Math.min(70, Math.round(75-score*1.35)));
  Boda.track('feature_use',{detail:'age_'+age});
  document.getElementById('q-box').innerHTML='';
  const res=document.getElementById('res'); res.className='result show';
  const txt = age<20?'عقلك شبابي مليان حيوية! 🎉':age<30?'عقلك في القمة — توازن رائع 🌟':
              age<45?'عقلك ناضج وحكيم 🧘':age<58?'عقلك حكيم بتجارب غنية 📚':'عقل فيلسوف حقيقي 🦉';
  res.innerHTML='<div style="font-size:40px;font-weight:800;color:var(--accent)">'+age+' سنة</div>'+
    '<p style="margin:8px 0">عقلكم العقلي: '+txt+'</p>'+
    '<button class="btn" onclick="location.reload()">🔁 إعادة الاختبار</button>'+
    '<button class="btn secondary" onclick="Boda.share(\'عقلي  \\''+age+'\\' سنة! جرّب اختبار العمر العقلي 🧠\',\'https://t.me/BodaMentalAgeBot\')">📤 شارك نتيجتك</button>';
}
render();
""",
)

APPS["iqtest"] = dict(
    emoji="🧩", title="اختبار الذكاء السريع", subtitle="10 أسئلة منطقية — 5 دقائق",
    interactive=True,
    body="""
<div class="card"><div id="q-box"></div><div class="result" id="res" style="text-align:center"></div></div>
""",
    js="""
const QS=[
 {q:'ما الرقم التالي: 2, 4, 8, 16, ...?',a:['24','32','20','18'],c:1},
 {q:'لو كل زهرة تحتاج شمس، والورد زهرة، إذن الورد...',a:['شجرة','يحتاج شمس','لا يحتاج شمس','شوكة'],c:1},
 {q:'CAT : DBU = DOG : ?',a:['EPH','EPG','EPI','DPH'],c:2},
 {q:'أي شكل لا ينتمي؟',a:['مربع','مثلث','دائرة','مستطيل'],c:2},
 {q:'5 آلات تصنع 5 قطع في 5 دقائق، 100 آلة تصنع 100 قطعة في...؟',a:['100 دقيقة','20 دقيقة','5 دقائق','50 دقيقة'],c:2},
 {q:'الأب فوق: عمره ضعف عمر ابنه، مجموع أعمارهما 60. عمر الأب؟',a:['45','40','35','30'],c:1},
 {q:'ما الحرف التالي: A, C, E, G, ...?',a:['H','I','J','K'],c:1},
 {q:'لو رأيت مرآة كلمة "BODA" فماذا تظهر؟',a:['BODA','ADO B','مقلوبة غير قابلة للقراءة','AOOB'],c:2},
 {q:'قطرة ماء واحدة = 10 ثوانٍ. كم ساعة يمتلئ كوب 360 قطرة؟',a:['1 ساعة','10 دقائق','ساعة ونصف','36 دقيقة'],c:0},
 {q:'الغريب دخل قرية كل أهلها كاذبون. قاله أحدهم: "أنا كاذب". هو...؟',a:['كاذب لأنهم كلهم كاذبون','صادق لأن الكاذب يكذب','متناقض — لا يمكن الحسم','أهلك القلعة'],c:2}];
let i=0, correct=0, t0=Date.now();
function render(){
  const q=QS[i];
  document.getElementById('q-box').innerHTML=
    '<small style="color:var(--hint)">سؤال '+(i+1)+'/'+QS.length+' ✓ '+correct+'</small>'+
    '<h2 style="margin:8px 0">'+q.q+'</h2>'+
    q.a.map((o,k)=>'<button class="btn secondary" onclick="pick('+k+')" style="text-align:right">'+o+'</button>').join('');
}
function pick(k){
  if(k===QS[i].c){ correct++; Boda.haptic('success'); } else Boda.haptic('error');
  i++; if(i<QS.length) render(); else finish();
}
function finish(){
  const pct=Math.round(correct/QS.length*100);
  const iq=Math.round(70+pct*0.65);
  Boda.track('feature_use',{detail:'iq_'+iq});
  const lv = iq>=120?'🧠 عبقري!':iq>=100?'🌟 فوق المتوسط':iq>=85?'😊 جيد جداً':'📚 تحتاج تدريب';
  document.getElementById('q-box').innerHTML='';
  const res=document.getElementById('res'); res.className='result show';
  res.innerHTML='<div style="font-size:40px;font-weight:800;color:var(--accent)">'+iq+'</div>'+
    '<p>أجبت صح على '+correct+' من '+QS.length+' في '+Math.round((Date.now()-t0)/1000)+' ثانية</p>'+
    '<p style="margin:6px 0">'+lv+'</p>'+
    '<button class="btn" onclick="location.reload()">🔁 إعادة</button>'+
    '<button class="btn secondary" onclick="Boda.share(\'نتيجتي في اختبار الذكاء: \'+\'\'+iq+\' IQ 🧠 جرّبها!\',\'https://t.me/BodaIQTestBot\')">📤 شارك</button>';
}
render();
""",
)

APPS["luckybox"] = dict(
    emoji="🎁", title="صندوق الحظ", subtitle="افتح صندوقاً غامضاً كل يوم — ماذا ستحصل عليه؟",
    interactive=True,
    body="""
<div class="card" style="text-align:center">
  <div id="box" style="font-size:80px;cursor:pointer;transition:transform .3s"
       onclick="openBox()">🎁</div>
  <p style="color:var(--hint);font-size:13px;margin-top:8px">اضغط الصندوق للفتح!</p>
  <div class="result" id="res"></div>
</div>
""",
    js="""
const PRIZES=[
 {e:'💎',t:'جوهرة نادرة!',w:5},{e:'🏆',t:'كأس البطل!',w:8},
 {e:'🌟',t:'حظ أسطوري اليوم!',w:10},{e:'💰',t:'كيس ذهب!',w:12},
 {e:'🍀',t:'برسيم الحظ!',w:20},{e:'🎂',t:'كيكة مفاجأة!',w:15},
 {e:'🐱',t:'قطة سعيدة!',w:15},{e:'💥',t:'انفجر الصندوق! 😂',w:15}];
function openBox(){
  const box=document.getElementById('box');
  if(box.dataset.busy) return;
  const today=new Date().toDateString();
  const last=localStorage.getItem('boda_lucky_last');
  if(last===today && !box.dataset.demo){
    Boda.toast('📅 عد غداً لصندوق جديد!'); return;
  }
  box.dataset.busy=1;
  let n=0; const spin=setInterval(()=>{
    box.style.transform='rotate('+(n*37)+'deg) scale('+(1+n%3*0.1)+')';
    box.textContent=['🎁','✨','🎲','🎊'][n%4]; n++;
  },90);
  setTimeout(()=>{
    clearInterval(spin); box.style.transform='none';
    const total=PRIZES.reduce((s,p)=>s+p.w,0);
    let r=Math.random()*total, pick=PRIZES[0];
    for(const p of PRIZES){ if((r-=p.w)<=0){ pick=p; break; } }
    box.textContent=pick.e; delete box.dataset.busy;
    localStorage.setItem('boda_lucky_last', today);
    Boda.haptic('success'); Boda.track('feature_use',{detail:'prize_'+pick.e});
    const res=document.getElementById('res'); res.className='result show';
    res.innerHTML='<h2 style="font-size:22px">'+pick.e+' '+pick.t+'</h2>'+
      '<button class="btn secondary" onclick="Boda.share(\'فتحت صندوق الحظ وحصلت على '+pick.e+' '+pick.t+' جرّب أنت كمان 🎁\',\'https://t.me/BodaLuckyBoxBot\')">📤 شارك حظك</button>'+
      '<p style="color:var(--hint);font-size:12px;margin-top:10px">صندوق جديد يومياً 🔄</p>';
  },1400);
}
""",
)

APPS["braintwist"] = dict(
    emoji="🌀", title="ألغاز الأذكياء", subtitle="ألغاز تمسك الدماغ — كل يوم لغز جديد",
    interactive=True,
    body="""
<div class="card"><div id="q-box"></div><div class="result" id="res"></div></div>
""",
    js="""
const PUZZLES=[
 {q:'ما الشيء الذي كلما أخذت منه كبر؟',a:'الحفرة',hint:'في الأرض'},
 {q:'له أسنان ولا يعض، ما هو؟',a:'المشط',hint:'للشعر'},
 {q:'يمشي بلا أرجل ويبكي بلا عيون، ما هو؟',a:'السحاب',hint:'في السماء'},
 {q:'كلمة مقروءة من اليمين ومن اليسار بنفس الطريقة',a:'مثل: كشك أو لا نيل إلا دم',hint:'اقرأها بالعكس'},
 {q:'ما هو الشيء الذي يسمع بلا أذن ويتكلم بلا لسان؟',a:'التليفون',hint:'في جيبك الآن'}];
let i=0, solved=0;
function render(){
  const p=PUZZLES[i];
  document.getElementById('q-box').innerHTML=
    '<small style="color:var(--hint)">لغز '+(i+1)+'/'+PUZZLES.length+' ✔ '+solved+'</small>'+
    '<h2 style="margin:8px 0">'+p.q+'</h2>'+
    '<input type="text" id="ans" placeholder="اكتب إجابتك هنا...">'+
    '<button class="btn" onclick="check()">✅ تحقق</button>'+
    '<button class="btn secondary" onclick="showHint()">💡 تلميح</button>';
  document.getElementById('hint-btn');
}
function showHint(){ Boda.toast('💡 '+PUZZLES[i].hint); Boda.track('feature_use',{detail:'hint_used'}); }
function check(){
  const v=document.getElementById('ans').value.trim().replace(/\\s+/g,'');
  const a=PUZZLES[i].a.replace(/\\s+/g,'');
  if(!v) return Boda.toast('⚠️ اكتب إجابة');
  if(v.includes(a)||a.includes(v)){
    solved++; Boda.haptic('success');
    document.getElementById('res').className='result show';
    document.getElementById('res').innerHTML='🎉 <b>إجابة صحيحة!</b> ('+PUZZLES[i].a+')'+
      '<button class="btn" style="margin-top:10px" onclick="next()">اللغز التالي ←</button>';
  } else { Boda.haptic('error'); Boda.toast('❌ ليست الإجابة — حاول مرة أخرى'); }
}
function next(){
  document.getElementById('res').className='result';
  i++; if(i<PUZZLES.length) render();
  else { document.getElementById('q-box').innerHTML='<h2>🎊 حللت كل الألغاز!</h2>'+
    '<p style="color:var(--hint)">عد غداً لألغاز جديدة</p>'+
    '<button class="btn" onclick="i=0;solved=0;render()">🔁 من البداية</button>'+
    '<button class="btn secondary" onclick="Boda.share(\'حللت كل ألغاز الأذكياء 🌀 تحداني!\',\'https://t.me/BodaBrainTwistBot\')">📤 تحدى صديقاً</button>';
    Boda.track('feature_use',{detail:'all_solved'}); }
}
render();
""",
)

APPS["fun_name"] = dict(
    emoji="🎭", title="مولّد الأسماء الطريفة", subtitle="اسم عربي مضحك + لقب — من اسمك الحقيقي",
    interactive=True,
    body="""
<div class="card">
  <label>اكتب اسمك</label><input type="text" id="name" placeholder="مثال: محمد">
  <button class="btn" onclick="gen()">🎲 ولّد اسمي الطريف</button>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
const TITLES=['سيّد','الخواجة','كابتن','باشا','الأستاذ','دكتور','الحاج','المعلم','برنس','شيخ'];
const NICKS=['اللي سيب قلبه في الطريق','مالك آخر كلمة في النرد','قلب الضبع','صاحب أسطورة اللف والنشر',
 'ملك الفتافيت الأخير','قاهر الدهاليز','مهندس المآسي الكبرى','نجم كورة الطاولة','حارس أسرار الرحابة','موزع الابتسامات المجاني'];
const ANIMALS=['النمر','الصقر','الذئب','الأسد الشجاع','الفهد','الثعلب المشمشي','البجعة','الحيوان الأليف الرسمي للدولة'];
function gen(){
  const n=document.getElementById('name').value.trim();
  if(!n) return Boda.toast('⚠️ اكتب اسمك');
  Boda.haptic('light');
  let h=0; for(const c of n) h=(h*31+c.codePointAt(0))>>>0;
  const t=TITLES[h%TITLES.length], k=NICKS[(h>>3)%NICKS.length], a=ANIMALS[(h>>6)%ANIMALS.length];
  const full=t+' '+n+' '+a+'، '+k;
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML='<div style="font-size:18px;font-weight:700">'+full+'</div>'+
    '<button class="btn secondary" onclick="Boda.copy(\\''+full+'\\')">📋 نسخ</button>'+
    '<button class="btn secondary" onclick="Boda.share(\'اسمي الطريف: '+full+' 🎭 ولّد اسمك!\',\'https://t.me/BodaFunNameBot\')">📤 شارك</button>';
  Boda.track('feature_use',{detail:'name_gen'});
}
""",
)

APPS["random_suggest"] = dict(
    emoji="🎲", title="قرار عشوائي ذكي", subtitle="متحتار؟ اترك القرار للعشوائية — أفلام، أكل، نشاطات",
    interactive=True,
    body="""
<div class="card">
  <div class="chips">
    <span class="chip active" onclick="pickCat(this,'eat')">🍔 أكل</span>
    <span class="chip" onclick="pickCat(this,'watch')">🎬 أفلام</span>
    <span class="chip" onclick="pickCat(this,'do')">⚡ نشاط</span>
  </div>
  <button class="btn" onclick="spin()">🎲 اقترح عليّ!</button>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
const DATA={
 eat:['كشري 🍚','بيتزا 🍕','برجر 🍔','شاورما 🌯','محشي 🫑','مكرونة بشاميل 🥧','فول وطعمية 🫘','سوشي 🍣','مشويات 🍖','صيني بالدجاج 🥡'],
 watch:['Interstellar 🌌','The Office 😂','Breaking Bad 🧪','Inception 🌀','فيلم مصري كوميدي 🇪🇬','Sherlock 🔍','Money Heist 💰','وثائقي عن الفضاء 🚀','The Last Dance 🏀','أوتاكو شونين ⚔️'],
 do:['اتصل بصديق قديم ☎️','امشي 20 دقيقة 🚶','تعلم كلمة بلغة جديدة 🌍','رتّب مكتبك 🗂','اسمع بودكاست 🎧','اكتب 3 أهداف 🔥','اشرب كوباية مية 💧','تمرين سريع 💪','اقرأ 10 صفحات 📖','نم بدري الليلة 😴']};
let cat='eat';
function pickCat(el,c){
  document.querySelectorAll('.chips .chip').forEach(x=>x.classList.remove('active'));
  el.classList.add('active'); cat=c;
}
function spin(){
  Boda.haptic('light');
  const list=DATA[cat];
  let n=0; const res=document.getElementById('res'); res.className='result show';
  const iv=setInterval(()=>{
    res.innerHTML='<div style="font-size:24px;font-weight:700">'+list[n%list.length]+'</div>';
    n++; if(n>12){ clearInterval(iv);
      const pick=list[Math.floor(Math.random()*list.length)];
      res.innerHTML='<div style="font-size:24px;font-weight:800;color:var(--accent)">'+pick+'</div>'+
        '<button class="btn secondary" onclick="spin()">🔁 مرة أخرى</button>'+
        '<button class="btn secondary" onclick="Boda.share(\'اقترح لي القرار العشوائي: '+pick+' 🎲\',\'https://t.me/BodaRandomBot\')">📤 شارك</button>';
      Boda.haptic('success'); Boda.track('feature_use',{detail:cat});
    }
  },80);
}
""",
)

# ═════════════════════════════════ صحة/إنتاجية ═══════════════════════════════

APPS["caltrack"] = dict(
    emoji="🍎", title="حاسبة السعرات", subtitle="اعرف سعرات طعامك اليومية ونسبة الحرق",
    interactive=True,
    body="""
<div class="card">
  <div style="display:flex;gap:10px">
    <div style="flex:1"><label>الوزن (كجم)</label><input type="number" id="w" value="75"></div>
    <div style="flex:1"><label>الطول (سم)</label><input type="number" id="h" value="170"></div>
    <div style="flex:1"><label>العمر</label><input type="number" id="age" value="25"></div>
  </div>
  <label>الجنس</label>
  <div class="chips">
    <span class="chip active" id="g-m" onclick="setG(this,'m')">ذكر</span>
    <span class="chip" id="g-f" onclick="setG(this,'f')">أنثى</span>
  </div>
  <label>مستوى النشاط</label>
  <select id="act">
    <option value="1.2">خفيف — مكتب بلا رياضة</option>
    <option value="1.375" selected>متوسط — رياضة 1-3 أيام</option>
    <option value="1.55">نشيط — رياضة 3-5 أيام</option>
    <option value="1.725">نشيط جداً — يومياً</option>
  </select>
  <button class="btn" onclick="calc()">🔥 احسب احتياجي اليومي</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
let g='m';
function setG(el,v){ document.querySelectorAll('.chips .chip').forEach(x=>x.classList.remove('active'));
  el.classList.add('active'); g=v; }
function calc(){
  const w=+document.getElementById('w').value, h=+document.getElementById('h').value,
        a=+document.getElementById('age').value, act=+document.getElementById('act').value;
  if(!w||!h||!a) return Boda.toast('⚠️ أكمل البيانات');
  // Mifflin-St Jeor
  const bmr=Math.round(10*w+6.25*h-5*a+(g==='m'?5:-161));
  const tdee=Math.round(bmr*act);
  Boda.haptic('success'); Boda.track('feature_use',{detail:'calories'});
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML=
    '<b>الأيض الأساسي (BMR):</b> '+bmr.toLocaleString()+" سعرة<br>"+
    '<b>احتياجك اليومي:</b> <span style="color:var(--accent);font-size:19px;font-weight:800">'+tdee.toLocaleString()+' سعرة</span><br>'+
    '<small style="color:var(--hint)">للإنقاص: '+(tdee-400).toLocaleString()+' · للتزيّد: '+(tdee+400).toLocaleString()+' سعرة</small>';
}
""",
)

APPS["fitcheck"] = dict(
    emoji="💪", title="فاحص اللياقة", subtitle="BMI + نبضك المستهدف + تقييم لياقتك",
    interactive=True,
    body="""
<div class="card">
  <div style="display:flex;gap:10px">
    <div style="flex:1"><label>الوزن (كجم)</label><input type="number" id="w" value="75"></div>
    <div style="flex:1"><label>الطول (سم)</label><input type="number" id="h" value="170"></div>
  </div>
  <label>عمرك (لحساب النبض)</label><input type="number" id="age" value="25">
  <button class="btn" onclick="calc()">📏 فحص اللياقة</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
function calc(){
  const w=+document.getElementById('w').value, h=+document.getElementById('h').value/100,
        age=+document.getElementById('age').value;
  if(!w||!h||!age) return Boda.toast('⚠️ أكمل البيانات');
  const bmi=w/(h*h);
  const lv = bmi<18.5?['نقص وزن','var(--warn)']:bmi<25?['وزن مثالي ✔','var(--ok)']:
             bmi<30?['زيادة وزن ⚠','var(--warn)']:['سمنة — خليك نشيط 💪','var(--danger)'];
  const max=Math.round(220-age), fat=Math.round(max*0.65), cardio=Math.round(max*0.8);
  Boda.haptic('success'); Boda.track('feature_use',{detail:'bmi_'+Math.round(bmi)});
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML=
    '<div style="text-align:center"><span style="font-size:32px;font-weight:800;color:'+lv[1]+'">'+bmi.toFixed(1)+'</span>'+
    '<br><small style="color:'+lv[1]+'">'+lv[0]+'</small></div><hr style="border-color:var(--hint);margin:10px 0">'+
    '<b>نطاق BMI الصحي:</b> 18.5 – 24.9<br>'+
    '<b>أقصى نبض:</b> '+max+' نبضة/د<br>'+
    '<b>النبض لحرق الدهون:</b> '+fat+'-'+(fat+15)+' نبضة/د';
}
""",
)

APPS["memoryvault"] = dict(
    emoji="🗄️", title="خزنة الذكريات", subtitle="اكتب ذكرى وحدد تاريخ فتحها — رسالة من الزمن",
    interactive=True,
    body="""
<div class="card">
  <label>عنوان الذكرى</label><input type="text" id="title" placeholder="مثال: رسالة لي بعد سنة">
  <label>الرسالة</label><textarea id="msg" placeholder="عزيزي أنا المستقبلي..."></textarea>
  <label>تاريخ فتح الخزنة</label><input type="date" id="date">
  <button class="btn" onclick="save()">🔐 خزّن الذكرى</button>
  <div class="result" id="res"></div>
</div>
<div class="card">
  <h2>🗝️ خزائنك</h2>
  <div id="vault-list" style="color:var(--hint);font-size:14px">لا توجد خزائن بعد</div>
</div>
""",
    js="""
function all(){ try{ return JSON.parse(localStorage.getItem('boda_vault')||'[]'); }catch(e){ return []; } }
function renderList(){
  const list=all();
  const el=document.getElementById('vault-list');
  if(!list.length){ el.innerHTML='لا توجد خزائن بعد'; return; }
  el.innerHTML=list.map((v,k)=>{
    const locked=new Date(v.date)>new Date();
    return '<div class="card" style="background:var(--bg);padding:12px;margin-bottom:8px">'+
      '<b>'+(locked?'🔒':'🔓')+' '+v.title+'</b>'+
      '<small style="color:var(--hint)"> — يفتح في '+v.date+'</small>'+
      (locked?'':'<p style="margin-top:6px">'+v.msg+'</p>')+'</div>';
  }).join('');
}
function save(){
  const t=document.getElementById('title').value.trim(), m=document.getElementById('msg').value.trim(),
        d=document.getElementById('date').value;
  if(!t||!m||!d) return Boda.toast('⚠️ أكمل كل الحقول');
  const list=all(); list.unshift({title:t,msg:m,date:d,created:Date.now()});
  localStorage.setItem('boda_vault', JSON.stringify(list.slice(0,30)));
  Boda.haptic('success'); Boda.track('feature_use',{detail:'vault_saved'});
  Boda.toast('🔐 تم الخزن! افتح التطبيق يوم '+d);
  document.getElementById('title').value=''; document.getElementById('msg').value='';
  renderList();
}
document.getElementById('date').value=new Date(Date.now()+30*864e5).toISOString().slice(0,10);
renderList();
""",
)

APPS["alarmbot"] = dict(
    emoji="⏰", title="مؤقّت التركيز", subtitle="بومودورو 25 دقيقة مع تنبيه داخل تيليجرام",
    interactive=True,
    body="""
<div class="card" style="text-align:center">
  <div id="clock" style="font-size:56px;font-weight:800;font-variant-numeric:tabular-nums">25:00</div>
  <div class="chips" style="justify-content:center">
    <span class="chip active" data-m="25" onclick="pick(this)">pomodoro 25</span>
    <span class="chip" data-m="5" onclick="pick(this)">استراحة 5</span>
    <span class="chip" data-m="50" onclick="pick(this)">عميق 50</span>
  </div>
  <button class="btn" id="start" onclick="toggle()">▶ ابدأ التركيز</button>
  <p style="color:var(--hint);font-size:12.5px;margin-top:10px" id="status">
    عند اكتمال الوقت سيهتز التطبيق وينبّهك تلقائياً</p>
</div>
""",
    js="""
let M=25, left=M*60, iv=null;
function pick(el){ document.querySelectorAll('.chips .chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active'); M=+el.dataset.m; stop(); left=M*60; draw(); }
function draw(){
  const s=Math.floor(left%60), m=Math.floor(left/60);
  document.getElementById('clock').textContent=
    String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
  try{ Boda.tg.setHeaderColor(left<M*60*0.25?'bg_color':'secondary_bg_color'); }catch(e){}
}
function toggle(){ iv?stop():(start(),Boda.track('feature_use',{detail:'focus_'+M})); }
function start(){
  document.getElementById('start').textContent='⏸ إيقاف مؤقت';
  iv=setInterval(()=>{
    left--; draw();
    if(left<=0){
      stop(); Boda.haptic('heavy');
      Boda.toast('⏰ انتهى الوقت! خد استراحة 🎉');
      document.getElementById('status').textContent='✅ اكتملت الجلسة — شرب ميّة وقوم اتحرك!';
      try{ Boda.tg.showAlert('⏰ انتهى وقت التركيز! أحسنت 👏'); }catch(e){}
    }
  },1000);
}
function stop(){ if(iv) clearInterval(iv); iv=null;
  document.getElementById('start').textContent='▶ ابدأ التركيز'; }
draw();
""",
)

APPS["transbot"] = dict(
    emoji="🌐", title="المترجم الفوري", subtitle="ترجمة فورية بين 100+ لغة — مدعوم بـ MyMemory",
    interactive=True,
    body="""
<div class="card">
  <div style="display:flex;gap:8px;align-items:center">
    <select id="from" style="flex:1"><option value="ar">العربية</option><option value="en">English</option></select>
    <button class="btn secondary" style="width:auto;padding:8px 12px;margin:0" onclick="swap()">⇄</button>
    <select id="to" style="flex:1"><option value="en">English</option><option value="ar">العربية</option></select>
  </div>
  <label>النص</label><textarea id="txt" placeholder="اكتب النص هنا..."></textarea>
  <button class="btn" onclick="tr()">🌐 ترجم</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
function swap(){ const f=document.getElementById('from'), t=document.getElementById('to');
  [f.value,t.value]=[t.value,f.value]; }
async function tr(){
  const txt=document.getElementById('txt').value.trim();
  if(!txt) return Boda.toast('⚠️ اكتب نصاً');
  const f=document.getElementById('from').value, t=document.getElementById('to').value;
  const res=document.getElementById('res'); res.className='result show'; res.innerHTML='⏳...';
  Boda.haptic('light');
  try{
    const r=await fetch('https://api.mymemory.translated.net/get?q='+encodeURIComponent(txt)+'&langpair='+f+'|'+t);
    const d=await r.json();
    const out=d.responseData.translatedText;
    res.innerHTML='<div>'+out.replace(/</g,'&lt;')+'</div>'+
      '<button class="btn secondary" style="margin-top:8px" onclick="Boda.copy(document.getElementById(\\'res div\\').textContent)">📋 نسخ</button>';
    Boda.track('feature_use',{detail:f+'>'+t});
  }catch(e){ res.innerHTML='⚠️ تعذر الاتصال بخدمة الترجمة'; }
}
""",
)

APPS["doctrans"] = dict(
    emoji="📄", title="ترجمة المستندات", subtitle="ترجمة النصوص الطويلة والمقالات قطعة قطعة",
    interactive=True,
    body="""
<div class="card">
  <label>النص الطويل (حتى 4000 حرف)</label>
  <textarea id="txt" style="min-height:140px" placeholder="ألصق المقال كاملاً هنا..."></textarea>
  <div style="display:flex;gap:8px;margin-top:10px">
    <select id="from" style="flex:1"><option value="ar">من: العربية</option><option value="en">من: English</option></select>
    <select id="to" style="flex:1"><option value="en">إلى: English</option><option value="ar">إلى: العربية</option></select>
  </div>
  <button class="btn" onclick="tr()">📄 ترجمة كاملة</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
async function tr(){
  const txt=document.getElementById('txt').value.trim();
  if(!txt) return Boda.toast('⚠️ ألصق نصاً');
  if(txt.length>4000) return Boda.toast('⚠️ الحد 4000 حرف');
  const f=document.getElementById('from').value, t=document.getElementById('to').value;
  const res=document.getElementById('res'); res.className='result show'; res.innerHTML='⏳ جاري الترجمة...';
  try{
    const r=await fetch('https://api.mymemory.translated.net/get?q='+encodeURIComponent(txt)+'&langpair='+f+'|'+t);
    const d=await r.json();
    res.innerHTML='<div style="line-height:2">'+d.responseData.translatedText.replace(/</g,'&lt;')+'</div>'+
      '<button class="btn secondary" style="margin-top:10px" onclick="Boda.copy(document.getElementById(\\'res div\\').textContent)">📋 نسخ الترجمة</button>';
    Boda.track('feature_use',{detail:'doc_'+txt.length});
  }catch(e){ res.innerHTML='⚠️ فشل الاتصال'; }
}
""",
)

# ═════════════════════════════════ معلومات ═══════════════════════════════════

APPS["weathernow"] = dict(
    emoji="🌦️", title="الطقس الآن", subtitle="أجواء مدينتك — حرارة ورطوبة وتوقعات",
    interactive=True,
    body="""
<div class="card">
  <label>المدينة</label>
  <input type="text" id="city" placeholder="القاهرة، الرياض، دبي..." value="القاهرة">
  <div class="chips">
    <span class="chip" onclick="setCity('Cairo')">القاهرة</span>
    <span class="chip" onclick="setCity('Riyadh')">الرياض</span>
    <span class="chip" onclick="setCity('Dubai')">دبي</span>
    <span class="chip" onclick="setCity('Amman')">عمّان</span>
  </div>
  <button class="btn" onclick="load()">🔍 ابحث</button>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
function setCity(c){ document.getElementById('city').value=c; load(); }
async function load(){
  const c=document.getElementById('city').value.trim();
  if(!c) return Boda.toast('⚠️ اكتب مدينة');
  const res=document.getElementById('res'); res.className='result show'; res.innerHTML='⏳...';
  Boda.haptic('light');
  try{
    // wttr.in — بدون مفتاح API
    const r=await fetch('https://wttr.in/'+encodeURIComponent(c)+'?format=j1');
    const d=await r.json();
    const cur=d.current_condition[0];
    const desc={Sunny:'☀️ مشمس',Clear:'🌙 صافٍ',Partly cloudy:'⛅ غائم جزئياً',Cloudy:'☁️ غائم',
      'Light rain':'🌧️ مطر خفيف',Rain:'🌧️ مطر',Thunderstorm:'⛈️ عواصف رعدية','Light snow':'🌨️ ثلج خفيف'}[cur.weatherDesc[0].value]||cur.weatherDesc[0].value;
    res.innerHTML='<div style="font-size:38px">'+desc+'</div>'+
      '<div style="font-size:30px;font-weight:800">'+cur.temp_C+'°C</div>'+
      '<small style="color:var(--hint)">إحساس '+cur.FeelsLikeC+'° · رطوبة '+cur.humidity+'% · رياح '+cur.windspeedKmph+' كم/س</small>'+
      '<hr style="border-color:var(--hint);margin:12px 0">'+
      d.weather.slice(1,3).map(w=>'<div style="display:flex;justify-content:space-between"><span>📅 غداً+</span><span>'+w.mintempC+'° — '+w.maxtempC+'°</span></div>').join('');
    Boda.track('feature_use',{detail:'weather'});
  }catch(e){ res.innerHTML='⚠️ تعذر جلب الطقس — تحقق من اسم المدينة'; }
}
load();
""",
)

# ═════════════════════════════════ اختبارات/مهني ═════════════════════════════

APPS["personalityanalyzer"] = dict(
    emoji="🔮", title="محلل الشخصية", subtitle="أجب بصدق واكتشف نمط شخصيتك المهيمن",
    interactive=True,
    body="""
<div class="card"><div id="q-box"></div><div class="result" id="res" style="text-align:center"></div></div>
""",
    js="""
const QS=[
 {q:'في حفلة، عادةً تجدك...',o:['وسط الرقص 🔥','مع مجموعة صغيرة','بجوار الأكل 😅','أرصد من بعيد'],t:[3,2,1,0]},
 {q:'رسالة غامضة وصلتك، ردّك الأول؟',o:['أتصل فوراً','أرد بنكتة','أحلل كل كلمة','أتجاهل ساعة'],t:[3,2,1,0]},
 {q:'مشروع جماعي، دورك الطبيعي؟',o:['القائد','المنسّق','المدعم','المفكر الصامت'],t:[3,2,1,0]},
 {q:'قرار كبير في حياتك يعتمد على...',o:['حدسي الفوري','رأي المقربين','تحليل الأرقام','الظروف'],t:[3,1,2,0]},
 {q:'يوم مثالي لك يعني...',o:['مغامرة جديدة','لقاءات وأصدقاء','هدوء وكتاب','إنجاز مهام'],t:[3,2,0,1]}];
const TYPES=[
 {n:'القائد الكاريزمي',e:'🦁',d:'طاقة عالية وحضور قوي — الناس تتبعك تلقائياً'},
 {n:'الموج الاجتماعي',e:'🦋',d:'محبوب وفيه خفة دم — الاجتماعات تصير أحلى معاك'},
 {n:'المفكر الهادئ',e:'🦉',d:'عمق ونظرة مختلفة — حلولك تأتي من زاوية لا يراها أحد'},
 {n:'المنظّم الاستراتيجي',e:'🐝',d:'دقة وتنظيم — الأمور ما تضيع في يدك أبداً'}];
let i=0, t=0;
function render(){
  const q=QS[i];
  document.getElementById('q-box').innerHTML=
    '<small style="color:var(--hint)">سؤال '+(i+1)+'/'+QS.length+'</small>'+
    '<h2 style="margin:8px 0">'+q.q+'</h2>'+
    q.o.map((o,k)=>'<button class="btn secondary" onclick="pick('+k+')" style="text-align:right">'+o+'</button>').join('');
}
function pick(k){
  t+=q_t(i,k); Boda.haptic('light'); i++;
  if(i<QS.length) render(); else finish();
}
function q_t(i,k){ return QS[i].t[k]; }
function finish(){
  const idx=Math.min(3,Math.round(t/4));
  const ty=TYPES[idx];
  Boda.track('feature_use',{detail:'type_'+idx});
  document.getElementById('q-box').innerHTML='';
  const res=document.getElementById('res'); res.className='result show';
  res.innerHTML='<div style="font-size:54px">'+ty.e+'</div>'+
    '<h2>'+ty.n+'</h2><p style="color:var(--hint);margin:8px 0">'+ty.d+'</p>'+
    '<button class="btn secondary" onclick="Boda.share(\'شخصيتي: \'+\'\'+ty.e+\' '+ty.n+' 🔮 اكتشف شخصيتك!\',\'https://t.me/BodaPersonaBot\')">📤 شارك</button>'+
    '<button class="btn" onclick="location.reload()">🔁 إعادة</button>';
}
render();
""",
)

APPS["cvbuilder"] = dict(
    emoji="💼", title="منشئ السيرة الذاتية", subtitle="أدخل بياناتك واحصل على CV منسّق جاهز للنسخ",
    interactive=True,
    body="""
<div class="card">
  <label>الاسم والمسمى الوظيفي</label>
  <input type="text" id="nm" placeholder="أحمد محمد — مطوّر واجهات">
  <label>الملخص المهني (سطران)</label>
  <textarea id="sum" style="min-height:60px" placeholder="خبرة 3 سنوات في..."></textarea>
  <label>أهم 3 مهارات (سطر لكل مهارة)</label>
  <textarea id="skills" style="min-height:70px">JavaScript
React
تصميم UI</textarea>
  <label>أحدث خبرة</label>
  <input type="text" id="exp" placeholder="شركة X — 2022 حتى الآن">
  <button class="btn" onclick="build()">💼 توليد السيرة</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
function build(){
  const nm=document.getElementById('nm').value.trim(),
        sum=document.getElementById('sum').value.trim(),
        skills=document.getElementById('skills').value.split('\\n').map(s=>s.trim()).filter(Boolean),
        exp=document.getElementById('exp').value.trim();
  if(!nm) return Boda.toast('⚠️ اكتب اسمك ومسماك');
  Boda.haptic('success'); Boda.track('feature_use',{detail:'cv'});
  const cv='════════════════════\\n  '+nm+'\\n════════════════════\\n\\n📌 الملخص:\\n'+(sum||'—')+
    '\\n\\n🛠 المهارات:\\n'+skills.map(s=>'  • '+s).join('\\n')+
    '\\n\\n🏢 آخر خبرة:\\n  '+(exp||'—')+
    '\\n\\n▔▔▔▔▔▔\\n تم التوليد عبر متجر تطبيقات بودا 🏪';
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML='<pre style="white-space:pre-wrap;font-family:inherit;line-height:1.8">'+cv.replace(/</g,'&lt;')+'</pre>'+
    '<button class="btn secondary" onclick="Boda.copy(document.querySelector(\\'#res pre\\').textContent)">📋 نسخ السيرة كاملة</button>';
}
""",
)

APPS["logotext"] = dict(
    emoji="🎨", title="صانع الشعارات النصية", subtitle="شعار فوري لاسم مشروعك — 6 أنماط ألوان",
    interactive=True,
    body="""
<div class="card">
  <label>اسم البراند</label><input type="text" id="txt" placeholder="Boda Store" maxlength="14">
  <label>النمط</label>
  <div class="chips" id="styles"></div>
  <button class="btn" onclick="gen()">🎨 توليد الشعار</button>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
const STYLES=[['درجات زرقاء',['#0f2027','#203a43','#2c5364']],['غروب',['#ff512f','#dd2476','#f7971e']],
 ['بنفسجي ملكي',['#41295a','#2F0743','#56ab2f']],['نعناع',['#11998e','#38ef7d','#11998e']],
 ['ذهبي',['#3E2723','#7b4397','#dc2430']],['ليلي',['#141e30','#243b55','#141e30']]];
let si=0;
document.getElementById('styles').innerHTML=STYLES.map((s,k)=>
 '<span class="chip'+(k===0?' active':'')+'" onclick="pickS('+k+',this)">'+s[0]+'</span>').join('');
function pickS(k,el){ si=k; document.querySelectorAll('#styles .chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active'); }
function gen(){
  const t=document.getElementById('txt').value.trim()||'Boda';
  Boda.haptic('light');
  const c=STYLES[si][1];
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="360" height="120">'+
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'+
    '<stop offset="0" stop-color="'+c[0]+'"/><stop offset="1" stop-color="'+c[1]+'"/></linearGradient></defs>'+
    '<rect width="360" height="120" rx="18" fill="url(#g)"/>'+
    '<text x="180" y="72" font-family="Segoe UI,Arial" font-size="34" font-weight="800" '+
    'fill="#fff" text-anchor="middle">'+t.replace(/</g,'&lt;')+'</text></svg>';
  const url='data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(svg)));
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML='<img src="'+url+'" style="max-width:100%;border-radius:14px">'+
    '<button class="btn secondary" style="margin-top:10px" onclick="dl()">⬇️ تحميل PNG</button>';
  window._svg=svg; Boda.track('feature_use',{detail:'logo_'+si});
}
async function dl(){
  const img=new Image(); img.src='data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(window._svg)));
  img.onload=()=>{
    const cv=document.createElement('canvas'); cv.width=720; cv.height=240;
    const cx=cv.getContext('2d'); cx.drawImage(img,0,0,720,240);
    const a=document.createElement('a'); a.download='logo.png'; a.href=cv.toDataURL('image/png'); a.click();
    Boda.toast('⬇️ تم التحميل');
  };
}
""",
)

APPS["colorpick"] = dict(
    emoji="🌈", title="منتقي الألوان الذكي", subtitle="اختر لوناً واحصل على تدرجات متناسقة + أكواد HEX",
    interactive=True,
    body="""
<div class="card" style="text-align:center">
  <input type="color" id="pick" value="#5288c1"
    style="width:120px;height:120px;border:none;border-radius:999px;cursor:pointer;background:none">
  <p style="color:var(--hint);font-size:13px;margin:8px 0">اضغط الدائرة لاختيار اللون</p>
  <button class="btn" onclick="pal()">🌈 توليد الباليتة</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
function hex2rgb(h){ return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)]; }
function rgb2hex(r,g,b){ return '#'+[r,g,b].map(x=>Math.max(0,Math.min(255,Math.round(x))).toString(16).padStart(2,'0')).join(''); }
function shade(h,f){ const [r,g,b]=hex2rgb(h);
  return f<0? rgb2hex(r*(1+f),g*(1+f),b*(1+f)) : rgb2hex(r+(255-r)*f,g+(255-g)*f,b+(255-b)*f); }
function pal(){
  const base=document.getElementById('pick').value;
  const shades=[shade(base,-0.45),shade(base,-0.25),base,shade(base,0.3),shade(base,0.55),shade(base,0.8)];
  Boda.haptic('light'); Boda.track('feature_use',{detail:'palette'});
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML=shades.map(c=>
    '<div class="chip" style="width:100%;justify-content:center;display:flex;padding:14px;background:'+c+
    ';color:'+(parseInt(c.slice(1,3),16)>140?'#111':'#fff')+';font-weight:700;cursor:pointer" '+
    'onclick="Boda.copy(\\''+c+'\\')">'+c.toUpperCase()+'</div>').join('<div style="height:6px"></div>');
}
""",
)

APPS["backdrop"] = dict(
    emoji="🖼️", title="مولّد الخلفيات", subtitle="خلفيات تدرّج أنيقة بجودة عالية — جاهزة للتحميل",
    interactive=True,
    body="""
<div class="card">
  <label>الكلمات المفتاحية (اختياري — لتوجيه الألوان)</label>
  <input type="text" id="kw" placeholder="بحر، صحراء، فضاء...">
  <div class="chips">
    <span class="chip" onclick="kw2('فضاء')">🚀 فضاء</span>
    <span class="chip" onclick="kw2('بحر')">🌊 بحر</span>
    <span class="chip" onclick="kw2('غروب')">🌅 غروب</span>
    <span class="chip" onclick="kw2('غابة')">🌲 غابة</span>
  </div>
  <button class="btn" onclick="gen()">🖼️ توليد خلفية</button>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
const THEMES={فضاء:['#000428','#004e92'],بحر:['#2193b0','#6dd5ed'],
 غروب:['#355C7D','#f8b195'],غابة:['#134E5E','#71b280'],default:['#5288c1','#232e3c']};
function kw2(k){ document.getElementById('kw').value=k; gen(); }
let _url='';
function gen(){
  const k=document.getElementById('kw').value.trim();
  const th=THEMES[k]||THEMES.default;
  // تدرّج فني بزوايا عشوائية
  const a=Math.floor(Math.random()*360);
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="720" height="1280">'+
   '<defs><linearGradient id="g" gradientTransform="rotate('+a+' .5 .5)">'+
   '<stop offset="0" stop-color="'+th[0]+'"/><stop offset="1" stop-color="'+th[1]+'"/></linearGradient></defs>'+
   '<rect width="720" height="1280" fill="url(#g)"/>'+
   Array.from({length:14},(_,i)=>{const x=Math.random()*720,y=Math.random()*1280,r=30+Math.random()*120;
     return '<circle cx="'+x+'" cy="'+y+'" r="'+r+'" fill="#ffffff" opacity="0.05"/>';}).join('')+
   '</svg>';
  _url='data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(svg)));
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML='<img src="'+_url+'" style="max-height:280px;border-radius:14px">'+
    '<button class="btn secondary" style="margin-top:10px" onclick="dl()">⬇️ تحميل الخلفية</button>';
  Boda.track('feature_use',{detail:'backdrop_'+(k||'random')});
}
function dl(){
  const img=new Image(); img.src=_url;
  img.onload=()=>{ const cv=document.createElement('canvas'); cv.width=720; cv.height=1280;
    cv.getContext('2d').drawImage(img,0,0);
    const a=document.createElement('a'); a.download='wallpaper.png'; a.href=cv.toDataURL('image/png'); a.click();
    Boda.toast('⬇️ تم التحميل'); };
}
""",
)

APPS["photoboost"] = dict(
    emoji="📸", title="محسّن الصور", subtitle="فلتر جماليات + تحويل لصيغ — كل شيء داخل جهازك",
    interactive=True,
    body="""
<div class="card">
  <label>اختر صورة من جهازك</label>
  <input type="file" id="file" accept="image/*" style="margin-top:6px">
  <label>الفلتر</label>
  <div class="chips">
    <span class="chip active" data-f="none" onclick="pickF(this)">أصلي</span>
    <span class="chip" data-f="grayscale(1)" onclick="pickF(this)">أبيض وأسود</span>
    <span class="chip" data-f="sepia(.7)" onclick="pickF(this)">سيبيا قديم</span>
    <span class="chip" data-f="saturate(1.6) contrast(1.1)" onclick="pickF(this)">ألوان صاخبة</span>
    <span class="chip" data-f="brightness(1.15) saturate(1.2)" onclick="pickF(this)">مشرق</span>
    <span class="chip" data-f="blur(1.5) saturate(1.3)" onclick="pickF(this)">حالم</span>
  </div>
  <button class="btn" onclick="dl()" disabled id="dl">⬇️ تحميل الصورة المعدلة</button>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
let filter='none', img=null;
function pickF(el){ document.querySelectorAll('.chips .chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active'); filter=el.dataset.f;
  if(img) apply(); }
document.getElementById('file').onchange=e=>{
  const f=e.target.files[0]; if(!f) return;
  img=new Image(); img.onload=apply;
  img.src=URL.createObjectURL(f);
  Boda.track('feature_use',{detail:'photo_uploaded'});
};
function apply(){
  const cv=document.createElement('canvas');
  const MAX=1080, sc=Math.min(1,MAX/Math.max(img.width,img.height));
  cv.width=img.width*sc; cv.height=img.height*sc;
  const cx=cv.getContext('2d');
  cx.filter=filter; cx.drawImage(img,0,0,cv.width,cv.height);
  const url=cv.toDataURL('image/png');
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML='<img src="'+url+'" style="max-width:100%;border-radius:12px">';
  document.getElementById('dl').disabled=false;
  window._url=url;
}
function dl(){ const a=document.createElement('a'); a.download='boosted.png'; a.href=window._url; a.click();
  Boda.toast('⬇️ تم التحميل'); Boda.haptic('success'); }
""",
)

# ═════════════════════════════════ أخرى ══════════════════════════════════════

APPS["birth_age"] = dict(
    emoji="🎂", title="حاسبة العمر الدقيقة", subtitle="عمرك بالسنين والشهور والأيام — وحتى نَفَسك 😄",
    interactive=True,
    body="""
<div class="card">
  <label>تاريخ ميلادك</label><input type="date" id="bd">
  <button class="btn" onclick="calc()">🎂 احسب عمري</button>
  <div class="result" id="res" style="text-align:center"></div>
</div>
""",
    js="""
function calc(){
  const v=document.getElementById('bd').value;
  if(!v) return Boda.toast('⚠️ اختر تاريخ ميلادك');
  const b=new Date(v), now=new Date();
  if(b>now) return Boda.toast('🤨 من المستقبل؟');
  let y=now.getFullYear()-b.getFullYear(), m=now.getMonth()-b.getMonth(), d=now.getDate()-b.getDate();
  if(d<0){ m--; d+=new Date(now.getFullYear(),now.getMonth(),0).getDate(); }
  if(m<0){ y--; m+=12; }
  const days=Math.floor((now-b)/864e5);
  Boda.haptic('success'); Boda.track('feature_use',{detail:'age'});
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML=
    '<div style="font-size:34px;font-weight:800;color:var(--accent)">'+y+' سنة و'+m+' شهر و'+d+' يوم</div>'+
    '<hr style="border-color:var(--hint);margin:12px 0">'+
    '<p style="line-height:2.1;font-size:14px">📅 عشت حتى الآن <b>'+days.toLocaleString()+'</b> يوم<br>'+
    '🫀 قلبك ضرب ~ <b>'+(days*24*60*75).toLocaleString()+'</b> مرة<br>'+
    '😴 نمت ~ <b>'+Math.round(days/3).toLocaleString()+'</b> يوم<br>'+
    '🌍 دارت حول الشمس <b>'+y+'</b> مرة</p>';
}
document.getElementById('bd').value='2000-01-01';
""",
)

APPS["textspeak"] = dict(
    emoji="🔤", title="محوّل أنماط الكتابة", subtitle="عربي مضغوط، عشوائي مائل، رموز جمالية...",
    interactive=True,
    body="""
<div class="card">
  <label>النص</label><textarea id="txt" placeholder="اكتب أي نص..."></textarea>
  <div class="chips">
    <span class="chip" onclick="conv(1)">𝓖وثيرك</span>
    <span class="chip" onclick="conv(2)">‌‌مـ‌‌تـ‌‌و‌‌س‌‌ط مفرّغ</span>
    <span class="chip" onclick="conv(3)">UPPER عشوائي</span>
    <span class="chip" onclick="conv(4)">مقلوب</span>
  </div>
  <div class="result" id="res"></div>
</div>
""",
    js="""
const FANCY={a:'𝓪',b:'𝓫',c:'𝓬',d:'𝓭',e:'𝓮',f:'𝓯',g:'𝓰',h:'𝓱',i:'𝓲',j:'𝓳',k:'𝓴',l:'𝓵',m:'𝓶',n:'𝓷',o:'𝓸',p:'𝓹',q:'𝓺',r:'𝓻',s:'𝓼',t:'𝓽',u:'𝓾',v:'𝓿',w:'𝔀',x:'𝔁',y:'𝔂',z:'𝔃'};
function conv(mode){
  const t=document.getElementById('txt').value.trim();
  if(!t) return Boda.toast('⚠️ اكتب نصاً');
  let out='';
  if(mode===1) out=[...t].map(c=>FANCY[c.toLowerCase()]||c).join('');
  if(mode===2) out=[...t].join('\\u200a');
  if(mode===3) out=[...t].map(c=>Math.random()<.5?c.toUpperCase():c.toLowerCase()).join('');
  if(mode===4) out=[...t].reverse().join('');
  Boda.haptic('light');
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML='<div style="font-size:17px;line-height:2">'+out.replace(/</g,'&lt;')+'</div>'+
    '<button class="btn secondary" onclick="Boda.copy(document.getElementById(\\'res div\\').textContent)">📋 نسخ</button>';
  Boda.track('feature_use',{detail:'style_'+mode});
}
""",
)

APPS["silentcut"] = dict(
    emoji="🔇", title="قصادم الصوت الصامت", subtitle="معالجة صوتية داخل جهازك — قريباً بمكتبة كاملة",
    interactive=False,
    body="""
<div class="card" style="text-align:center">
  <div style="font-size:64px">🔇</div>
  <h2 style="margin:10px 0">نسخة الويب قيد التطوير</h2>
  <p style="color:var(--hint);line-height:2;font-size:14px">
    إزالة الصمت من الفيديوهات تحتاج معالجة ثقيلة تعمل حالياً عبر البوت نفسه.<br>
    <b>أرسل فيديوك للبوت الآن وسيحدثك خلال دقائق!</b></p>
  <button class="btn" onclick="location.href='https://t.me/BodaSilentCutBot'">🤖 فتح البوت مباشرة</button>
</div>
""",
    js="""
Boda.track('app_open',{detail:'landing'});
""",
)

APPS["cleantok"] = dict(
    emoji="🎵", title="تيك توك بلا علامة", subtitle="أرسل الرابط للبوت واستلم الفيديو نظيفاً",
    interactive=False,
    body="""
<div class="card">
  <label>رابط فيديو تيك توك</label>
  <input type="text" id="url" dir="ltr" placeholder="https://vm.tiktok.com/...">
  <button class="btn" id="go" onclick="send()">🤖 أرسل للبوت</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
function send(){
  const u=document.getElementById('url').value.trim();
  if(!/tiktok\\.com/i.test(u)) return Boda.toast('⚠️ أدخل رابط تيك توك صحيح');
  Boda.haptic('light'); Boda.track('feature_use',{detail:'link_prepared'});
  // الفيديو الثقيل يُعالج في البوت — ننقله إليه مع الرابط جاهزاً
  Boda.copy(u, '📋 تم نسخ الرابط');
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML=
    '✅ نُسخ الرابط! الآن:<br>1️⃣ افتح البوت<br>2️⃣ أرسل الرابط (لصق)'+
    '<button class="btn" onclick="location.href=\\'https://t.me/BodaCleanTokBot\\'">🤖 فتح البوت</button>';
}
""",
)

APPS["vidload"] = dict(
    emoji="📥", title="محمل الفيديوهات", subtitle="يوتيوب وإنستغرام — عبر البوت بجودة عالية",
    interactive=False,
    body="""
<div class="card">
  <label>رابط الفيديو</label>
  <input type="text" id="url" dir="ltr" placeholder="https://youtube.com/...">
  <button class="btn" id="go" onclick="send()">🤖 أرسل للبوت</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
function send(){
  const u=document.getElementById('url').value.trim();
  if(!/youtube|youtu\\.be|instagram/i.test(u)) return Boda.toast('⚠️ أدخل رابط يوتيوب أو إنستغرام');
  Boda.haptic('light'); Boda.track('feature_use',{detail:'link_prepared'});
  Boda.copy(u, '📋 تم نسخ الرابط');
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML=
    '✅ نُسخ الرابط! افتح البوت وألصقه ليصلك الفيديو'+
    '<button class="btn" onclick="location.href=\\'https://t.me/BodaVidLoadBot\\'">🤖 فتح البوت</button>';
}
""",
)

APPS["stickerx"] = dict(
    emoji="🎨", title="صانع الملصقات", subtitle="حوّل صورك إلى ملصقات تيليجرام — عبر البوت",
    interactive=False,
    body="""
<div class="card" style="text-align:center">
  <div style="font-size:64px">🎨</div>
  <h2 style="margin:10px 0">صناعة الملصقات عبر البوت</h2>
  <p style="color:var(--hint);line-height:2;font-size:14px">
    أرسل أي صورة للبوت وسيحولها لملصق بحجم تيليجرام الرسمي (512px) ويفصل الخلفية تلقائياً</p>
  <button class="btn" onclick="location.href='https://t.me/BodaStickerXBot'">🤖 فتح البوت</button>
</div>
""",
    js="""
Boda.track('app_open',{detail:'landing'});
""",
)

APPS["formatfix"] = dict(
    emoji="🧹", title="منظّم النصوص", subtitle="تنظيف المسافات والرموز — لصق نظيف بضغطة",
    interactive=True,
    body="""
<div class="card">
  <label>النص الفوضوي</label>
  <textarea id="txt" style="min-height:120px" placeholder="ألصق نصاً فيه مسافات زائدة وأسطر مكسورة..."></textarea>
  <div class="chips">
    <span class="chip" onclick="fix(1)">تنظيف كامل</span>
    <span class="chip" onclick="fix(2)">سطر واحد</span>
    <span class="chip" onclick="fix(3)">إزالة إيموجي</span>
  </div>
  <div class="result" id="res"></div>
</div>
""",
    js="""
function fix(mode){
  let t=document.getElementById('txt').value;
  if(!t.trim()) return Boda.toast('⚠️ ألصق نصاً');
  if(mode===1) t=t.replace(/[ \\t]+/g,' ').replace(/\\n{3,}/g,'\\n\\n').trim();
  if(mode===2) t=t.replace(/\\s*\\n\\s*/g,' ').replace(/ {2,}/g,' ').trim();
  if(mode===3) t=t.replace(/[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}\\u{FE0F}]/gu,'').trim();
  Boda.haptic('light');
  document.getElementById('res').className='result show';
  document.getElementById('res').innerHTML='<div style="line-height:1.9">'+t.replace(/</g,'&lt;')+'</div>'+
    '<button class="btn secondary" style="margin-top:8px" onclick="Boda.copy(document.getElementById(\\'res div\\').textContent)">📋 نسخ</button>';
  Boda.track('feature_use',{detail:'fix_'+mode});
}
""",
)

APPS["memory"] = dict(
    emoji="🧠", title="لعبة الذاكرة", subtitle="اختبر ذاكرتك — تذكر التسلسل المتزايد",
    interactive=True,
    body="""
<div class="card" style="text-align:center">
  <div id="seq" style="font-size:34px;min-height:60px;letter-spacing:8px">اضغط ابدأ</div>
  <input type="text" id="inp" placeholder="اكتب التسلسل الذي رأيته" style="margin-top:10px;text-align:center">
  <button class="btn" onclick="start()">▶ ابدأ (المستوى 1)</button>
  <div class="result" id="res"></div>
</div>
""",
    js="""
let level=1, seq='', showing=false;
function start(){
  level=1; next();
}
function next(){
  seq=''; for(let i=0;i<level+2;i++) seq+=Math.floor(Math.random()*10);
  showing=true;
  const el=document.getElementById('seq');
  el.textContent='⏳ تذكر...';
  setTimeout(()=>{
    el.textContent=seq;
    setTimeout(()=>{
      el.textContent='✏️ اكتبه الآن!';
      showing=false;
      document.getElementById('inp').value=''; document.getElementById('inp').focus();
    }, 800+level*300);
  },600);
}
document.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!showing&&document.getElementById('inp').value) check();
});
function check(){
  const v=document.getElementById('inp').value.trim();
  if(!v) return;
  if(v===seq){
    level++; Boda.haptic('success'); Boda.track('feature_use',{detail:'level_'+level});
    document.getElementById('seq').textContent='✅ صحيح! المستوى '+level;
    document.getElementById('res').className='result';
    setTimeout(next,1200);
  } else {
    Boda.haptic('error');
    document.getElementById('res').className='result show';
    document.getElementById('res').innerHTML=
      '❌ الخزانة كانت: <b>'+seq+'</b><br>وصلت للمستوى <b>'+level+'</b>'+
      '<br><button class="btn" onclick="start()">🔁 حاول مجدداً</button>';
    document.getElementById('seq').textContent='انتهت اللعبة';
  }
}
""",
)
