"""
tests/test_ad_manager.py — اختبارات شاملة لنظام إدارة الإعلانات (ad_manager)
تغطي: Monetag config, ad_click tracking, force_subscribe, footer/button ads
"""
import json
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))


class TestAdManagerMonetag:
    """اختبارات إعدادات إعلانات Monetag"""

    @pytest.fixture
    def ad_manager(self, tmp_path, monkeypatch):
        """مدير إعلانات بملفات إعدادات مؤقتة"""
        from ad_manager import AdManager

        cfg_file = tmp_path / "ads_config.json"
        mon_file = tmp_path / "monetag_config.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "force_subscribe": {"enabled": False},
            "footer_ad": {"enabled": True, "frequency": 1, "text": "TEST AD"},
            "button_ad": {"enabled": True, "button_text": "Btn", "url": "https://t.me/Test"}
        }, ensure_ascii=False), encoding="utf-8")

        mon_file.write_text(json.dumps({
            "global_default": {
                "enabled": True,
                "direct_link": "https://global.monetag.com/link",
                "zone_id": "12345",
                "script_url": "",
                "format": "direct_link",
                "frequency": 3
            },
            "bots": {
                "currency": {
                    "has_custom_ads": True,
                    "direct_link": "https://currency.monetag.com/link",
                    "zone_id": "67890",
                    "format": "direct_link",
                    "frequency": 2,
                    "active": True
                }
            }
        }, ensure_ascii=False), encoding="utf-8")

        mgr = AdManager(config_file=cfg_file, monetag_file=mon_file)
        return mgr

    def test_get_monetag_config_custom(self, ad_manager):
        """البوت ذو الإعداد المخصص يرجع إعداداته"""
        cfg = ad_manager.get_monetag_config("currency")
        assert cfg["direct_link"] == "https://currency.monetag.com/link"
        assert cfg["zone_id"] == "67890"
        assert cfg["frequency"] == 2

    def test_get_monetag_config_global_fallback(self, ad_manager):
        """بوت بلا إعداد مخصص يرجع الإعداد العام"""
        cfg = ad_manager.get_monetag_config("vidload")  # لا يوجد في bots
        assert cfg["direct_link"] == "https://global.monetag.com/link"
        assert cfg["zone_id"] == "12345"
        assert cfg.get("is_global_fallback") is True

    def test_has_monetag_ad_true(self, ad_manager):
        """بوت له شفرة إعلانية (مخصصة أو عامة) → True"""
        assert ad_manager.has_monetag_ad("currency") is True
        assert ad_manager.has_monetag_ad("vidload") is True  # يستخدم العام

    def test_has_monetag_ad_false(self, ad_manager, tmp_path):
        """بلا شفرة عامة → False"""
        # Manager جديد بلا شفرة عامة
        cfg_file = tmp_path / "ads2.json"
        mon_file = tmp_path / "mon2.json"
        cfg_file.write_text(json.dumps({"enabled": True}), encoding="utf-8")
        mon_file.write_text(json.dumps({
            "global_default": {"enabled": False, "direct_link": "", "zone_id": ""},
            "bots": {}
        }, ensure_ascii=False), encoding="utf-8")

        from ad_manager import AdManager
        mgr = AdManager(config_file=cfg_file, monetag_file=mon_file)
        assert mgr.has_monetag_ad("anybot") is False

    def test_has_custom_monetag_ad(self, ad_manager):
        """كشف الإعدادات المخصصة فقط"""
        assert ad_manager.has_custom_monetag_ad("currency") is True
        assert ad_manager.has_custom_monetag_ad("vidload") is False

    def test_set_monetag_config_creates_custom(self, ad_manager):
        """إضافة إعداد مخصص جديد"""
        result = ad_manager.set_monetag_config(
            "newbot",
            direct_link="https://new.monetag.com/link",
            zone_id="99999",
            frequency=5
        )
        assert result is True
        cfg = ad_manager.get_monetag_config("newbot")
        assert cfg["direct_link"] == "https://new.monetag.com/link"
        assert cfg["zone_id"] == "99999"
        assert cfg["frequency"] == 5
        assert cfg["has_custom_ads"] is True

    def test_set_monetag_config_empty_disables(self, ad_manager):
        """إضافة بلا شفرة → معطل"""
        ad_manager.set_monetag_config("emptybot", direct_link="", zone_id="")
        cfg = ad_manager.get_monetag_config("emptybot")
        assert cfg.get("active") is False

    def test_set_global_monetag_default(self, ad_manager):
        """تحديث الشفرة العامة"""
        result = ad_manager.set_global_monetag_default(
            direct_link="https://new-global.monetag.com/link",
            zone_id="11111",
            frequency=4
        )
        assert result is True
        cfg = ad_manager.get_monetag_config("fallbackbot")
        assert cfg["direct_link"] == "https://new-global.monetag.com/link"
        assert cfg["zone_id"] == "11111"
        assert cfg["frequency"] == 4

    def test_get_all_monetag_statuses(self, ad_manager):
        """تقرير شامل لجميع البوتات"""
        statuses = ad_manager.get_all_monetag_statuses()
        assert "currency" in statuses
        assert statuses["currency"]["has_ad"] is True
        assert statuses["currency"]["is_custom"] is True
        assert statuses["currency"]["format"] == "direct_link"


