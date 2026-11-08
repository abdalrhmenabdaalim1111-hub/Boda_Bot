"""
logger_config.py — نظام Logging موحد لجميع البوتات
يوفر logger منسّق مع:
  - طباعة ملوّنة في الـ Console
  - حفظ في ملفات Logs/ مع rotation يومي
  - آخر 7 أيام فقط
"""
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from pathlib import Path

# ── مسار مجلد Logs ──────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent.parent  # مجلد @Boda_Bot
LOGS_DIR = _HERE / "Logs"
LOGS_DIR.mkdir(exist_ok=True)

# ── ألوان Console (ANSI) ────────────────────────────────────────────────────────
_COLORS = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Green
    "WARNING":  "\033[33m",   # Yellow
    "ERROR":    "\033[31m",   # Red
    "CRITICAL": "\033[35m",   # Magenta
    "RESET":    "\033[0m",
}

_WIN = sys.platform == "win32"

class _ColoredFormatter(logging.Formatter):
    """Formatter ملوّن للـ Console"""

    def format(self, record):
        msg = super().format(record)
        if not _WIN:
            color = _COLORS.get(record.levelname, "")
            reset = _COLORS["RESET"]
            return f"{color}{msg}{reset}"
        return msg


def get_logger(bot_name: str) -> logging.Logger:
    """
    إنشاء أو إرجاع logger مُعدّ مسبقاً للبوت.

    Args:
        bot_name: اسم البوت (مثل "store" أو "bot_currency")

    Returns:
        logging.Logger جاهز للاستخدام
    """
    # تنظيف الاسم
    clean_name = bot_name.replace("bot_", "").replace("_", "-")
    logger = logging.getLogger(clean_name)

    # منع إعادة إضافة handlers إذا كان logger موجوداً
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    # ── تنسيق موحد ──────────────────────────────────────────────────────────────
    fmt_console = f"[{clean_name.upper():12s}] %(asctime)s %(levelname)-8s %(message)s"
    fmt_file    = f"[{clean_name.upper():12s}] %(asctime)s %(levelname)-8s %(message)s"
    date_fmt    = "%H:%M:%S"

    # ── Handler 1: Console ────────────────────────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_ColoredFormatter(fmt_console, datefmt=date_fmt))
    logger.addHandler(ch)

    # ── Handler 2: ملف يومي ───────────────────────────────────────────────────────
    log_file = LOGS_DIR / f"{clean_name}.log"
    fh = TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt_file, datefmt="%Y-%m-%d %H:%M:%S"))
    fh.suffix = "%Y-%m-%d"
    logger.addHandler(fh)

    return logger


def configure_windows_encoding():
    """إعداد encoding مناسب لـ Windows"""
    if _WIN:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ── اختبار سريع ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    configure_windows_encoding()
    log = get_logger("test-logger")
    log.info("✅ نظام Logging يعمل بشكل صحيح")
    log.warning("⚠️ هذا تحذير تجريبي")
    log.error("❌ هذا خطأ تجريبي")
    print(f"\n📂 ملفات السجلات في: {LOGS_DIR}")
