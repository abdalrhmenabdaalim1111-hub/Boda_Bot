# 🤖 Boda Bot System

<div align="center">

![Version](https://img.shields.io/badge/version-4.5-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen)
![Bots](https://img.shields.io/badge/bots-36-orange)
![Tests](https://img.shields.io/badge/tests-66%20passed-success)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20Docker-lightgrey)

**نظام إدارة بوتات تيليجرام متعدد مع واجهة رسومية احترافية ونظام نمو فيروسي**

</div>

---

## 📋 نظرة عامة

**Boda Bot System** هو نظام متكامل لإدارة وتشغيل **36 بوت تيليجرام** بواجهة رسومية مبنية بـ Python/Tkinter مع تحكم كامل دون الحاجة لكتابة كود:

- 🎛️ **لوحة تحكم مركزية** — تشغيل/إيقاف/مراقبة كل البوتات من مكان واحد
- 🔑 **إدارة التوكنات المرئية** — وضع وتحديث توكنات البوتات غير المفعلة بضغطة زر مع فحص تيليجرام التلقائي
- ➕ **توليد بوتات جديدة** — إنشاء بوت جديد وتسجيله وربطه بالمتجر والشبكة فوراً
- 🌟 **شبكة الـ 5 بوتات الإجبارية** — تفعيل إجباري يضمن انتشار البوتات واشتراك المستخدمين
- 🔗 **نظام الإحالات والمشاركة الفيروسية** — رابط دعوة ومكافآت VIP لكل مستخدم
- 📋 **سجل موحد** — رؤية مخرجات جميع البوتات مع فلتر وألوان فريدة
- 📊 **إحصائيات حية** — جدول تفصيلي للحالة والـ uptime والـ CPU/RAM
- 🔄 **إعادة تشغيل تلقائية** — البوتات تُعيد تشغيل نفسها عند الانهيار
- 🗄️ **قاعدة بيانات SQLite** — تتبع المستخدمين والإحالات والتفعيلات
- 🔒 **single-instance lock** — منع تشغيل نسختين بنفس الوقت

---

## 🗂️ هيكل المشروع

```
@Boda_Bot/
├── Manager.py              # 🎛️ واجهة التحكم الرئيسية (v4.1)
├── StartManager.py         # 🚀 مشغّل موحد مع فحص البيئة
├── StartManager.bat        # ⚡ تشغيل سريع لـ Windows
├── config.py               # ⚙️ إعدادات مركزية
├── bots_registry.json      # 📋 سجل البوتات (35+ بوت)
├── manager_config.json     # 🔧 إعدادات auto-restart
├── backup_manager.py       # 💾 إدارة النسخ الاحتياطية
├── requirements.txt        # 📦 المكتبات المطلوبة
├── pytest.ini              # 🧪 إعدادات الاختبارات
│
├── ui/                     # 🎨 مكونات الواجهة الرسومية
│   ├── theme.py            #    نظام الألوان والأنماط
│   ├── header.py           #    شريط العنوان
│   ├── bot_list.py         #    قائمة البوتات
│   ├── log_panel.py        #    لوحة السجل الموحد
│   ├── stats_panel.py      #    لوحة الإحصائيات (جديد!)
│   └── statusbar.py        #    شريط الحالة
│
├── Bots_Folder/            # 🤖 البوتات والمكتبات المشتركة
│   ├── bot_base.py         #    الفئة الأساسية الموحدة
│   ├── database.py         #    قاعدة بيانات SQLite (جديد!)
│   ├── data_manager.py     #    مدير البيانات المشترك
│   ├── monitor.py          #    مراقبة الأداء
│   ├── rate_limiter.py     #    حد معدل الطلبات
│   ├── error_handler.py    #    معالج الأخطاء
│   ├── notification_system.py  نظام الإشعارات
│   ├── logger_config.py    #    إعداد السجلات
│   └── bot_*.py            #    35+ بوت
│
├── tests/                  # 🧪 الاختبارات التلقائية
│   ├── test_registry.py    #    اختبارات bots_registry.json
│   ├── test_database.py    #    اختبارات SQLite
│   └── test_bot_base.py    #    اختبارات الفئة الأساسية
│
├── Logs/                   # 📝 سجلات البوتات
├── Data/                   # 🗄️ ملفات البيانات وقاعدة البيانات
└── .env                    # 🔐 توكنات API (لا تُضاف لـ git)
```

---

## 🚀 التشغيل السريع

### 1. المتطلبات

```bash
pip install -r requirements.txt
```

### 2. الإعداد

```bash
# انسخ ملف الإعدادات
copy .env.example .env

# ضع توكناتك في .env
notepad .env
```

### 3. التشغيل

```bash
# Windows — الطريقة الأسهل
StartManager.bat

# أو مباشرة
python Manager.py
```

### 4. التشغيل عبر Docker (اختياري للإنتاج والسيرفرات)

```bash
docker-compose up -d
```

---

## 🛠️ أداة المطور والصيانة (`dev_tools.py`)

أداة CLI موحدة للتحكم بالصيانة والفحص السريع:

```bash
# تقرير شامل لحالة النظام والتوكنات وقاعدة البيانات
python dev_tools.py status

# تشغيل كافة الاختبارات التلقائية
python dev_tools.py test

# فحص كود المشروع والتأكد من خلوه من أي أخطاء syntax
python dev_tools.py lint

# فحص صحة وتكامل البوتات المسجلة وملفاتها
python dev_tools.py health

# تنظيف ملفات الكاش والملفات المؤقتة
python dev_tools.py clean

# إنشاء نسخة احتياطية مضغوطة فوراً
python dev_tools.py backup

# توليد بوت جديد وتسجيله تلقائياً
python dev_tools.py new-bot <id> <name> [category]
```

---

## 🌐 خادم المراقبة والصحة (`api_server.py`)

يوفر واجهة برمجية HTTP خفيفة ومستقلة:

```bash
python api_server.py --port 8080
```

- `GET /health` — فحص سلامة النظام وتوفر البيئة
- `GET /api/stats` — إحصائيات قاعدة البيانات والمستخدمين
- `GET /api/bots` — قائمة البوتات المسجلة وحالاتها
- `GET /api/logs` — قراءة أحدث أسطر السجلات

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
| ⏰ إنتاجية | alarmbot, memoryvault, pollmaster |
| 🌦️ معلومات | weathernow, termgloss |
| 🏪 متجر | store |

---

## 🗄️ قاعدة البيانات

البوتات يمكنها اختيارياً تتبع المستخدمين بإضافة سطرين:

```python
from bot_base import track_user, record_error

@bot.message_handler(func=lambda m: True)
def handle(message):
    # تتبع المستخدم (اختياري)
    track_user("my_bot", message.from_user.id,
               message.from_user.full_name,
               message.from_user.username or "")
    # ... باقي الكود
```

---

## 🧪 تشغيل الاختبارات

```bash
# جميع الاختبارات
pytest

# بتفاصيل أكثر
pytest -v

# اختبار ملف معين
pytest tests/test_registry.py -v

# مع تقرير التغطية
pytest --cov=Bots_Folder --cov-report=html
```

---

## ➕ إضافة بوت جديد

1. انسخ `Bots_Folder/bot_template.py`
2. أعد تسميته `bot_mybotname.py`
3. أضف `TOKEN = "your_token_here"` بالتوكن الحقيقي
4. اضغط **🔄 Refresh** في Manager لاكتشافه تلقائياً
5. اضغط **▶** لتشغيله

---

## 📈 الإصدارات

| الإصدار | التغييرات |
|---------|-----------|
| **v4.5** | أداة `dev_tools.py`، خادم `api_server.py`، دعم Docker، نسخ احتياطي ZIP مضغوط، دعم Webhook، وتوسيع الاختبارات لـ 57 اختباراً |
| **v4.1** | هيكلة معمارية، قاعدة بيانات SQLite، لوحة إحصائيات، اختبارات |
| **v4.0** | واجهة GitHub-dark، سجل موحد، auto-restart محسّن |
| **v3.x** | نظام إشعارات، rate limiter، error handler |

---

## 🛠️ تطوير بوت جديد

```python
# bot_mybot.py — Template
import telebot
from bot_base import get_token, start_polling, track_user

TOKEN = get_token("BOT_MYBOT_TOKEN")
bot   = telebot.TeleBot(TOKEN, parse_mode="HTML")
BOT_NAME = "mybot"

@bot.message_handler(commands=["start"])
def cmd_start(message):
    track_user(BOT_NAME, message.from_user.id,
               message.from_user.full_name)
    bot.reply_to(message, "👋 أهلاً!")

if __name__ == "__main__":
    start_polling(bot, BOT_NAME)
```

---

<div align="center">
<sub>🤖 Boda Bot System — Built with ❤️ using Python & pyTelegramBotAPI</sub>
</div>
