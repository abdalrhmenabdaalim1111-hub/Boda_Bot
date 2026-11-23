# 🃏 بوت بطاقات بالاسم — namecards

بوت مدمج في منظومة Boda (ليس مشروعاً منفصلاً).

## ما هو X-API-Key؟
هو **مفتاح حماية لوحة التحكم/الـ API** (ليس توكن البوت). موجود في `.env` كسطر:
```
API_SERVER_KEY=boda_xxxxx...
```
- الأسهل: أرسل `/admin` للبوت من حساب أدمن → يفتح اللوحة ويُدخل المفتاح تلقائياً.
- أو افتح `http://127.0.0.1:8080/admin/namecards.html?key=<API_SERVER_KEY>`.
- يُحفظ المفتاح في `localStorage` فقط، ويمكن حذفه بزر «خروج».

## التشغيل
1. أضف التوكن إلى `.env`:
   ```
   NAMECARDS_BOT_TOKEN=<token from @BotFather>
   ```
2. أعد بناء الويب: `python tools/build_mini_apps.py`
   (ينسخ `ui/namecards/index.html` → `webroot/namecards/` و`admin.html` → `webroot/admin/namecards.html`)
3. شغّل النظام: `Start_Boda.bat` (البوت يُبدأ تلقائياً عبر Supervisor).
4. افتح التطبيق: `http://127.0.0.1:8080/apps/namecards/`
5. صفحة الأدمن (محمية بمفتاح API):
   `http://127.0.0.1:8080/admin/namecards.html?key=<API_SERVER_KEY>`

## رفع قالب جديد
من صفحة الأدمن:
- معرّف القالب، اسم العرض، صورة (PNG/JPG/WebP ≤ 10MB).
- `name_box`: `[x, y, w, h]` بالإكسل داخل الصورة ( роста النص يتصغر تلقائياً).
- `name2_box` للقوالب ذات الاسمين، خيارات العلامة المائية والتفعيل.

القوالب تُحفظ في `Data/namecards/templates/<id>.png` + `<id>.json`.

## الأوامر
- `/start` — ترحيب + زر التطبيق (وتسجيل `ref_` إن وُجد).
- `/help` — المساعدة.
- `/mycards` — آخر 5 بطاقات للمستخدم.

## الأمان
- تحقق HMAC من `initData` بمفتاح البوت.
- حد معدل لكل مستخدم، و30 حرفاً كحد أقصى للاسم، وتنقية الرموز غير المرئية.
- مسارات الأدمن تتطلب `X-API-Key`.
- الإحصائيات تستخدم هاش المستخدم لا معرّفه الخام.

## الإعلانات
- Monetag Rewarded (zone `10274259`) لإزالة العلامة المائية.
- `div#promo` يجلب من `/api/promo` ويُخفى بصمت عند الفشل.

## الاختبارات
`python -m pytest tests/test_namecards.py -q`

## أنماط النص الجاهزة
ثلث زخرفي (Rakkas) / رقعة (Aref Ruqaa) / نسخ كلاسيكي (Amiri) — مضمّنة في assets/fonts/namecards/، لا حاجة لرفع خطوط.
