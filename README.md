# 🤖 Boda Bot System

<div align="center">

![Version](https://img.shields.io/badge/version-5.1-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen)
![Bots](https://img.shields.io/badge/bots-34-orange)
![Tests](https://img.shields.io/badge/tests-165%2B%20passed-success)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20Docker-lightgrey)

**نظام إدارة وتشغيل 34 بوت تيليجرام — واجهة رسومية محليًا، وتشغيل إنتاجي بلا واجهة على السيرفر**

</div>

---

## 📋 نظرة عامة

**Boda Bot System** نظام متكامل لإدارة وتشغيل **34 بوت تيليجرام** مع تطبيقات ويب مصغّرة لكل بوت:

- 🎛️ **لوحة تحكم محلية (Manager)** — تشغيل/إيقاف/مراقبة البوتات على جهازك
- 🏭 **مشغّل إنتاجي بلا واجهة (`server_runner.py`)** — عملية واحدة تدير كل البوتات على VPS/Docker
- 🌐 **Webhooks حقيقية** — خادم HTTP مشترك لكل البوتات يقلّل استهلاك الموارد مقابل Polling
- 📊 **APM وإحصائيات** — قياس زمن الاستجابة والأخطاء لكل بوت
- 🚨 **مركز أخطاء ذكي** — تصنيف الأخطاء (توكن/شبكة/حدود/كود) وبصمات وتنبيهات
- 📢 **إعلانات Monetag** — شفرات لكل بوت + تتبع ظهور ونقرات + زر راعي تلقائي
- 👁️ **مراقبة خارجية** — `/health` و`/api/stats` جاهزة لـ UptimeRobot + تنبيهات Telegram
- 💾 **نسخ احتياطي مجدول** — لقطة SQLite متسقة + **اختبار استعادة فعلي** تلقائي
- 🌟 **شبكة الـ5 بوتات والنمو الفيروسي** — إحالات ومكافآت VIP
- 🗄️ **SQLite بوضع WAL** — يسمح بقراءة/كتابة متزامنة من عدة خدمات
- 🔒 **single-instance lock** — منع تشغيل نسختين محليًا

---

## 🗂️ هيكل المشروع

```text
@Boda_Bot/
├── Manager.py                 # 🎛️ واجهة التحكم المحلية (Tkinter)
├── StartManager.py            # 🚀 مشغّل محلي مع فحص البيئة
├── server_runner.py           # 🏭 المشغّل الإنتاجي بلا واجهة (Polling/Webhook)
├── monitor_agent.py           # 👁️ مراقبة /health + تنبيهات Telegram
├── api_server.py              # 🌐 خادم المراقبة وواجهة API
├── backup_manager.py          # 💾 نسخ احتياطي + اختبار استعادة فعلي
├── Dockerfile                 # 🐳 صورة إنتاجية (CMD = server_runner)
├── docker-compose.yml         # 🧩 بوتات + API + مراقب (restart: always)
├── requirements.txt           # 📦 المكتبات
├── bots_registry.json         # 📋 سجل البوتات (34 بوت)
├── manager_config.json        # 🔧 إعدادات auto-restart
├── pytest.ini                 # 🧪 إعدادات الاختبارات
│
├── ui/                        # 🎨 مكونات الواجهة الرسومية
│   ├── theme.py               #    الألوان والأنماط
│   ├── header.py              #    شريط العنوان
│   ├── bot_list.py            #    قائمة البوتات + زر Monetag
│   ├── log_panel.py           #    السجل الموحد
│   ├── stats_panel.py         #    KPIs والفلاتر والجدول
│   └── statusbar.py           #    شريط الحالة
│
├── Bots_Folder/               # 🤖 البوتات والمكتبات المشتركة
│   ├── bot_base.py            #    التشغيل الموحد (Polling/Webhook)
│   ├── webhook_server.py      #    خادم Webhook متعدد البوتات
│   ├── database.py            #    SQLite + WAL + جداول الإعلانات والأخطاء
│   ├── data_manager.py        #    مدير البيانات المشترك
│   ├── monitor.py             #    مراقبة الأداء
│   ├── rate_limiter.py        #    حد معدل الطلبات
│   ├── error_handler.py       #    معالج الأخطاء
│   ├── error_tracker.py       #    تصنيف/بصمة/تتبع الأخطاء
│   ├── unified_middleware.py  #    تتبع + زر WebApp + زر الراعي
│   ├── growth_engine.py       #    محرك النمو الفيروسي
│   ├── ad_manager.py          #    إعلانات Monetag + تتبع النقرات
│   ├── notification_system.py #    نظام الإشعارات
│   ├── logger_config.py       #    سجلات دوّارة
│   └── bot_*.py               #    34 بوت
│
├── tests/                     # 🧪 الاختبارات (165+)
├── tools/                     # 🛠️ بناء التطبيقات ومزامنة المستودعات
├── webroot/                   # 🌍 موقع GitHub Pages الموحد
├── Logs/                      # 📝 السجلات
├── Data/                      # 🗄️ قاعدة البيانات والإعدادات (غير مرفوع)
├── Backups/                   # 💾 النسخ الاحتياطية
└── .env                       # 🔐 التوكنات (غير مرفوع)
```

---

## 🚀 التشغيل المحلي (Windows)

```bash
# 1) تثبيت المكتبات
pip install -r requirements.txt

# 2) إعداد البيئة
copy .env.example .env
notepad .env        # ضع توكنات البوتات

# 3) التشغيل
StartManager.bat    # أو: python Manager.py
```

---

## 🏭 النشر الإنتاجي (VPS / Docker)

### 1) تجهيز السيرفر

```bash
git clone <repo> boda-bot && cd boda-bot
cp .env.example .env
nano .env
# انسخ مجلد Data/ من جهازك (قاعدة البيانات + إعدادات Monetag) — غير مرفوع لأسباب أمنية
docker compose up -d --build
docker compose ps
```

الخدمات الثلاث تعمل تلقائيًا مع `restart: always`:

| الخدمة | الوظيفة |
|--------|---------|
| `boda-bots` | عملية واحدة تدير كل البوتات (`server_runner.py`) |
| `boda-api` | `/health` و`/api/stats` و`/api/bots` و`/api/logs` |
| `boda-monitor` | فحص دوري + تنبيهات Telegram عند العطل/التعافي |

### 2) تقسيم البوتات على حاويات (اختياري)

لتخفيف الحمل أو عزل المجموعات، انسخ خدمة `boda-bots` في `docker-compose.yml` وحدد لكل نسخة:

```yaml
environment:
  BODA_BOTS: "currency,qrgen,formatfix,shortlink"
```

> ملاحظة مهمة: لا تشغّل نفس البوت في حاويتين بنظام Polling. عند التقسيم استخدم **Webhook** (خادم مشترك) أو وزّع البوتات دون تكرار.

### 3) Webhooks بدل Polling

Polling يفتح اتصالًا دائمًا لكل بوت ويستهلك موارد أكبر. مع كثرة البوتات استخدم Webhook:

```env
USE_WEBHOOK=true
WEBHOOK_BASE_URL=https://bots.example.com
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8443
WEBHOOK_SECRET=change-me-to-a-long-random-secret
```

- خادم واحد يخدم كل البوتات عبر المسار: `/webhook/<secret>/<bot_id>`
- يتم تسجيل الروابط عند التشغيل وحذفها عند الإيقاف تلقائيًا
- يجب أن يكون النطاق **HTTPS** (شهادة Let's Encrypt عبر Nginx/Caddy)

مثال Nginx:

```nginx
server {
    listen 443 ssl;
    server_name bots.example.com;

    ssl_certificate     /etc/letsencrypt/live/bots.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bots.example.com/privkey.pem;

    location /webhook/ {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 4) المراقبة الخارجية + تنبيهات Telegram

- **UptimeRobot** (أو أي مراقب): راقب `https://api.example.com/ready` كل دقيقة (يعيد 503 عند عدم الجاهزية)، وفعّل تنبيه Telegram من إعدادات UptimeRobot.
- **المراقب المدمج**: خدمة `boda-monitor` تفحص `/health` و`/api/stats` وترسل تنبيهًا عند العطل والتعافي.

```env
BODA_MONITOR_URL=http://127.0.0.1:8080/health
BODA_MONITOR_INTERVAL=60
BODA_MONITOR_COOLDOWN_MIN=30
BODA_MONITOR_BOT_TOKEN=123456:ABC...   # توكن بوت الإشعارات
BODA_ADMIN_CHAT_ID=123456789           # شات الأدمن
```

اختبار سريع:

```bash
python monitor_agent.py --test     # رسالة تجريبية
python monitor_agent.py --once     # فحص واحد
```

### 5) النسخ الاحتياطي المجدول واختبار الاستعادة

المشغّل ينشئ نسخة كل 24 ساعة (قابل للتعديل) **ويجري عليها اختبار استعادة فعليًا**:
يستخرج قاعدة البيانات إلى مجلد مؤقت، يشغّل `PRAGMA integrity_check`، ويقرأ عدد السجلات.

```env
BODA_BACKUP_HOURS=24    # 0 لتعطيل النسخ المجدول
```

يدويًا:

```bash
python backup_manager.py                 # نسخة الآن
python backup_manager.py --verify        # اختبار استعادة الأحدث
python dev_tools.py backup-verify        # نفس الفحص من أداة المطور
python backup_manager.py --restore       # استعادة الأحدث (بحذر)
```

### 6) إبقاء Manager كلوحة مراقبة فقط

- على السيرفر: لا تشغّل `Manager.py` (يحتاج شاشة) — استخدم `server_runner` + `api_server` + `monitor_agent`.
- على جهازك: يمكنك تشغيل Manager محليًا لمتابعة النسخ/السجلات، أو الاعتماد على `/api/stats` وUptimeRobot.
- أوامر الصيانة تعمل من السيرفر مباشرة: `python dev_tools.py status | diagnose | bots-check`.

### 7) التحديث والصيانة

```bash
git pull
docker compose up -d --build
docker compose logs -f boda-bots
docker compose exec boda-bots python dev_tools.py diagnose
```

---

## 🛠️ أداة المطور والصيانة (`dev_tools.py`)

```bash
# تقرير شامل لحالة النظام والتوكنات وقاعدة البيانات
python dev_tools.py status

# تشخيص ذكي شامل: بنية + توكنات + صفحات + إعلانات + أخطاء + توصيات
python dev_tools.py diagnose

# جدول حالة التوكنات واليوزرنيم المخطط لكل بوت
python dev_tools.py tokens

# إدخال توكنات بالجملة من new_tokens.txt مع فحص تيليجرام التلقائي
python dev_tools.py import-tokens

# فحص صلاحية كل التوكنات الحالية عبر خوادم تيليجرام
python dev_tools.py tokens-verify

# تشغيل كافة الاختبارات التلقائية
python dev_tools.py test

# فحص كود المشروع والتأكد من خلوه من أي أخطاء syntax
python dev_tools.py lint

# فحص صحة وتكامل البوتات المسجلة وملفاتها
python dev_tools.py health

# فحص جودة شامل: 7 فحوصات لكل بوت (238/238)
python dev_tools.py bots-check

# تقرير APM: زمن الاستجابة والأخطاء والإعلانات
python dev_tools.py stats

# جدول إعلانات Monetag لكل بوت
python dev_tools.py ads

# ضبط شفرة Monetag لبوت معين وحقنها في صفحته فورًا
python dev_tools.py set-ad currency https://smartlink.example/abc

# مركز الأخطاء والتشخيص
python dev_tools.py errors [bot_id]

# نسخة احتياطية + اختبار استعادة فعلي
python dev_tools.py backup
python dev_tools.py backup-verify

# مزامنة مستودعات GitHub الـ34 وصفحاتها
python dev_tools.py repos-sync

# تنظيف الكاش والملفات المؤقتة
python dev_tools.py clean
```

---

## 🌐 خادم المراقبة والصحة (`api_server.py`)

```bash
python api_server.py --host 0.0.0.0 --port 8080
```

- `GET /health` — فحص سلامة النظام (عام، بلا مفتاح)
- `GET /ready` — فحص الجاهزية: 200 جاهز / 503 غير جاهز (لـ UptimeRobot)
- `GET /api/stats` — إحصائيات المستخدمين والبوتات
- `GET /api/bots` — قائمة البوتات المسجلة
- `GET /api/logs?bot=<id>&limit=50` — أحدث السجلات
- `GET /api/events` — أحداث التطبيقات
- `POST /api/track` — تسجيل حدث من التطبيقات

إن ضبطت `API_SERVER_KEY` في `.env` فلن تعمل مسارات `/api/*` إلا بترويسة `X-API-Key`.

---

## 🤖 فئات البوتات

| الفئة | البوتات |
|-------|---------|
| 🛠️ أدوات | currency, qrgen, formatfix, shortlink, cashier, safepass |
| 🎪 ترفيه | fun_name, random_suggest, lovecalculator, mentalage, luckybox, braintwist |
| 🤖 ذكاء اصطناعي | backdrop, stickerx, photoboost, colorpick |
| 📥 تحميل | vidload, cleantok, silentcut |
| 🌐 ترجمة | transbot, doctrans |
| 📝 اختبارات | iqtest, personalityanalyzer, cvbuilder |
| 💰 مالية | cryptorate |
| 💪 صحة | fitcheck, caltrack |
| ⏰ إنتاجية | alarmbot, memoryvault |
| 🌦️ معلومات | weathernow |
| 🏪 متجر | store |

---

## 🗄️ قاعدة البيانات

جداول SQLite (وضع WAL):

| الجدول | المحتوى |
|--------|---------|
| `users` | المستخدمون وتفعيلاتهم |
| `usage_stats` | إحصاءات الاستخدام اليومية |
| `bot_sessions` | جلسات تشغيل البوتات ومدتها |
| `error_log` | سجل الأخطاء المبسّط |
| `error_events` | الأخطاء التفصيلية + البصمة |
| `referrals` | الإحالات والمكافآت |
| `network_activations` / `network_assignments` | شبكة البوتات الخمسة |
| `monetag_ad_stats` | ظهور/نقرات إعلانات Monetag |

---

## 🧪 تشغيل الاختبارات

```bash
pytest                              # كل الاختبارات
pytest -v                           # بتفاصيل
pytest tests/test_webhook_server.py # ملف محدد
pytest --cov=Bots_Folder --cov-report=html
```

---

## ➕ إضافة بوت جديد (للمطورين)

1. انسخ `Bots_Folder/bot_template.py`
2. أعد تسميته `bot_mybotname.py` وعدّل التوكن
3. أضف التوكن في `.env` بالمفتاح `BOT_MYBOTNAME_TOKEN`
4. أضف التطبيق في `tools/app_defs.py` وسجّله في `bots_registry.json`
5. أعد البناء: `python tools/build_mini_apps.py`
6. افحص: `python dev_tools.py bots-check`

---

## 🌍 المواقع والمستودعات

- **الموقع الموحد:** `https://abdalrhmenabdaalim1111-hub.github.io/Boda_Bot/`
- **متجر التطبيقات:** `.../Boda_Bot/store/`
- **صفحة كل بوت:** `https://abdalrhmenabdaalim1111-hub.github.io/boda-bot-<id>/`
- **المستودعات:** 34 مستودعًا عامًا `boda-bot-<id>`

> 🔐 **ملاحظة الخصوصية:** صفحات GitHub Pages المجانية تتطلب مستودعًا **عامًا**. لجعل الصفحات خاصة تحتاج GitHub Pro (صفحات خاصة) أو استضافة بديلة. المحتوى هنا صفحات تعريفية عامة لتطبيقات البوتات، ولا يحتوي أي توكنات أو بيانات مستخدمين.

---

## 📱 إعداد BotFather (مرة واحدة)

1. لكل بوت: `/setwebapp` → اختر البوت → ضع رابط تطبيقه.
2. `/setdomain` أو توثيق النطاق: `abdalrhmenabdaalim1111-hub.github.io`
3. عند استخدام Webhook: تأكد أن `WEBHOOK_BASE_URL` يطابق النطاق الموثق، ثم شغّل `server_runner.py`.

---

## 📈 الإصدارات

| الإصدار | التغييرات |
|---------|-----------|
| **v5.1** | تشغيل إنتاجي Headless + Docker (restart always) + Webhooks حقيقية + مراقبة UptimeRobot/Telegram + نسخ احتياطي مجدول مع اختبار استعادة فعلي |
| **v5.0** | APM وإحصائيات، Monetag كامل + تتبع النقرات، مركز أخطاء ذكي، لوحة KPIs، أوامر ads/set-ad/errors/diagnose |
| **v4.5** | `dev_tools.py`، `api_server.py`، Docker، نسخ ZIP، Webhook (أساسي) |
| **v4.1** | هيكلة معمارية، SQLite، لوحة إحصائيات، اختبارات |
| **v4.0** | واجهة GitHub-dark، سجل موحد، auto-restart |
| **v3.x** | إشعارات، rate limiter، error handler |

---

<div align="center">
<sub>🤖 Boda Bot System — Built with ❤️ using Python & pyTelegramBotAPI</sub>
</div>
