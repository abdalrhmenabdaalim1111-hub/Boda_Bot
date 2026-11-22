# Boda Bot System — معمارية النظام (Architecture)

## نظرة عامة
منظومة متكاملة: **34 بوت تيليجرام** + **33 تطبيقاً مصغّراً (Mini Apps)** + **متجر** + **لوحة تحكم**.
كل شيء يعمل من منفذ واحد `8080` عبر `Start_Boda.bat`.

## المكونات الأساسية
| المكون | الملف | الدور |
|---|---|---|
| سجل البوتات | `bots_registry.json` | مصدر الحقيقة للأسماء/الأوصاف/الفئات/الروابط |
| كتالوج المتجر | `Bots_Folder/store_catalog.py` | الفئات، الترتيب، استبعاد بوت المتجر |
| بوت المتجر | `Bots_Folder/bot_store.py` | واجهة تيليجرام: فئات، بحث، تفاصيل، إحصاءات |
| بوابة الاشتراك | `Bots_Folder/gate_check.py`, `gate_middleware.py` | `@Stick_boda` + `@ebdo_4`، فحص فوري |
| طبقة موحّدة | `Bots_Folder/unified_middleware.py` | تُركّب على كل بوت: gate، تتبع، /about، /app |
| تعريفات التطبيقات | `tools/app_defs.py` | JS/HTML لكل تطبيق + شفرات Monetag |
| قالب التطبيق | `tools/app_template.py` |壳 موحد: DS SDK، بانر، مشاركة، Flashing Ads |
| نظام التصميم | `tools/ds_tokens.py`, `ds_components.py`, `ds_sdk.py` | ألوان، مكونات، SDK |
| مولّد الويب | `tools/build_mini_apps.py` | يبني `webroot/` (تطبيقات + متجر + لوحة) |
| لوحة التحكم | `tools/dashboard_template.py` | إدارة البوتات + تحليلات + أداء الإعلانات |
| API | `api_server.py`, `control_center/api.py` | خدمات محلية + حماية مفتاح |
| قاعدة البيانات | `Bots_Folder/database.py` | مستخدمون، أحداث، إعلانات، A/B |

## تدفق البناء
```
bots_registry.json + app_defs.py + app_template.py
        ↓  python tools/build_mini_apps.py
webroot/<id>/index.html  (33 تطبيق)
webroot/store/index.html (متجر)
webroot/dashboard/index.html (لوحة)
webroot/data/catalog.json + stats.json
        ↓  api_server.py على :8080
/apps/<id>/  ·  /apps/store/  ·  /dashboard/
```

## الإعلانات
- **Monetag فيديو (Interstitial):** `show_<zone>()` عند `uses % 2 === 0` في كل تطبيق.
- **بانر ثابت:** `window.__BODA_ADS__.banner` أسفل الشاشة بمساحة آمنة (`--bd-banner-h`).
- **Flashing Ads:** وميض قصير قبل الإعلان (في `app_template.py`).
- **IntersectionObserver:** البانر يظهر فقط عند ظهور التطبيق.
- **لوحة الأداء:** Dashboard ← التحليلات ← لوحة أداء الإعلانات (KPI + رسم + جدول).

## التوسيع (Scalability)
لإضافة بوت جديد:
1. أضف إدخالاً إلى `bots_registry.json` (id, emoji, name, description, features, category_key, url).
2. أضف `APPS["<id>"]` إلى `tools/app_defs.py` مع `loadMonetag('<zone>')` + `showAd()`.
3. أضف الزون إلى `Data/monetag_config.json`.
4. شغّل `python tools/build_mini_apps.py`.

كل البقية (المتجر، اللوحة، البوابة، البانر) تتحدث تلقائياً.

## الأمان
- بوابة القناتين مفعّلة على كل الرسائل والأزرار (`use_cache=False`).
- API يتطلب `X-API-Key` من `Data/.local_admin_token` للطلبات الحساسة.
- `.env` و`Data/` محليان وغير مرفوعين إلى GitHub.
