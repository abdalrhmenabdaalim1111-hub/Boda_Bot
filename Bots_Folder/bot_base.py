# =============================================================================
#  Bots_Folder/bot_base.py — الفئة الأساسية الموحدة لجميع البوتات (v2)
#  تحتوي على: logger, error_handler, DB tracking, polling
# =============================================================================
import os
import sys
import time
import logging
from pathlib import Path

# تحميل .env
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass

# إعداد encoding لـ Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_token(env_key: str, fallback: str = "") -> str:
    """
    الحصول على التوكن من متغيرات البيئة.

    Args:
        env_key:  اسم المتغير في .env (مثل "BOT_STORE_TOKEN")
        fallback: قيمة احتياطية (للتوافق مع الكود القديم)
    """
    token = os.getenv(env_key, "").strip()
    if not token or token == "ضع_التوكن_هنا":
        if fallback and fallback != "ضع_التوكن_هنا":
            return fallback
        return ""
    return token


def get_logger(bot_name: str) -> logging.Logger:
    """الحصول على logger منسّق للبوت."""
    try:
        from logger_config import get_logger as _get
        return _get(bot_name)
    except ImportError:
        clean = bot_name.replace("bot_", "").replace("_", "-")
        logger = logging.getLogger(clean)
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            h = logging.StreamHandler(sys.stdout)
            h.setFormatter(logging.Formatter(
                f"[{clean.upper():12s}] %(asctime)s %(message)s",
                datefmt="%H:%M:%S"
            ))
            logger.addHandler(h)
        return logger


def get_db():
    """
    الحصول على نسخة قاعدة البيانات المشتركة (اختياري).
    يُعيد None إذا لم تكن قاعدة البيانات متاحة.
    """
    try:
        from database import get_db as _get_db
        return _get_db()
    except Exception:
        return None


def track_user(bot_name: str, user_id: int,
               full_name: str = "", username: str = ""):
    """
    تتبع مستخدم في قاعدة البيانات (اختياري — لا يوقف البوت عند الفشل).

    مثال::

        from bot_base import track_user
        track_user("currency", message.from_user.id,
                   message.from_user.full_name,
                   message.from_user.username or "")
    """
    try:
        db = get_db()
        if db:
            db.track_user(bot_name, user_id, full_name, username)
    except Exception:
        pass


def record_error(bot_name: str, error: Exception, user_id: int = None):
    """
    تسجيل خطأ في قاعدة البيانات (اختياري).

    مثال::

        from bot_base import record_error
        try:
            ...
        except Exception as e:
            record_error("currency", e, message.from_user.id)
    """
    try:
        db = get_db()
        if db:
            db.record_error(bot_name, str(error), user_id)
    except Exception:
        pass


def start_polling(bot, bot_name: str = "bot", allowed_updates=None):
    """
    تشغيل البوت بالشكل الصحيح مع معالجة الأخطاء وتسجيل الجلسة.
    يُستخدَم في جميع البوتات بدلاً من كتابة polling في كل ملف.

    مثال::

        from bot_base import start_bot
        start_bot(bot, "base")
        start_bot(bot, "poll_bot", allowed_updates=["message", "callback_query"])
    """
    log = get_logger(bot_name)
    log.info("🚀 بدء التشغيل (Polling)...")

    try:
        me = bot.get_me()
        log.info(f"✅ متصل: @{me.username}")
    except Exception as e:
        log.error(f"❌ فشل الاتصال: {e}")
        try:
            from error_tracker import track_exception
            track_exception(bot_name, e, context="startup_get_me")
        except Exception:
            pass
        sys.exit(1)

    db = get_db()
    session_id = None
    if db:
        try:
            session_id = db.record_bot_start(bot_name)
        except Exception:
            pass

    # ربط أنظمة النمو الفيروسي والإعلانات الموحدة تلقائياً
    try:
        from ad_manager import attach_unified_ads
        attach_unified_ads(bot, bot_name)
    except Exception as e:
        log.debug(f"AdManager attach: {e}")

    try:
        from growth_engine import attach_growth_engine
        attach_growth_engine(bot, bot_name)
    except Exception as e:
        log.debug(f"GrowthEngine attach: {e}")

    # الطبقة الموحدة: تتبع المستخدمين + زر القائمة + بطاقة التطبيق
    try:
        from unified_middleware import install_unified_layer
        install_unified_layer(bot, bot_name)
    except Exception as e:
        log.debug(f"UnifiedLayer install: {e}")

    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(1)
        log.info("📡 Polling started...")
        poll_kwargs = dict(
            skip_pending=True,
            timeout=10,
            long_polling_timeout=20,
        )
        if allowed_updates:
            poll_kwargs["allowed_updates"] = allowed_updates
        bot.infinity_polling(**poll_kwargs)
    except KeyboardInterrupt:
        log.info("⏹ تم الإيقاف يدوياً.")
    except Exception as e:
        log.error(f"❌ خطأ فادح: {e}")
        try:
            from error_tracker import track_exception
            track_exception(bot_name, e, context="polling_crash")
        except Exception:
            pass
        raise
    finally:
        if db and session_id:
            try:
                db.record_bot_stop(session_id)
            except Exception:
                pass


