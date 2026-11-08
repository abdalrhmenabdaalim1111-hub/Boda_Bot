"""
notification_system.py — نظام الإشعارات المتقدم
يوفر نظاماً متكاملاً لإدارة الإشعارات بين البوتات
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import os

logging.basicConfig(
    level=logging.INFO,
    format="[Notification] %(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Notification")

class NotificationType(Enum):
    """أنواع الإشعارات"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    UPDATE = "update"

class NotificationPriority(Enum):
    """أولوية الإشعارات"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class Notification:
    """فئة الإشعار"""
    id: str
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    read: bool = False
    data: Optional[Dict] = None

class NotificationSystem:
    """نظام الإشعارات الرئيسي"""

    def __init__(self, storage_path: Optional[str] = None):
        """
        تهيئة نظام الإشعارات

        Args:
            storage_path: مسار ملف التخزين
        """
        if storage_path is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Data")
            os.makedirs(data_dir, exist_ok=True)
            storage_path = os.path.join(data_dir, "notifications.json")

        self.storage_path = storage_path
        self.notifications: List[Notification] = []
        self.subscribers: Dict[str, List[Callable]] = {}
        self._load_notifications()

    def _load_notifications(self):
        """تحميل الإشعارات من الملف"""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for notif_data in data:
                        notif = Notification(
                            id=notif_data['id'],
                            type=NotificationType(notif_data['type']),
                            priority=NotificationPriority(notif_data['priority']),
                            title=notif_data['title'],
                            message=notif_data['message'],
                            source=notif_data['source'],
                            timestamp=datetime.fromisoformat(notif_data['timestamp']),
                            read=notif_data['read'],
                            data=notif_data.get('data')
                        )
                        self.notifications.append(notif)
                logger.info(f"تم تحميل {len(self.notifications)} إشعار")
        except Exception as e:
            logger.error(f"خطأ في تحميل الإشعارات: {e}")

    def _save_notifications(self):
        """حفظ الإشعارات في الملف"""
        try:
            data = []
            for notif in self.notifications:
                notif_data = {
                    'id': notif.id,
                    'type': notif.type.value,
                    'priority': notif.priority.value,
                    'title': notif.title,
                    'message': notif.message,
                    'source': notif.source,
                    'timestamp': notif.timestamp.isoformat(),
                    'read': notif.read,
                    'data': notif.data
                }
                data.append(notif_data)

            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"خطأ في حفظ الإشعارات: {e}")

    def create_notification(
        self,
        title: str,
        message: str,
        source: str,
        notif_type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        data: Optional[Dict] = None
    ) -> Notification:
        """
        إنشاء إشعار جديد

        Args:
            title: عنوان الإشعار
            message: رسالة الإشعار
            source: مصدر الإشعار
            notif_type: نوع الإشعار
            priority: أولوية الإشعار
            data: بيانات إضافية

        Returns:
            الإشعار المنشأ
        """
        notif_id = f"{source}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        notification = Notification(
            id=notif_id,
            type=notif_type,
            priority=priority,
            title=title,
            message=message,
            source=source,
            data=data
        )

        self.notifications.append(notification)
        self._save_notifications()

        # إرسال الإشعار للمشتركين
        self._notify_subscribers(notification)

        logger.info(f"تم إنشاء إشعار: {title}")
        return notification

    def get_notifications(
        self,
        source: Optional[str] = None,
        notif_type: Optional[NotificationType] = None,
        priority: Optional[NotificationPriority] = None,
        unread_only: bool = False,
        limit: int = 50
    ) -> List[Notification]:
        """
        الحصول على الإشعارات

        Args:
            source: تصفية حسب المصدر
            notif_type: تصفية حسب النوع
            priority: تصفية حسب الأولوية
            unread_only: فقط الإشعارات غير المقروءة
            limit: الحد الأقصى للإشعارات

        Returns:
            قائمة الإشعارات المصفاة
        """
        filtered = self.notifications

        if source:
            filtered = [n for n in filtered if n.source == source]
        if notif_type:
            filtered = [n for n in filtered if n.type == notif_type]
        if priority:
            filtered = [n for n in filtered if n.priority == priority]
        if unread_only:
            filtered = [n for n in filtered if not n.read]

        # ترتيب حسب الأولوية والتاريخ
        filtered.sort(key=lambda x: (x.priority.value, x.timestamp), reverse=True)

        return filtered[:limit]

    def mark_as_read(self, notification_id: str):
        """
        تعليم إشعار كمقروء

        Args:
            notification_id: معرف الإشعار
        """
        for notif in self.notifications:
            if notif.id == notification_id:
                notif.read = True
                self._save_notifications()
                logger.info(f"تم تعليم الإشعار {notification_id} كمقروء")
                return

    def mark_all_as_read(self, source: Optional[str] = None):
        """
        تعليم جميع الإشعارات كمقروءة

        Args:
            source: مصدر الإشعارات (اختياري)
        """
        for notif in self.notifications:
            if source is None or notif.source == source:
                notif.read = True
        self._save_notifications()
        logger.info(f"تم تعليم جميع الإشعارات كمقروءة")

    def delete_notification(self, notification_id: str):
        """
        حذف إشعار

        Args:
            notification_id: معرف الإشعار
        """
        self.notifications = [n for n in self.notifications if n.id != notification_id]
        self._save_notifications()
        logger.info(f"تم حذف الإشعار {notification_id}")

    def clear_old_notifications(self, days: int = 30):
        """
        مسح الإشعارات القديمة

        Args:
            days: عدد الأيام
        """
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        old_count = len(self.notifications)
        self.notifications = [n for n in self.notifications if n.timestamp > cutoff]
        self._save_notifications()
        logger.info(f"تم مسح {old_count - len(self.notifications)} إشعار قديم")

    def subscribe(self, source: str, callback: Callable):
        """
        الاشتراك في إشعارات مصدر معين

        Args:
            source: مصدر الإشعارات
            callback: دالة الاستدعاء
        """
        if source not in self.subscribers:
            self.subscribers[source] = []
        self.subscribers[source].append(callback)
        logger.info(f"تم الاشتراك في إشعارات {source}")

    def unsubscribe(self, source: str, callback: Callable):
        """
        إلغاء الاشتراك من إشعارات مصدر معين

        Args:
            source: مصدر الإشعارات
            callback: دالة الاستدعاء
        """
        if source in self.subscribers:
            self.subscribers[source].remove(callback)
            if not self.subscribers[source]:
                del self.subscribers[source]
            logger.info(f"تم إلغاء الاشتراك من إشعارات {source}")

    def _notify_subscribers(self, notification: Notification):
        """
        إرسال الإشعار للمشتركين

        Args:
            notification: الإشعار
        """
        if notification.source in self.subscribers:
            for callback in self.subscribers[notification.source]:
                try:
                    callback(notification)
                except Exception as e:
                    logger.error(f"خطأ في إرسال الإشعار: {e}")

    def get_summary(self) -> Dict:
        """
        الحصول على ملخص الإشعارات

        Returns:
            قاموس يحتوي على ملخص الإشعارات
        """
        total = len(self.notifications)
        unread = len([n for n in self.notifications if not n.read])

        by_type = {}
        for notif_type in NotificationType:
            by_type[notif_type.value] = len([n for n in self.notifications if n.type == notif_type])

        by_priority = {}
        for priority in NotificationPriority:
            by_priority[priority.name] = len([n for n in self.notifications if n.priority == priority])

        return {
            "total": total,
            "unread": unread,
            "by_type": by_type,
            "by_priority": by_priority
        }

    def notify_crash(self, bot_name: str, error_msg: str) -> Notification:
        """إشعار فوري عند انهيار أو توقف بوت بشكل غير متوقع"""
        title = f"🚨 انهيار البوت: {bot_name}"
        msg = f"تعطل البوت {bot_name} بسبب الخطأ التالي:\n{error_msg}"
        return self.create_notification(
            title=title,
            message=msg,
            source=bot_name,
            notif_type=NotificationType.ERROR,
            priority=NotificationPriority.CRITICAL,
            data={"error": error_msg}
        )

    def notify_rate_limit(self, bot_name: str, user_id: int) -> Notification:
        """إشعار عند تجاوز مستخدم لحد معدل الطلبات (Rate limit)"""
        title = f"⚠️ تجاوز حد الطلبات في {bot_name}"
        msg = f"المستخدم {user_id} تجاوز حد الطلبات المسموح به."
        return self.create_notification(
            title=title,
            message=msg,
            source=bot_name,
            notif_type=NotificationType.WARNING,
            priority=NotificationPriority.MEDIUM,
            data={"user_id": user_id}
        )


_system_instance = None

def get_notification_system() -> NotificationSystem:
    """الحصول على النسخة المشتركة لنظام الإشعارات (Singleton)"""
    global _system_instance
    if _system_instance is None:
        _system_instance = NotificationSystem()
    return _system_instance
