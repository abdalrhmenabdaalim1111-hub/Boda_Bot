"""
error_handler.py — نظام معالجة الأخطاء الموحد
يوفر نظاماً متكاملاً لمعالجة الأخطاء وتسجيلها
"""
import logging
import sys
import traceback
from datetime import datetime
from typing import Optional, Callable, Any
from functools import wraps

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format="[ErrorHandler] %(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ErrorHandler")

class ErrorHandler:
    """فئة لإدارة معالجة الأخطاء بشكل موحد"""

    def __init__(self, bot_name: str):
        """
        تهيئة معالج الأخطاء

        Args:
            bot_name: اسم البوت
        """
        self.bot_name = bot_name
        self.error_count = 0
        self.last_error = None
        self.error_log = []

    def handle_error(self, error: Exception, context: str = "") -> str:
        """
        معالجة الخطأ وتسجيله

        Args:
            error: الخطأ الذي حدث
            context: سياق الخطأ

        Returns:
            رسالة الخطأ المنسقة
        """
        self.error_count += 1
        self.last_error = error

        # إنشاء رسالة الخطأ
        error_msg = f"❌ خطأ في {self.bot_name}"
        if context:
            error_msg += f" - {context}"
        error_msg += f": {str(error)}"

        # تسجيل الخطأ
        logger.error(error_msg)
        logger.error(traceback.format_exc())

        # إضافة إلى سجل الأخطاء
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "error": str(error),
            "context": context,
            "traceback": traceback.format_exc()
        }
        self.error_log.append(error_entry)

        return error_msg

    def get_error_stats(self) -> dict:
        """
        الحصول على إحصائيات الأخطاء

        Returns:
            قاموس يحتوي على إحصائيات الأخطاء
        """
        return {
            "total_errors": self.error_count,
            "last_error": str(self.last_error) if self.last_error else None,
            "recent_errors": self.error_log[-10:]  # آخر 10 أخطاء
        }

    def clear_errors(self):
        """مسح سجل الأخطاء"""
        self.error_count = 0
        self.last_error = None
        self.error_log = []
        logger.info(f"تم مسح سجل الأخطاء لـ {self.bot_name}")

def handle_errors(error_handler: ErrorHandler, context: str = ""):
    """
    مزخرف لمعالجة الأخطاء في الدوال

    Args:
        error_handler: معالج الأخطاء
        context: سياق الخطأ
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Optional[Any]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = error_handler.handle_error(e, context or func.__name__)
                logger.error(error_msg)
                return None
        return wrapper
    return decorator

def log_error(bot_name: str, error: Exception, context: str = ""):
    """
    دالة مساعدة لتسجيل الأخطاء

    Args:
        bot_name: اسم البوت
        error: الخطأ
        context: سياق الخطأ
    """
    handler = ErrorHandler(bot_name)
    handler.handle_error(error, context)
