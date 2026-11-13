# نظام تصميم Boda — المرحلة 0 و1

> آخر تحديث: 2026-11-11 · الفرع: `feature/ad-publish`

## 1) نتيجة الجرد (المرحلة 0)

| القياس | قبل | بعد |
|---|---|---|
| عدد صفحات Mini Apps | 34 | 34 |
| متوسط حجم الصفحة | 16.0 KB | ~41 KB |
| إجمالي الصفحات | 545 KB | ~1.4 MB (مولّدة) |
| خط عربي محلي | ❌ لا يوجد (Segoe UI/Tahoma) | ✅ Cairo متغيّر 400–800 |
| `prefers-reduced-motion` | 0 صفحة | ✅ كل الصفحات |
| MainButton / BackButton | 0 | ✅ SDK جاهز |
| CloudStorage | 0 | ✅ مع بديل localStorage |
| التحقق من `initData` | غير موجود | ✅ يُرسل مع التتبع و`Boda.api` |
| ألوان Hex داخل الصفحة | ~12 متوسط | ✅ Tokens مركزية |
| JavaScript مكسور | 9 تطبيقات | ✅ 0 (فُحصت 34 صفحة عبر Node) |

### أهم ما اكتُشف
- القالب كان مركزيًا بالفعل (`tools/app_template.py`)، لكن بلا هوية بصرية
  للمجموعات وبلا خط عربي محلي وبلا حركات محترمة لتقليل الحركة.
- 9 تطبيقات كانت **معطّلة بالكامل** بسبب علامات اقتباس غير مهربة في أزرار
  `Boda.share` و`weathernow` (مفتاح `Partly cloudy` غير مقتبس):
  `shortlink, lovecalculator, mentalage, iqtest, luckybox, braintwist,
  fun_name, random_suggest, personalityanalyzer, weathernow`.
- الإعلان البيني كان يظهر **عند فتح التطبيق** (أول استخدام)، وهو مخالف
  لقاعدة حماية التجربة.
- البانر لم يكن ثابتًا أسفل الشاشة، ولا يراعي `safe-area` في iPhone.

## 2) ملفات النظام (المرحلة 1)

```
tools/
  ds_tokens.py       # الألوان/الخط/المسافات/الظلال/الحركة + هوية كل مجموعة
  ds_components.py   # مكتبة المكونات + keyframes + reduced-motion
  ds_sdk.py          # Telegram SDK + الإعلانات + التتبع
  design_system.py   # نقطة الدخول: build_css(tag, bot_id) / brand()
  app_template.py    # يستهلك النظام ويولّد الصفحة (نفس العقد القديم)
```

### الهوية اللونية للمجموعات
| المجموعة | اللون | الاستخدام |
|---|---|---|
| أدوات | `#3b82f6` أزرق | currency, cashier, qrgen… |
| وسائط | `#8b5cf6` بنفسجي | vidload, cleantok, stickerx… |
| ترفيه/اختبارات | `#f97316` برتقالي | iqtest, luckybox, braintwist… |
| صحة | `#22c55e` أخضر | fitcheck, caltrack, birth_age |
| نصوص/ترجمة | `#14b8a6` تركوازي | transbot, cvbuilder, doctrans |
| متجر | `#eab308` ذهبي | store |

الألوان تُحقن تلقائيًا من `tag` البوت في `bots_registry.json`، وتبقى
متوافقة مع `Telegram.WebApp.themeParams` (فاتح/داكن).

### الخط
- `Cairo` متغيّر الوزن (400–800)، عربي + لاتيني، محلي في:
  - `webroot/assets/fonts/`
  - `webapps/assets/fonts/`
  - `assets/fonts/` (للنسخ المستقلة)
- `font-display: swap` + `preload` + `unicode-range` لتقليل أثر التحميل.
- الوزن الكلي للخطين ≈ 65 KB.

