# =============================================================================
#  Bots_Folder/error_tracker.py — محرك تشخيص وتصنيف وتتبع الأخطاء المتقدم
#  يوفر تتبعاً ذكياً على غرار Sentry لجميع الـ 36 بوتاً دون لمس الكود
# =============================================================================
import sys
import time
import hashlib
import traceback
import logging
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger("ErrorTracker")

# الفئات الرئيسية للأخطاء
CATEGORY_TOKEN_MISSING   = "AUTH_TOKEN_MISSING"
CATEGORY_TOKEN_INVALID   = "AUTH_TOKEN_INVALID"
CATEGORY_RATE_LIMIT      = "TELEGRAM_RATE_LIMIT"
CATEGORY_USER_BLOCKED    = "USER_BLOCKED_BOT"
CATEGORY_NETWORK         = "NETWORK_TIMEOUT"
CATEGORY_EXTERNAL_API    = "EXTERNAL_API_ERROR"
CATEGORY_CODE_ERROR      = "INTERNAL_CODE_ERROR"

# فترات التهدئة لتنبيهات المطور (منع إغراق الإشعارات)
_ALERT_THROTTLE_SECONDS = 300  # تنبيه واحد لكل بصمة خطأ كل 5 دقائق
_last_alerts: Dict[str, float] = {}


def classify_error(exc: Exception) -> Tuple[str, str]:
    """
    تصنيف ذكي للخطأ وإرجاع (التصنيف, مستوى الخطورة).
    
    مستويات الخطورة:
      • INFO: أحداث طبيعية (مثل حظر مستخدم للبوت)
      • WARNING: مشاكل مؤقتة (انقطاع شبكة أو تجاوز حدود الطلبات)
      • ERROR: استثناء برمجي غير متوقع في الكود
      • CRITICAL: مشاكل في التوكن أو انهيار كامل للبوت
    """
    exc_type = type(exc).__name__
    msg = str(exc).lower()

    if "unauthorized" in msg or "invalid token" in msg or "token is invalid" in msg:
        return CATEGORY_TOKEN_INVALID, "CRITICAL"

    if "429" in msg or "too many requests" in msg or "retry_after" in msg or "floodwait" in msg:
        return CATEGORY_RATE_LIMIT, "WARNING"

    if "403" in msg or "blocked by the user" in msg or "user is deactivated" in msg:
        return CATEGORY_USER_BLOCKED, "INFO"

    if any(k in msg for k in ("connection", "timeout", "timed out", "max retries", "ssl", "name resolution")):
        return CATEGORY_NETWORK, "WARNING"

    if any(k in msg for k in ("api", "http 50", "exchangerate", "open-meteo", "bad gateway")):
        return CATEGORY_EXTERNAL_API, "WARNING"

    return CATEGORY_CODE_ERROR, "ERROR"


def compute_fingerprint(bot_name: str, category: str, exc: Exception) -> str:
    """توليد بصمة فريدة للخطأ لتجميع الحالات المتشابهة بدقة."""
    clean_bot = bot_name.replace("bot_", "")
    exc_type = type(exc).__name__
    # أخذ أول سطر من رسالة الخطأ لتفادي المتغيرات الديناميكية
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    raw = f"{clean_bot}:{category}:{exc_type}:{first_line[:80]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def track_exception(bot_name: str, exc: Exception,
                    user_id: Optional[int] = None,
                    context: str = "") -> Dict[str, Any]:
    """
    التقاط وتصنيف وتسجيل الخطأ تلقائياً في قاعدة البيانات ونظام الإشعارات.
    
    Args:
        bot_name: اسم البوت
        exc: كائن الاستثناء (Exception)
        user_id: معرف المستخدم إن وُجد
        context: سياق الرسالة أو الأمر
    """
    clean_bot = bot_name.replace("bot_", "")
    category, severity = classify_error(exc)
    fingerprint = compute_fingerprint(clean_bot, category, exc)
    tb_str = traceback.format_exc()
    if tb_str.strip() == "NoneType: None":
        tb_str = f"{type(exc).__name__}: {str(exc)}"

    logger.warning(f"🚨 [{clean_bot}] {category} ({severity}): {exc}")

    # 1. إذا كان المستخدم حظر البوت (403) — تحديث حالته في قاعدة البيانات
    if category == CATEGORY_USER_BLOCKED and user_id:
        try:
            from database import get_db
            db = get_db()
            if db:
                db.mark_user_blocked(clean_bot, user_id)
        except Exception:
            pass

    # 2. تسجيل الخطأ في قاعدة البيانات المركزية
    try:
        from database import get_db
        db = get_db()
        if db:
            full_msg = f"{str(exc)} | Context: {context}" if context else str(exc)
            db.record_error_event(
                bot_name=clean_bot,
                error_type=category,
                error_message=full_msg,
                traceback_str=tb_str,
                user_id=user_id,
                fingerprint=fingerprint
            )
    except Exception as e:
        logger.debug(f"Error recording in db: {e}")

    # 3. إشعار النظام / المطور عند المشاكل الحرجة أو المتكررة (مع Throttling)
    now = time.time()
    last_time = _last_alerts.get(fingerprint, 0.0)
    should_alert = (severity in ("CRITICAL", "ERROR")) and (now - last_time > _ALERT_THROTTLE_SECONDS)

    if should_alert:
        _last_alerts[fingerprint] = now
        try:
            from notification_system import get_notification_system
            ns = get_notification_system()
            if ns:
                if severity == "CRITICAL":
                    ns.notify_crash(clean_bot, f"[{category}] {str(exc)}")
                else:
                    ns.create_notification(
                        title=f"⚠️ استثناء في {clean_bot}",
                        message=f"نوع الخطأ: {category}\nالرسالة: {str(exc)[:200]}",
                        source=clean_bot,
                        priority=3,
                        data={"fingerprint": fingerprint, "user_id": user_id}
                    )
        except Exception as e:
            logger.debug(f"Error sending notification: {e}")

    return {
        "bot_name": clean_bot,
        "category": category,
        "severity": severity,
        "fingerprint": fingerprint,
        "message": str(exc)
    }