class TestAdManagerClickTracking:
    """اختبارات تتبع نقرات الإعلانات عبر الروابط العميقة"""

    @pytest.fixture
    def ad_manager(self, tmp_path):
        from ad_manager import AdManager
        cfg_file = tmp_path / "ads.json"
        mon_file = tmp_path / "mon.json"
        cfg_file.write_text(json.dumps({"enabled": True}, ensure_ascii=False), encoding="utf-8")
        mon_file.write_text(json.dumps({
            "global_default": {"enabled": True, "direct_link": "https://global.link", "zone_id": "123"},
            "bots": {"testbot": {"has_custom_ads": True, "direct_link": "https://test.link", "zone_id": "456", "active": True}}
        }, ensure_ascii=False), encoding="utf-8")
        return AdManager(config_file=cfg_file, monetag_file=mon_file)

    def test_build_ad_click_url_with_custom(self, ad_manager):
        """بوت له شفرة مخصصة → رابط تتبع للمتجر"""
        url = ad_manager.build_ad_click_url("testbot")
        assert url.startswith("https://t.me/BodaStoreeBot?start=adclick_testbot")

    def test_build_ad_click_url_with_global(self, ad_manager):
        """بوت يستخدم الشفرة العامة → رابط تتبع"""
        url = ad_manager.build_ad_click_url("globalbot")
        assert url.startswith("https://t.me/BodaStoreeBot?start=adclick_globalbot")

    def test_build_ad_click_url_no_ad(self, ad_manager, tmp_path):
        """بلا شفرة → نص فارغ"""
        cfg_file = tmp_path / "ads3.json"
        mon_file = tmp_path / "mon3.json"
        cfg_file.write_text(json.dumps({"enabled": True}, ensure_ascii=False), encoding="utf-8")
        mon_file.write_text(json.dumps({
            "global_default": {"enabled": False, "direct_link": ""},
            "bots": {}
        }, ensure_ascii=False), encoding="utf-8")
        from ad_manager import AdManager
        mgr = AdManager(config_file=cfg_file, monetag_file=mon_file)
        assert mgr.build_ad_click_url("noadbot") == ""

    def test_resolve_ad_click_records_and_returns(self, ad_manager):
        """تسجيل النقرة وإرجاع معلومات العرض"""
        with patch("database.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            result = ad_manager.resolve_ad_click("testbot")
            assert result is not None
            assert result["bot_id"] == "testbot"
            assert result["direct_link"] == "https://test.link"
            assert result["zone_id"] == "456"
            mock_db.record_ad_click.assert_called_once_with("testbot", "direct_link")


class TestAdManagerForceSubscribe:
    """اختبارات بوابة الاشتراك الإجباري"""

    @pytest.fixture
    def ad_manager_enabled(self, tmp_path):
        from ad_manager import AdManager
        cfg_file = tmp_path / "ads.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "force_subscribe": {
                "enabled": True,
                "channel_username": "@TestChannel",
                "channel_title": "Test Channel",
                "invite_link": "https://t.me/TestChannel",
                "gate_message": "Please subscribe"
            }
        }, ensure_ascii=False), encoding="utf-8")
        mon_file = tmp_path / "mon.json"
        mon_file.write_text(json.dumps({"global_default": {}, "bots": {}}, ensure_ascii=False), encoding="utf-8")
        return AdManager(config_file=cfg_file, monetag_file=mon_file)

    @pytest.fixture
    def ad_manager_disabled(self, tmp_path):
        from ad_manager import AdManager
        cfg_file = tmp_path / "ads.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "force_subscribe": {"enabled": False}
        }, ensure_ascii=False), encoding="utf-8")
        mon_file = tmp_path / "mon.json"
        mon_file.write_text(json.dumps({"global_default": {}, "bots": {}}, ensure_ascii=False), encoding="utf-8")
        return AdManager(config_file=cfg_file, monetag_file=mon_file)

    def test_check_force_subscribe_disabled(self, ad_manager_disabled):
        """معطل كلياً → السماح"""
        mock_bot = MagicMock()
        allowed, msg, kb = ad_manager_disabled.check_force_subscribe(mock_bot, 123)
        assert allowed is True
        assert msg is None

    def test_check_force_subscribe_subscribed(self, ad_manager_enabled):
        """مستخدم مشترك → السماح"""
        mock_bot = MagicMock()
        mock_member = MagicMock()
        mock_member.status = "member"
        mock_bot.get_chat_member.return_value = mock_member

        allowed, msg, kb = ad_manager_enabled.check_force_subscribe(mock_bot, 123)
        assert allowed is True
        assert msg is None
        mock_bot.get_chat_member.assert_called_once_with("@TestChannel", 123)

    def test_check_force_subscribe_admin(self, ad_manager_enabled):
        """أدمن في القناة → السماح"""
        mock_bot = MagicMock()
        mock_member = MagicMock()
        mock_member.status = "administrator"
        mock_bot.get_chat_member.return_value = mock_member

        allowed, msg, kb = ad_manager_enabled.check_force_subscribe(mock_bot, 123)
        assert allowed is True

    def test_check_force_subscribe_not_subscribed(self, ad_manager_enabled):
        """غير مشترك → بوابة الاشتراك"""
        mock_bot = MagicMock()
        mock_member = MagicMock()
        mock_member.status = "left"
        mock_bot.get_chat_member.return_value = mock_member

        allowed, msg, kb = ad_manager_enabled.check_force_subscribe(mock_bot, 123)
        assert allowed is False
        assert "Please subscribe" in msg
        assert kb is not None

    def test_check_force_subscribe_api_error_fails_open(self, ad_manager_enabled):
        """خطأ API → السماح (fail-open)"""
        mock_bot = MagicMock()
        mock_bot.get_chat_member.side_effect = Exception("Network error")

        allowed, msg, kb = ad_manager_enabled.check_force_subscribe(mock_bot, 123)
        assert allowed is True  # fail-open
        assert msg is None


