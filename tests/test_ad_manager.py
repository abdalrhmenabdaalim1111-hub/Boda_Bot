"""
tests/test_ad_manager.py — اختبارات نظام الإعلانات والاشتراك الإجباري
"""
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

from ad_manager import AdManager, get_ad_manager


@pytest.fixture
def temp_ad_manager(tmp_path):
    cfg_file = tmp_path / "test_ads_config.json"
    cfg = {
        "enabled": True,
        "force_subscribe": {
            "enabled": True,
            "channel_username": "@TestChannel",
            "channel_title": "قناة تجريبية",
            "invite_link": "https://t.me/TestChannel",
            "gate_message": "يرجى الاشتراك"
        },
        "footer_ad": {
            "enabled": True,
            "frequency": 2,
            "text": "\n📢 إعلان تجريبي"
        },
        "button_ad": {
            "enabled": True,
            "button_text": "رابط الراعي",
            "url": "https://example.com"
        }
    }
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return AdManager(config_file=cfg_file)


def test_ad_footer_frequency(temp_ad_manager):
    """اختبار ظهور الإعلان بحسب معدل التكرار frequency=2"""
    # الرسالة الأولى: لا يظهر
    msg1 = temp_ad_manager.attach_ad_to_text("مرحباً بك", user_id=101)
    assert msg1 == "مرحباً بك"

    # الرسالة الثانية: يظهر الإعلان
    msg2 = temp_ad_manager.attach_ad_to_text("نتيجتك هي 100", user_id=101)
    assert "📢 إعلان تجريبي" in msg2


def test_force_subscribe_allowed(temp_ad_manager):
    """اختبار السماح للمستخدم إذا كان عضواً في القناة"""
    mock_bot = MagicMock()
    mock_member = MagicMock()
    mock_member.status = "member"
    mock_bot.get_chat_member.return_value = mock_member

    allowed, msg, kb = temp_ad_manager.check_force_subscribe(mock_bot, user_id=101)
    assert allowed is True
    assert msg is None
    assert kb is None


def test_force_subscribe_blocked(temp_ad_manager):
    """اختبار منع المستخدم إذا لم يكن عضواً في القناة"""
    mock_bot = MagicMock()
    mock_member = MagicMock()
    mock_member.status = "left"
    mock_bot.get_chat_member.return_value = mock_member

    allowed, msg, kb = temp_ad_manager.check_force_subscribe(mock_bot, user_id=102)
    assert allowed is False
    assert "يرجى الاشتراك" in msg
    assert kb is not None


def test_ad_button(temp_ad_manager):
    """اختبار زر الإعلان Inline"""
    btn = temp_ad_manager.get_ad_button()
    assert btn is not None
    assert btn.text == "رابط الراعي"
    assert btn.url == "https://example.com"


def test_disabled_ads(temp_ad_manager):
    """اختبار تعطيل الإعلانات تماماً"""
    temp_ad_manager.config["enabled"] = False
    assert temp_ad_manager.get_footer_ad() == ""
    assert temp_ad_manager.get_ad_button() is None