def start_webhook(bot, bot_name: str, webhook_url: str,
                  host: str = "0.0.0.0", port: int = 8443,
                  allowed_updates=None):
    """
    تشغيل البوت بنظام Webhook للإنتاج والنشر السحابي.

    Args:
        bot: كائن البوت (telebot)
        bot_name: اسم البوت
        webhook_url: رابط الـ Webhook العام (HTTPS)
        host: واجهة الاستماع المحلية
        port: المنفذ المحلي
        allowed_updates: قائمة أنواع التحديثات المطلوبة (اختياري)
    """
    log = get_logger(bot_name)
    log.info(f"🚀 بدء التشغيل (Webhook على {webhook_url})...")

    try:
        me = bot.get_me()
        log.info(f"✅ متصل: @{me.username}")
    except Exception as e:
        log.error(f"❌ فشل الاتصال: {e}")
        try:
            from error_tracker import track_exception
            track_exception(bot_name, e, context="startup_get_me")
        except Exception:
            pass
        sys.exit(1)

    db = get_db()
    session_id = None
    if db:
        try:
            session_id = db.record_bot_start(bot_name)
        except Exception:
            pass

    # ربط أنظمة النمو الفيروسي والإعلانات الموحدة تلقائياً
    try:
        from ad_manager import attach_unified_ads
        attach_unified_ads(bot, bot_name)
    except Exception as e:
        log.debug(f"AdManager attach: {e}")

    try:
        from growth_engine import attach_growth_engine
        attach_growth_engine(bot, bot_name)
    except Exception as e:
        log.debug(f"GrowthEngine attach: {e}")

    # الطبقة الموحدة: تتبع المستخدمين + زر القائمة + بطاقة التطبيق
    try:
        from unified_middleware import install_unified_layer
        install_unified_layer(bot, bot_name)
    except Exception as e:
        log.debug(f"UnifiedLayer install: {e}")

    try:
        bot.remove_webhook()
        time.sleep(1)
        full_url = f"{webhook_url.rstrip('/')}/{bot_name}"
        hook_kwargs = dict(url=full_url)
        if allowed_updates:
            hook_kwargs["allowed_updates"] = allowed_updates
        bot.set_webhook(**hook_kwargs)
        log.info(f"🌐 تم تفعيل Webhook: {full_url}")
        # إذا كانت مكتبة الخادم مجهزة يتم تشغيلها
        log.info(f"👂 الاستماع على {host}:{port}")
    except KeyboardInterrupt:
        log.info("⏹ تم إيقاف Webhook.")
    except Exception as e:
        log.error(f"❌ خطأ في Webhook: {e}")
        raise
    finally:
        if db and session_id:
            try:
                db.record_bot_stop(session_id)
            except Exception:
                pass


def start_bot(bot, bot_name: str = "bot", allowed_updates=None):
    """
    مشغّل ذكي موحد للبوت:
    يفحص تلقائياً متغيرات البيئة USE_WEBHOOK و WEBHOOK_URL
    لاختيار التشغيل عبر Webhook أو Polling تلقائياً.

    Args:
        bot: كائن البوت (telebot)
        bot_name: اسم البوت
        allowed_updates: قائمة أنواع التحديثات المطلوبة (اختياري)
    """
    use_webhook = os.getenv("USE_WEBHOOK", "false").lower() in ("true", "1", "yes")
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()

    if use_webhook and webhook_url:
        port = int(os.getenv("WEBHOOK_PORT", "8443"))
        start_webhook(bot, bot_name, webhook_url, port=port,
                      allowed_updates=allowed_updates)
    else:
        start_polling(bot, bot_name, allowed_updates=allowed_updates)


# ── مساعدات التطبيقات المصغّرة (إعادة تصدير للاستخدام الاختياري في البوتات) ──
def get_miniapps_url(bot_id: str) -> str:
    """رابط التطبيق المصغّر لبوت معيّن (من unified_middleware)"""
    try:
        from unified_middleware import get_miniapps_url as _get_url
        return _get_url(bot_id)
    except Exception:
        return ""


def webapp_keyboard(bot_id: str):
    """لوحة أزرار التطبيق (من unified_middleware)"""
    try:
        from unified_middleware import webapp_keyboard as _kb
        return _kb(bot_id)
    except Exception:
        return None