class TestAdManagerFooterButton:
    """اختبارات إعلانات الذيل والأزرار"""

    @pytest.fixture
    def ad_manager(self, tmp_path):
        from ad_manager import AdManager
        cfg_file = tmp_path / "ads.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "footer_ad": {"enabled": True, "frequency": 3, "text": "\n📢 FOOTER AD"},
            "button_ad": {"enabled": True, "button_text": "🌟 Button", "url": "https://t.me/Test"}
        }, ensure_ascii=False), encoding="utf-8")
        mon_file = tmp_path / "mon.json"
        mon_file.write_text(json.dumps({"global_default": {}, "bots": {}}, ensure_ascii=False), encoding="utf-8")
        return AdManager(config_file=cfg_file, monetag_file=mon_file)

    def test_get_footer_ad_frequency(self, ad_manager):
        """تكرار الإعلان حسب frequency"""
        # أول رسالتين بلا إعلان (frequency=3)
        assert ad_manager.get_footer_ad(1) == ""
        assert ad_manager.get_footer_ad(1) == ""
        # الثالثة بها إعلان
        assert "FOOTER AD" in ad_manager.get_footer_ad(1)
        # رابعة خامسة بلا إعلان
        assert ad_manager.get_footer_ad(1) == ""
        assert ad_manager.get_footer_ad(1) == ""
        # سادسة بها إعلان
        assert "FOOTER AD" in ad_manager.get_footer_ad(1)

    def test_get_footer_ad_disabled(self, tmp_path):
        """معطل → نص فارغ"""
        from ad_manager import AdManager
        cfg_file = tmp_path / "ads.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "footer_ad": {"enabled": False}
        }, ensure_ascii=False), encoding="utf-8")
        mon_file = tmp_path / "mon.json"
        mon_file.write_text(json.dumps({"global_default": {}, "bots": {}}, ensure_ascii=False), encoding="utf-8")
        mgr = AdManager(config_file=cfg_file, monetag_file=mon_file)
        assert mgr.get_footer_ad(1) == ""

    def test_attach_ad_to_text(self, ad_manager):
        """دمج الإعلان مع النص"""
        # لا تكرار - أول رسالة
        result = ad_manager.attach_ad_to_text("Hello", user_id=1)
        assert result == "Hello"  # frequency=3, العداد = 1

        # ثاني رسالة
        result = ad_manager.attach_ad_to_text("Hello", user_id=1)
        assert result == "Hello"  # العداد = 2

        # ثالثة - تظهر الإعلان
        result = ad_manager.attach_ad_to_text("Hello", user_id=1)
        assert "FOOTER AD" in result  # العداد = 3

    def test_get_ad_button(self, ad_manager):
        """إرجاع زر الإعلان"""
        btn = ad_manager.get_ad_button()
        assert btn is not None
        assert btn.text == "🌟 Button"
        assert btn.url == "https://t.me/Test"

    def test_get_ad_button_disabled(self, tmp_path):
        """معطل → None"""
        from ad_manager import AdManager
        cfg_file = tmp_path / "ads.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "button_ad": {"enabled": False}
        }, ensure_ascii=False), encoding="utf-8")
        mon_file = tmp_path / "mon.json"
        mon_file.write_text(json.dumps({"global_default": {}, "bots": {}}, ensure_ascii=False), encoding="utf-8")
        mgr = AdManager(config_file=cfg_file, monetag_file=mon_file)
        assert mgr.get_ad_button() is None


