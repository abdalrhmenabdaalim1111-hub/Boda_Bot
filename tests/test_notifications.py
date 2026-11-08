"""
tests/test_notifications.py — اختبارات نظام الإشعارات والتنبيهات
"""
import pytest
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

from notification_system import (
    NotificationSystem,
    NotificationType,
    NotificationPriority,
    get_notification_system
)


@pytest.fixture
def temp_notif_system(tmp_path):
    storage = tmp_path / "test_notifs.json"
    return NotificationSystem(storage_path=str(storage))


def test_create_and_get_notification(temp_notif_system):
    """اختبار إنشاء واسترجاع إشعار"""
    n = temp_notif_system.create_notification(
        title="Test Alert",
        message="Test Message Content",
        source="test_bot",
        notif_type=NotificationType.INFO,
        priority=NotificationPriority.MEDIUM
    )
    assert n.title == "Test Alert"
    assert n.read is False

    notifs = temp_notif_system.get_notifications()
    assert len(notifs) == 1
    assert notifs[0].id == n.id


def test_mark_as_read(temp_notif_system):
    """اختبار تعليم الإشعار كمقروء"""
    n = temp_notif_system.create_notification(
        title="Alert",
        message="Content",
        source="currency"
    )
    temp_notif_system.mark_as_read(n.id)
    unread = temp_notif_system.get_notifications(unread_only=True)
    assert len(unread) == 0


def test_notify_crash(temp_notif_system):
    """اختبار إشعار الانهيار Critical Crash"""
    crash_notif = temp_notif_system.notify_crash("currency", "ConnectionResetError")
    assert crash_notif.priority == NotificationPriority.CRITICAL
    assert crash_notif.type == NotificationType.ERROR
    assert "currency" in crash_notif.title


def test_notify_rate_limit(temp_notif_system):
    """اختبار إشعار تجاوز الحد Warning Rate Limit"""
    rl_notif = temp_notif_system.notify_rate_limit("fun_name", 998877)
    assert rl_notif.priority == NotificationPriority.MEDIUM
    assert rl_notif.type == NotificationType.WARNING
    assert "998877" in rl_notif.message


def test_get_summary(temp_notif_system):
    """اختبار ملخص الإشعارات"""
    temp_notif_system.notify_crash("bot_a", "Err")
    temp_notif_system.notify_rate_limit("bot_b", 123)
    summary = temp_notif_system.get_summary()

    assert summary["total"] == 2
    assert summary["unread"] == 2
    assert summary["by_priority"]["CRITICAL"] == 1

