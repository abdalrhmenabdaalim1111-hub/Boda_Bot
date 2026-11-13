"""
tests/test_notification_system.py — اختبارات شاملة لنظام الإشعارات (Notification System)
تغطي: NotificationSystem class, create_notification, get_notifications, mark_as_read,
mark_all_as_read, delete_notification, clear_old_notifications, subscribe/unsubscribe,
get_summary, notify_crash, notify_rate_limit, singleton get_notification_system
"""
import os
import sys
import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))


class TestNotificationSystemInit:
    """اختبارات تهيئة نظام الإشعارات"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        """نظام إشعارات بملف تخزين مؤقت"""
        from notification_system import NotificationSystem
        storage_file = tmp_path / "notifications.json"
        return NotificationSystem(storage_path=str(storage_file))

    def test_init_creates_storage_dir(self, tmp_path):
        """ينشئ مجلد التخزين إذا لم يكن موجوداً"""
        from notification_system import NotificationSystem
        storage_file = tmp_path / "subdir" / "notifications.json"
        ns = NotificationSystem(storage_path=str(storage_file))
        assert storage_file.parent.exists()

    def test_load_notifications_existing_file(self, notification_system, tmp_path):
        """يحمل الإشعارات الموجودة من الملف"""
        # إضافة بيانات مباشرة
        storage_file = tmp_path / "notifications.json"
        test_data = [{
            "id": "test_1",
            "type": "info",
            "priority": 1,
            "title": "Test",
            "message": "Test message",
            "source": "test",
            "timestamp": datetime.now().isoformat(),
            "read": False,
            "data": None
        }]
        storage_file.write_text(json.dumps(test_data, ensure_ascii=False), encoding="utf-8")

        # إعادة تهيئة لتحميل البيانات
        from notification_system import NotificationSystem
        ns = NotificationSystem(storage_path=str(storage_file))
        assert len(ns.notifications) == 1
        assert ns.notifications[0].title == "Test"

    def test_load_notifications_corrupted_file(self, notification_system, tmp_path):
        """ملف تالف → يبدأ بقائمة فارغة"""
        storage_file = tmp_path / "notifications.json"
        storage_file.write_text("invalid json", encoding="utf-8")

        from notification_system import NotificationSystem
        ns = NotificationSystem(storage_path=str(storage_file))
        assert len(ns.notifications) == 0


class TestNotificationSystemCreateNotification:
    """اختبارات إنشاء الإشعارات"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem
        storage_file = tmp_path / "notifications.json"
        return NotificationSystem(storage_path=str(storage_file))

    def test_create_notification_basic(self, notification_system):
        """إنشاء إشعار أساسي"""
        notif = notification_system.create_notification(
            title="Test Title",
            message="Test Message",
            source="test_source"
        )
        assert notif.title == "Test Title"
        assert notif.message == "Test Message"
        assert notif.source == "test_source"
        assert notif.type.value == "info"
        assert notif.priority.value == 2  # MEDIUM
        assert notif.read is False
        assert len(notification_system.notifications) == 1

    def test_create_notification_with_type_priority(self, notification_system):
        """إنشاء إشعار بنوع وأولوية مخصصة"""
        from notification_system import NotificationType, NotificationPriority

        notif = notification_system.create_notification(
            title="Error",
            message="Error message",
            source="test",
            notif_type=NotificationType.ERROR,
            priority=NotificationPriority.CRITICAL
        )
        assert notif.type == NotificationType.ERROR
        assert notif.priority == NotificationPriority.CRITICAL

    def test_create_notification_with_data(self, notification_system):
        """إنشاء إشعار مع بيانات إضافية"""
        notif = notification_system.create_notification(
            title="Test",
            message="Test",
            source="test",
            data={"key": "value", "count": 5}
        )
        assert notif.data == {"key": "value", "count": 5}

    def test_create_notification_saves_to_file(self, notification_system, tmp_path):
        """يحفظ الإشعار في الملف"""
        storage_file = tmp_path / "notifications.json"
        notification_system.create_notification("Test", "Msg", "test")

        # قراءة الملف مباشرة
        with open(storage_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["title"] == "Test"

    def test_create_notification_notifies_subscribers(self, notification_system):
        """يرسل الإشعار للمشتركين"""
        callback = MagicMock()
        notification_system.subscribe("test_source", callback)

        notification_system.create_notification("Test", "Msg", "test_source")
        callback.assert_called_once()


class TestNotificationSystemGetNotifications:
    """اختبارات استرجاع الإشعارات"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem, NotificationType, NotificationPriority
        storage_file = tmp_path / "notifications.json"
        ns = NotificationSystem(storage_path=str(storage_file))
        # إضافة إشعارات اختبار
        ns.create_notification("Info 1", "Msg", "source1", notif_type=NotificationType.INFO, priority=NotificationPriority.LOW)
        ns.create_notification("Warning 1", "Msg", "source1", notif_type=NotificationType.WARNING, priority=NotificationPriority.HIGH)
        ns.create_notification("Error 1", "Msg", "source2", notif_type=NotificationType.ERROR, priority=NotificationPriority.CRITICAL)
        ns.create_notification("Success 1", "Msg", "source2", notif_type=NotificationType.SUCCESS, priority=NotificationPriority.MEDIUM)
        return ns

    def test_get_notifications_all(self, notification_system):
        """استرجاع جميع الإشعارات"""
        notifs = notification_system.get_notifications()
        assert len(notifs) == 4

    def test_get_notifications_filter_source(self, notification_system):
        """تصفية حسب المصدر"""
        notifs = notification_system.get_notifications(source="source1")
        assert len(notifs) == 2
        assert all(n.source == "source1" for n in notifs)

    def test_get_notifications_filter_type(self, notification_system):
        """تصفية حسب النوع"""
        from notification_system import NotificationType
        notifs = notification_system.get_notifications(notif_type=NotificationType.ERROR)
        assert len(notifs) == 1
        assert notifs[0].type.value == "error"

    def test_get_notifications_filter_priority(self, notification_system):
        """تصفية حسب الأولوية"""
        from notification_system import NotificationPriority
        notifs = notification_system.get_notifications(priority=NotificationPriority.CRITICAL)
        assert len(notifs) == 1
        assert notifs[0].priority.value == 4

    def test_get_notifications_unread_only(self, notification_system):
        """إشعارات غير مقروءة فقط"""
        # تعليم واحد كمقروء
        notification_system.notifications[0].read = True
        notification_system._save_notifications()

        notifs = notification_system.get_notifications(unread_only=True)
        assert len(notifs) == 3
        assert all(not n.read for n in notifs)

    def test_get_notifications_limit(self, notification_system):
        """حد أقصى للنتائج"""
        notifs = notification_system.get_notifications(limit=2)
        assert len(notifs) == 2

    def test_get_notifications_sorted_by_priority_and_time(self, notification_system):
        """مرتبة حسب الأولوية ثم الوقت"""
        notifs = notification_system.get_notifications()
        # الأولوية الأعلى أولاً
        assert notifs[0].priority.value >= notifs[1].priority.value


class TestNotificationSystemMarkAsRead:
    """اختبارات تعليم الإشعارات كمقروءة"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem
        storage_file = tmp_path / "notifications.json"
        ns = NotificationSystem(storage_path=str(storage_file))
        ns.create_notification("Test 1", "Msg", "test")
        ns.create_notification("Test 2", "Msg", "test")
        return ns

    def test_mark_as_read_existing(self, notification_system):
        """تعليم إشعار موجود كمقروء"""
        notif_id = notification_system.notifications[0].id
        notification_system.mark_as_read(notif_id)
        assert notification_system.notifications[0].read is True

    def test_mark_as_read_nonexistent(self, notification_system):
        """إشعار غير موجود → لا خطأ"""
        notification_system.mark_as_read("nonexistent")
        # لا يجب أن يطرح استثناء

    def test_mark_all_as_read(self, notification_system):
        """تعليم جميع الإشعارات كمقروءة"""
        notification_system.mark_all_as_read()
        assert all(n.read for n in notification_system.notifications)

    def test_mark_all_as_read_by_source(self, notification_system):
        """تعليم جميع إشعارات مصدر معين"""
        # إضافة إشعار من مصدر آخر
        notification_system.create_notification("Other", "Msg", "other")
        notification_system.mark_all_as_read(source="test")
        # إشعارات test مقروءة، other لا
        for n in notification_system.notifications:
            if n.source == "test":
                assert n.read is True
            else:
                assert n.read is False


class TestNotificationSystemDelete:
    """اختبارات حذف الإشعارات"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem
        storage_file = tmp_path / "notifications.json"
        ns = NotificationSystem(storage_path=str(storage_file))
        ns.create_notification("Test 1", "Msg", "test")
        ns.create_notification("Test 2", "Msg", "test")
        return ns

    def test_delete_notification_existing(self, notification_system):
        """حذف إشعار موجود"""
        notif_id = notification_system.notifications[0].id
        notification_system.delete_notification(notif_id)
        assert len(notification_system.notifications) == 1
        assert notification_system.notifications[0].id != notif_id

    def test_delete_notification_nonexistent(self, notification_system):
        """حذف إشعار غير موجود → لا خطأ"""
        notification_system.delete_notification("nonexistent")
        assert len(notification_system.notifications) == 2


class TestNotificationSystemClearOld:
    """اختبارات مسح الإشعارات القديمة"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem
        storage_file = tmp_path / "notifications.json"
        return NotificationSystem(storage_path=str(storage_file))

    def test_clear_old_notifications(self, notification_system):
        """مسح الإشعارات الأقدم من N أيام"""
        # إضافة إشعار قديم
        old_notif = notification_system.create_notification("Old", "Msg", "test")
        # تعديل الوقت ليكون قديماً
        old_notif.timestamp = datetime.now() - timedelta(days=40)
        notification_system._save_notifications()

        # إضافة إشعار حديث
        notification_system.create_notification("New", "Msg", "test")

        notification_system.clear_old_notifications(days=30)
        assert len(notification_system.notifications) == 1
        assert notification_system.notifications[0].title == "New"

    def test_clear_old_notifications_zero_days(self, notification_system):
        """صفر أيام → يمسح الكل"""
        notification_system.create_notification("Test", "Msg", "test")
        notification_system.clear_old_notifications(days=0)
        assert len(notification_system.notifications) == 0


class TestNotificationSystemSubscribe:
    """اختبارات الاشتراك في الإشعارات"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem
        storage_file = tmp_path / "notifications.json"
        return NotificationSystem(storage_path=str(storage_file))

    def test_subscribe_and_unsubscribe(self, notification_system):
        """اشتراك وإلغاء اشتراك"""
        callback = MagicMock()
        notification_system.subscribe("test", callback)
        assert "test" in notification_system.subscribers
        assert callback in notification_system.subscribers["test"]

        notification_system.unsubscribe("test", callback)
        assert "test" not in notification_system.subscribers

    def test_subscribe_multiple_callbacks(self, notification_system):
        """عدة callbacks لنفس المصدر"""
        cb1 = MagicMock()
        cb2 = MagicMock()
        notification_system.subscribe("test", cb1)
        notification_system.subscribe("test", cb2)
        assert len(notification_system.subscribers["test"]) == 2

        # عند إنشاء إشعار، يُستدعى كلاهما
        notification_system.create_notification("Test", "Msg", "test")
        cb1.assert_called_once()
        cb2.assert_called_once()


class TestNotificationSystemGetSummary:
    """اختبارات ملخص الإشعارات"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem, NotificationType, NotificationPriority
        storage_file = tmp_path / "notifications.json"
        ns = NotificationSystem(storage_path=str(storage_file))
        ns.create_notification("Info", "Msg", "s1", notif_type=NotificationType.INFO, priority=NotificationPriority.LOW)
        ns.create_notification("Warning", "Msg", "s1", notif_type=NotificationType.WARNING, priority=NotificationPriority.HIGH)
        ns.create_notification("Error", "Msg", "s2", notif_type=NotificationType.ERROR, priority=NotificationPriority.CRITICAL)
        ns.notifications[0].read = True
        ns._save_notifications()
        return ns

    def test_get_summary(self, notification_system):
        """ملخص صحيح"""
        summary = notification_system.get_summary()
        assert summary["total"] == 3
        assert summary["unread"] == 2
        assert summary["by_type"]["info"] == 1
        assert summary["by_type"]["warning"] == 1
        assert summary["by_type"]["error"] == 1
        assert summary["by_priority"]["LOW"] == 1
        assert summary["by_priority"]["HIGH"] == 1
        assert summary["by_priority"]["CRITICAL"] == 1


class TestNotificationSystemNotifyCrash:
    """اختبارات إشعار الانهيار"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem
        storage_file = tmp_path / "notifications.json"
        return NotificationSystem(storage_path=str(storage_file))

    def test_notify_crash(self, notification_system):
        """إشعار انهيار بوت"""
        notif = notification_system.notify_crash("testbot", "Segmentation fault")
        assert "انهيار" in notif.title
        assert "testbot" in notif.title
        assert "Segmentation fault" in notif.message
        assert notif.type.value == "error"
        assert notif.priority.value == 4  # CRITICAL
        assert notif.data["error"] == "Segmentation fault"


class TestNotificationSystemNotifyRateLimit:
    """اختبارات إشعار تجاوز معدل الطلبات"""

    @pytest.fixture
    def notification_system(self, tmp_path):
        from notification_system import NotificationSystem
        storage_file = tmp_path / "notifications.json"
        return NotificationSystem(storage_path=str(storage_file))

    def test_notify_rate_limit(self, notification_system):
        """إشعار تجاوز حد الطلبات"""
        notif = notification_system.notify_rate_limit("testbot", 12345)
        assert "تجاوز" in notif.title
        assert "testbot" in notif.title
        assert "12345" in notif.message
        assert notif.type.value == "warning"
        assert notif.priority.value == 2  # MEDIUM
        assert notif.data["user_id"] == 12345


class TestGetNotificationSystemSingleton:
    """اختبار دالة get_notification_system (Singleton)"""

    def test_get_notification_system_singleton(self):
        """إرجاع نفس النسخة في كل استدعاء"""
        from notification_system import get_notification_system, _system_instance
        # إعادة تعيين
        import notification_system
        notification_system._system_instance = None

        ns1 = get_notification_system()
        ns2 = get_notification_system()
        assert ns1 is ns2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])