class TestAdManagerAttachUnifiedAds:
    """اختبار التركيب التلقائي على البوت"""

    @pytest.fixture
    def ad_manager(self, tmp_path):
        from ad_manager import AdManager
        cfg_file = tmp_path / "ads.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "footer_ad": {"enabled": True, "frequency": 1, "text": "\n📢 AD"},
            "button_ad": {"enabled": False}
        }, ensure_ascii=False), encoding="utf-8")
        mon_file = tmp_path / "mon.json"
        mon_file.write_text(json.dumps({"global_default": {}, "bots": {}}, ensure_ascii=False), encoding="utf-8")
        return AdManager(config_file=cfg_file, monetag_file=mon_file)

    def test_attach_unified_ads_wraps_send_message(self, tmp_path):
        """attach_unified_ads يغلّف send_message"""
        from ad_manager import AdManager, attach_unified_ads, get_ad_manager
        import json

        cfg_file = tmp_path / "ads.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "footer_ad": {"enabled": True, "frequency": 1, "text": "\n📢 AD"},
            "button_ad": {"enabled": False}
        }, ensure_ascii=False), encoding="utf-8")
        mon_file = tmp_path / "mon.json"
        mon_file.write_text(json.dumps({"global_default": {}, "bots": {}}, ensure_ascii=False), encoding="utf-8")

        # إعادة تعيين singleton لاستخدام إعدادات الاختبار
        import ad_manager
        ad_manager._ad_manager_instance = None
        mgr = AdManager(config_file=cfg_file, monetag_file=mon_file)
        ad_manager._ad_manager_instance = mgr

        # محاكاة bot
        mock_bot = MagicMock()
        original_send = MagicMock(return_value=MagicMock())
        mock_bot.send_message = original_send

        attach_unified_ads(mock_bot, "testbot")

        # استدعاء send_message المغلف
        mock_bot.send_message(123, "Test message")

        # التحقق من إضافة الإعلان
        call_args = original_send.call_args
        text = call_args[1].get("text") if "text" in call_args[1] else call_args[0][1]
        assert "📢 AD" in text

    def test_attach_unified_ads_private_chat_only(self, tmp_path):
        """الإعلان في المحادثات الخاصة فقط (chat_id موجب)"""
        from ad_manager import AdManager, attach_unified_ads, get_ad_manager
        import json

        cfg_file = tmp_path / "ads.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "footer_ad": {"enabled": True, "frequency": 1, "text": "\n📢 AD"},
            "button_ad": {"enabled": False}
        }, ensure_ascii=False), encoding="utf-8")
        mon_file = tmp_path / "mon.json"
        mon_file.write_text(json.dumps({"global_default": {}, "bots": {}}, ensure_ascii=False), encoding="utf-8")

        # إعادة تعيين singleton
        import ad_manager
        ad_manager._ad_manager_instance = None
        mgr = AdManager(config_file=cfg_file, monetag_file=mon_file)
        ad_manager._ad_manager_instance = mgr

        mock_bot = MagicMock()
        original_send = MagicMock(return_value=MagicMock())
        mock_bot.send_message = original_send

        attach_unified_ads(mock_bot, "testbot")

        # محادثة خاصة
        mock_bot.send_message(123, "Test")
        call_args = original_send.call_args
        text = call_args[1].get("text") if "text" in call_args[1] else call_args[0][1]
        assert "📢 AD" in text

        # مجموعة (chat_id سالب) - لا إعلان
        original_send.reset_mock()
        mock_bot.send_message(-100, "Test")
        call_args = original_send.call_args
        text = call_args[1].get("text") if "text" in call_args[1] else call_args[0][1]
        assert "📢 AD" not in text