### المكونات الجاهزة
`.card`, `.btn` (أساسي/ثانوي/شبح/خطر/صغير/تحميل), حقول `.field`,
`.chips`, `.segmented`, `.list-item`, `.stat-grid`, `.badge`,
`.progress` (+ غير محدد), `.skeleton`, `.empty`, `.result`,
`.sheet` (ورقة سفلية), `.toast`, `.ad-banner`, `.sponsor-card`,
`.stagger` للظهور المتتابع.

### الحركة
- انتقالات `transform/opacity` فقط.
- `@media (prefers-reduced-motion: reduce)` يوقف كل الحركات.
- مدة قصيرة (120–380ms) ومنحنى `cubic-bezier(.22,.8,.28,1)`.

## 3) تكامل Telegram SDK

متاح عبر `window.Boda`:

```js
Boda.MainButton.set('تحويل', () => convert());
Boda.MainButton.progress(true);
Boda.BackButton.show(() => history.back());
Boda.haptic('success');
Boda.Cloud.set('last_result', value);      // CloudStorage + fallback
Boda.share('نتيجتي…', 'https://t.me/Bot');
Boda.api('/api/secure', { ... });          // يضيف initData تلقائيًا
```

- `Boda.track` يرسل `init_data` مع كل حدث (للتحقق الخادمي مستقبلًا).
- `Boda.Ad.afterResult()` هو نقطة العرض البيني الوحيدة.

## 4) مواضع الإعلانات (من التصميم)

1. **بانر ثابت أسفل الشاشة**: `.ad-banner`، يحترم `safe-area`،
   قابل للإغلاق في الجلسة، ولا يغطي المحتوى (`--bd-banner-h`).
2. **إعلان بيني بعد النتيجة فقط**: يُشغَّل تلقائيًا عند إضافة
   `show` إلى أي `.result` (MutationObserver)، كل `N` نتيجة، مع عدّاد
   3 ثوانٍ قبل «متابعة»، وبحد أقصى مرة كل 90 ثانية.
3. لا يظهر أي إعلان عند فتح التطبيق أو أثناء العملية.

## 5) ضبط الإعلانات عمليًا

### من لوحة الويب (الأسهل)
1. شغّل `python api_server.py`.
2. افتح `http://127.0.0.1:8080/dashboard`.
3. تبويب **📢 الإعلانات** → اختر البوت.
4. أدخل `Direct Link` أو `Zone ID` (أو `Script URL`)، اختر الصيغة
   والتكرار، ثم **حفظ وإعادة توليد الصفحات**.
5. الحفظ يحدّث `Data/monetag_config.json` ويعيد توليد كل صفحات HTML.

### من Manager.py
زر الإعلانات في بطاقة كل بوت يفتح نفس الإعدادات.

### عبر API
```bash
curl -X POST http://127.0.0.1:8080/api/ads/set \
  -H "Content-Type: application/json" \
  -d '{"bot_id":"currency","direct_link":"https://...","format":"direct_link","frequency":3,"active":true}'
```

## 6) الأداء

- الصفحة الأولى: ~41 KB HTML + 65 KB خطوط = ~106 KB (دون سكربت تيليجرام
  الخارجي المخزّن مؤقتًا) → ضمن ميزانية 150 KB.
- لا صور نقطية في القالب؛ الأيقونات إيموجي و SVG مدمج.
- الحركة على `transform/opacity` فقط.

## 7) الخطوات التالية

- **المرحلة 2**: تحسين 3 بوتات نموذجية يدويًا (currency/vidload/iqtest)
  باستخدام `MainButton` وبطاقة نتيجة + مشاركة.
- **المرحلة 3**: تعميم المكونات على بقية التطبيقات مجموعةً مجموعة.
- **المرحلة 4**: أوصاف BotFather + الأوامر + صور الوصف + Menu Button.
- **المرحلة 5**: Playwright + Lighthouse + اختبارات إتاحة وأداء.
