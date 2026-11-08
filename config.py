
"""
config.py — ملف الإعدادات العام للبوتات
🚀 WebApp-First
@BodaStoreBot
"""
import os
from pathlib import Path

# المسارات
BASE_DIR = Path(__file__).parent
BOTS_FOLDER = BASE_DIR / "Bots_Folder"
LOGS_FOLDER = BASE_DIR / "Logs"
DATA_FOLDER = BASE_DIR / "Data"

# إنشاء المجلدات إذا لم تكن موجودة
LOGS_FOLDER.mkdir(exist_ok=True)
DATA_FOLDER.mkdir(exist_ok=True)

# إعدادات المتجر
STORE_URL = "https://t.me/BodaStoreeBot"
STORE_BOT_USERNAME = "BodaStoreeBot"


# إعدادات التسجيل
LOG_LEVEL = "INFO"
LOG_FORMAT = "[%(name)s] %(asctime)s %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

# إعدادات البوت
BOT_PARSE_MODE = "HTML"
BOT_THREADING = True
POLLING_TIMEOUT = 10
LONG_POLLING_TIMEOUT = 20

# إعدادات الأمان
MAX_RETRIES = 3
RETRY_DELAY = 5

# معلومات المطور
DEVELOPER_USERNAME = "@YourUsername"
DEVELOPER_EMAIL = "your.email@example.com"

# إعدادات قاعدة البيانات (إذا لزم الأمر)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# إعدادات Redis (إذا لزم الأمر)
REDIS_URL = os.getenv("REDIS_URL", "")

# إعدادات التخزين السحابي (إذا لزم الأمر)
STORAGE_URL = os.getenv("STORAGE_URL", "")

# إعدادات API (إذا لزم الأمر)
API_KEY = os.getenv("API_KEY", "")
API_SECRET = os.getenv("API_SECRET", "")