class TestParseAdClickPayload:
    """اختبار تحليل حمولة تتبع النقرات"""

    def test_parse_valid_payload(self):
        from ad_manager import parse_ad_click_payload
        assert parse_ad_click_payload("/start adclick_currency") == "currency"
        assert parse_ad_click_payload("/start adclick_vidload ") == "vidload"
        # The function expects /start prefix, so without it returns empty
        assert parse_ad_click_payload("/start adclick_test") == "test"

    def test_parse_invalid_payload(self):
        from ad_manager import parse_ad_click_payload
        assert parse_ad_click_payload("/start") == ""
        assert parse_ad_click_payload("/start ref_123") == ""
        assert parse_ad_click_payload("") == ""
        assert parse_ad_click_payload("adclick_") == ""  # فارغ
        assert parse_ad_click_payload("adclick_INVALID@") == ""  # حروف غير صالحة
        assert parse_ad_click_payload("/start adclick_") == ""  # فارغ بعد البادئة


class TestGetMonetagButton:
    """اختبار زر Monetag في لوحة المفاتيح"""

    def test_get_monetag_button_with_link(self):
        from ad_manager import get_ad_manager, get_monetag_button
        mgr = get_ad_manager()
        # Setup
        mgr.set_global_monetag_default(direct_link="https://monetag.link")

        btn = get_monetag_button("currency")
        assert btn is not None
        assert "راعي" in btn.text or "عرض" in btn.text

    def test_get_monetag_button_without_link(self):
        from ad_manager import get_ad_manager, get_monetag_button
        mgr = get_ad_manager()
        mgr.set_global_monetag_default(direct_link="")

        btn = get_monetag_button("nobot")
        assert btn is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])