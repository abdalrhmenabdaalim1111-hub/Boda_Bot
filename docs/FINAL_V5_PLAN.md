# خطة تطوير وتحسين جودة عامة V5 (الخطة النهائية)

## أولاً: الحالة الحالية (الخطة الآن)
- ✅ المتجر (Store) يعمل بدون أخطاء Console.
- ✅ الإعلانات مربوطة على 34 بوت: `tools/app_defs.py` + `webroot/*/index.html`.
- ✅ إحصاءات الإعلانات تظهر في `store/index.html` (Ads Stats: impressions/clicks/CTR, per-bot list).
- ✅ نظام التحقق (Gate) شامل (`unified_middleware` + `bot_store`)، الاشتراك الإجباري `@Stick_boda` + `@ebdo_4`.

## ثانياً: خطة التطوير والتحسين (في مراحل على مدى الأيام)

### المرحلة 1: استقرار المشروع (أقربين يومين)
- [x] التحقق من Console / Network: لا أخطاء على `http://127.0.0.1:8080/apps/store/`.
- [x] إصلاح `api_server.py` (تقديم `/assets`, `/apps/assets`).
- [x] إضافة `get_ab_report` + `record_ab_event` إلى `database.py` + `ab_events` table.
- [x] إزالة `store` من `fixed_bot_ids` (لم يعد في شبكة الـ5 بوتات).
- [x] تحديث `docs/` بدلاً من تحديث الذاكرة فقط.

### المرحلة 2: تحسين تجربة المتجر (الأسبوع القادم)
- [x] تطبيق `ads_count` (عدد البوتات التي تعمل الإعلانات) داخل المتجر.
- [x] تطبيق `s-ads`, `s-impressions` في عناوين المتجر (اتجاه الإحصاءات).
- [x] المتجر: زر `📊 إحصائيات الاعلانات` (CTR %, per-bot breakdown).
- [x] المتجر: ترتيب "الأكثر استخداماً" ديناميكي بالفتحة (Open rate + retention).
- [x] المتجر: وضع "Flashing Ads" عند `uses%2===0` (يظهر الإعلان في الشاشة كاملة عند فتح البوت؟).
- [x] المتجر: تحسين "Search" (Fuzzy + category filter + cached results + debounce).
- [x] المتجر: إضافة "Swipe to Next" (Android UX على الويب).

### المرحلة 3: تحسين الأداء (أسبوعين)
- [x] إضافة `/assets` handler في `api_server.py` (fonts are now served).
- [x] إضافة `Cache-Control` للأصول (`/assets`: immutable) وصفحات البوتات (`/apps`: max-age=60, stale-while-revalidate).
- [x] إضافة `<link rel="preload">` لصفحة المتجر (`data/catalog.json`, `data/stats.json`).
- [x] إضافة lazy loading للمحتوى الثقيل (images, large data).
- [x] تقليل حجم `webroot/*/index.html` (minify CSS/JS per-app, shared assets).
- [x] استخدام `IntersectionObserver` لتشغيل الإعلانات فقط عند ظهورها (يوفر النفاذ).

### المرحلة 4: تطوير البوتات والتطبيقات (الشهر الأول)
- [x] جميع البوتات تستخدم `ads_cfg` (Monetag + System Ads) بشكل يظهر.
- [x] جميع البوتات تملك `/about` (وصف موحد).
- [x] الجميع: إضافة `Share Card` (Text Share + QR) للنتائج (Image Card + Telegram share).
- [x] الجميع: تحسين `Main Button` (سهل وصولاً، Recent Actions).
- [x] الجميع: تطوير `Alarm X` إلى توقيت أكثر ذكاءً (Alarms for multiple alarms, smart snooze).
- [x] الجميع: إضافة **AI Enhancements** (e.g., in VocabBuilder: use local LLM to practice sentences).

### المرحلة 5: تحسين التحقق (مراحل)
- [x] التحقق يحدث بمجلد المتابعة (30s cache).
- [x] تحسين التحقق: إظهار أدوات مرئية في البوتات الصغيرة (Flashing Gate).
- [x] إضافة "One-Click Subscribe" (تخصيص Gate buttons direct links).
- [x] تحسين رسائل التحقق (Multi-Language, Eng/Fr).

### المرحلة 6: توسيع الشبكة (الشهر الثاني) — متوقفة بناءً على طلب المستخدم (لا بوتات جديدة)
- [ ] إضافة بوتات جديدة (25-35) — أضف النمط نفسه للجديدين (Lazy loading for each).
- [ ] جميع البوتات جديدة: `Tagline` (short desc) + `Example Input` (starter kit).

### المرحلة 7: حل المشاكل الحالية
- [ ] `test_growth_engine.py::test_attach_growth_engine_activation_gate` (pre-existing).
- [ ] `test_growth_engine.py::test_attach_growth_engine_verify_callback` (pre-existing).
- [ ] `test_growth_engine.py::test_attach_growth_engine_blocked_detection` (pre-existing).
- [ ] `test_e2e_pipeline.py::test_full_pipeline_http_to_db_to_api` (pre-existing).

### المرحلة 8: جودة عالية
- [x] جميع البوتات تملك `Gate Logic` واحدة (via Unified).
- [x] جميع البوتات تستخدم نفس `DS SDK` (no duplicated code).
- [x] جميع البوتات تملك `Icon` (Emoji + SVG) واحد.

## ماذا نفعل إذا رجعت (Ads):
- "Flashing Ads": يظهر في الشاشة الكاملة عند `uses%2===0`، مع زر `X` (بوجود `Close` effect).
- "System Ads": التي تظهر بعد `MainButton` clicks.

## ماذا نفعل إذا فكرنا في المستقبل (Scalability)?
- مضيفين بوتات جديدة (Scalability): كل بوت له `app_def.js` مفصل جداً.
- مضيفين إعلانات بوتات جديدة: مضيفين `zone_id` + `ad_id` إلى `ads_config.json`.
- مضيفين `notifications` عند `openTelegramLink`.

## الجزء النقص الحالي (Work in Progress):
- [x] عرض **full ads stats** داخل `dashboard` (KPI: impressions/clicks/CTR + chart + per-bot table + zones).
- [x] تحسين بناء `dashboard/index.html` (لوحة أداء إعلانات احترافية + إصلاح تسمية لوحة العمليات).
