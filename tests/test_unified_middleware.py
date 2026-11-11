"""
tests/test_unified_middleware.py — اختبارات شاملة للطبقة الموحدة (Unified Middleware)
تغطي: webapp_keyboard, setup_menu_button, UnifiedBotMiddleware (pre_process, post_process, _send_promo),
install_unified_layer, get_miniapps_url
"""
import os
import sys
import pytest
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

# استيراد الوحدة مباشرة
import unified_middleware


def _patch_miniapps_url(url: str):
    """patch للـ MINIAPPS_BASE_URL في الوحدة"""
    return patch.object(unified_middleware, "MINIAPPS_BASE_URL", url.strip().rstrip("/"))


class TestUnifiedMiddlewareGetMiniappsUrl:
    """اختبارات دالة get_miniapps_url"""

    def test_get_miniapps_url_with_env(self):
        """مع متغير بيئة MINIAPPS_BASE_URL → يعيد رابط صحيح"""
        with _patch_miniapps_url("https://example.com/bots"):
            url = unified_middleware.get_miniapps_url("currency")
            assert url == "https://example.com/bots/currency/"

    def test_get_miniapps_url_without_env(self):
        """بدون متغير بيئة → نص فارغ"""
        with _patch_miniapps_url(""):
            url = unified_middleware.get_miniapps_url("currency")
            assert url == ""

    def test_get_miniapps_url_strips_trailing_slash(self):
        """يزيل slash النهائية من القاعدة"""
        with _patch_miniapps_url("https://example.com/bots/"):
            url = unified_middleware.get_miniapps_url("currency")
            assert url == "https://example.com/bots/currency/"


class TestUnifiedMiddlewareWebappKeyboard:
    """اختبارات دالة webapp_keyboard"""

    def test_webapp_keyboard_with_url(self):
        """مع رابط تطبيق → يعيد لوحة مفاتيح بها أزرار"""
        with _patch_miniapps_url("https://example.com/bots"):
            kb = unified_middleware.webapp_keyboard("currency")
            assert kb is not None
            assert len(kb.keyboard) >= 2
            found_webapp = False
            for row in kb.keyboard:
                for btn in row:
                    if hasattr(btn, 'web_app') and btn.web_app:
                        found_webapp = True
                        assert btn.web_app.url == "https://example.com/bots/currency/"
            assert found_webapp

    def test_webapp_keyboard_without_url(self):
        """بدون رابط تطبيق → لوحة بها زر المتجر فقط"""
        with _patch_miniapps_url(""):
            kb = unified_middleware.webapp_keyboard("currency")
            assert kb is not None
            # يجب أن يحتوي على زر المتجر فقط
            assert len(kb.keyboard) >= 1
            found_store = False
            for row in kb.keyboard:
                for btn in row:
                    if hasattr(btn, 'url') and 'BodaStoreeBot' in btn.url:
                        found_store = True
            assert found_store

    def test_webapp_keyboard_sponsor_button(self):
        """زر الراعي Monetag يظهر عند وجود شفرة إعلانية"""
        with _patch_miniapps_url("https://example.com/bots"):
            with patch("ad_manager.get_ad_manager") as mock_get_ad_manager:
                mock_mgr = MagicMock()
                mock_mgr.build_ad_click_url.return_value = "https://t.me/BodaStoreeBot?start=adclick_currency"
                mock_get_ad_manager.return_value = mock_mgr

                kb = unified_middleware.webapp_keyboard("currency")
                found_sponsor = False
                for row in kb.keyboard:
                    for btn in row:
                        if hasattr(btn, 'text') and 'عرض حصري' in btn.text:
                            found_sponsor = True
                            assert btn.url == "https://t.me/BodaStoreeBot?start=adclick_currency"
                assert found_sponsor


class TestUnifiedMiddlewareSetupMenuButton:
    """اختبارات دالة setup_menu_button"""

    def test_setup_menu_button_with_url(self):
        """مع رابط → يستدعي set_chat_menu_button ويعيد True"""
        with _patch_miniapps_url("https://example.com/bots"):
            mock_bot = MagicMock()
            mock_bot.set_chat_menu_button = MagicMock(return_value=True)

            result = unified_middleware.setup_menu_button(mock_bot, "currency")
            assert result is True
            mock_bot.set_chat_menu_button.assert_called_once()

    def test_setup_menu_button_without_url(self):
        """بدون رابط → يعيد False دون استدعاء API"""
        with _patch_miniapps_url(""):
            mock_bot = MagicMock()
            result = unified_middleware.setup_menu_button(mock_bot, "currency")
            assert result is False
            mock_bot.set_chat_menu_button.assert_not_called()

    def test_setup_menu_button_exception(self):
        """استثناء في API → يعيد False"""
        with _patch_miniapps_url("https://example.com/bots"):
            mock_bot = MagicMock()
            mock_bot.set_chat_menu_button = MagicMock(side_effect=Exception("API Error"))

            result = unified_middleware.setup_menu_button(mock_bot, "currency")
            assert result is False


# ── البرمجية الوسيطة ──────────────────────────────────────────────────────────


def _make_middleware_with_url():
    """إنشاء ميدل وير مع متغير بيئة مفعل"""
    with _patch_miniapps_url("https://example.com/bots"):
        mock_bot = MagicMock()
        mw = unified_middleware.UnifiedBotMiddleware(mock_bot, "testbot")
        return mw, mock_bot


def _make_middleware_without_url():
    """إنشاء ميدل وير بدون متغير بيئة"""
    mock_bot = MagicMock()
    mw = unified_middleware.UnifiedBotMiddleware(mock_bot, "testbot")
    return mw, mock_bot


class TestUnifiedBotMiddleware:
    """اختبارات كلاس UnifiedBotMiddleware"""

    def test_pre_process_tracks_user_private(self):
        """pre_process: يتتبع المستخدم في المحادثات الخاصة"""
        mw, mock_bot = _make_middleware_with_url()
        mock_msg = MagicMock()
        mock_msg.from_user.id = 123
        mock_msg.from_user.first_name = "Test"
        mock_msg.from_user.last_name = "User"
        mock_msg.from_user.username = "testuser"
        mock_msg.chat.type = "private"
        mock_msg.text = "/start"

        with patch("unified_middleware.track_user") as mock_track:
            mw.pre_process(mock_msg, {})
            mock_track.assert_called_once_with("testbot", 123, "Test User", "testuser")

    def test_pre_process_skips_group_chat(self):
        """pre_process: لا يتتبع في المجموعات"""
        mw, mock_bot = _make_middleware_with_url()
        mock_msg = MagicMock()
        mock_msg.from_user.id = 123
        mock_msg.chat.type = "group"
        mock_msg.text = "/start"

        with patch("unified_middleware.track_user") as mock_track:
            mw.pre_process(mock_msg, {})
            mock_track.assert_not_called()

    def test_pre_process_sends_promo_on_start_first_time(self):
        """pre_process: يرسل بطاقة التطبيق مرة واحدة عند /start"""
        # السياق يُبقي رابط التطبيق مرقّعاً أثناء pre_process نفسها —
        # لا اعتماد على MINIAPPS_BASE_URL من .env المحلي (مستقل عن البيئة)
        with _patch_miniapps_url("https://example.com/bots"):
            mw, mock_bot = _make_middleware_without_url()
            mock_msg = MagicMock()
            mock_msg.from_user.id = 123
            mock_msg.chat.type = "private"
            mock_msg.text = "/start"

            with patch("threading.Timer") as mock_timer:
                mock_timer_instance = MagicMock()
                mock_timer.return_value = mock_timer_instance
                mw.pre_process(mock_msg, {})
                mock_timer.assert_called_once()
                call_args = mock_timer.call_args
                callback = call_args[0][1]
                callback(123)
                mock_bot.send_message.assert_called()
                call_args = mock_bot.send_message.call_args
                text = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("text", "")
                assert "تفاعلية" in text

    def test_pre_process_no_promo_on_second_start(self):
        """pre_process: لا يرسل البطاقة مرة ثانية"""
        with _patch_miniapps_url("https://example.com/bots"):
            mw, mock_bot = _make_middleware_without_url()
            mock_msg = MagicMock()
            mock_msg.from_user.id = 123
            mock_msg.chat.type = "private"
            mock_msg.text = "/start"

            with patch("threading.Timer"):
                mw.pre_process(mock_msg, {})
                mw.pre_process(mock_msg, {})
            assert 123 in mw._promo_sent

    def test_pre_process_no_promo_without_url(self):
        """pre_process: لا بطاقة بدون MINIAPPS_BASE_URL"""
        with _patch_miniapps_url(""):
            mw, mock_bot = _make_middleware_without_url()
            mock_msg = MagicMock()
            mock_msg.from_user.id = 123
            mock_msg.chat.type = "private"
            mock_msg.text = "/start"

            with patch("threading.Timer") as mock_timer:
                mw.pre_process(mock_msg, {})
                mock_timer.assert_not_called()
                mock_bot.send_message.assert_not_called()


class TestUnifiedBotMiddlewarePostProcess:
    """اختبارات post_process"""

    def test_post_process_tracks_exception(self):
        """post_process: يتتبع الاستثناءات عبر error_tracker"""
        mw, mock_bot = _make_middleware_with_url()
        mock_msg = MagicMock()
        mock_msg.from_user.id = 123
        mock_msg.text = "/test"

        test_exc = ValueError("Test error")

        with patch("error_tracker.track_exception") as mock_track:
            mw.post_process(mock_msg, {}, test_exc)
            mock_track.assert_called_once_with("testbot", test_exc, user_id=123, context="/test")

    def test_post_process_no_user_id(self):
        """post_process: يعمل حتى لو لم يكن هناك user_id"""
        mw, mock_bot = _make_middleware_with_url()
        mock_msg = MagicMock()
        mock_msg.from_user = None
        mock_msg.text = "/test"

        test_exc = ValueError("Test error")

        with patch("error_tracker.track_exception") as mock_track:
            mw.post_process(mock_msg, {}, test_exc)
            mock_track.assert_called_once_with("testbot", test_exc, user_id=None, context="/test")

    def test_post_process_logs_slow_response(self):
        """post_process: يسجل تحذير للاستجابات البطيئة (>3000ms)"""
        mw, mock_bot = _make_middleware_with_url()
        mock_msg = MagicMock()
        mock_msg.from_user.id = 123

        data = {"_t0": time.time() - 4}

        with patch.object(mw.log, "warning") as mock_warning:
            mw.post_process(mock_msg, data, None)
            mock_warning.assert_called()

    def test_post_process_no_slow_log_for_fast(self):
        """post_process: لا يسجل تحذير للاستجابات السريعة"""
        mw, mock_bot = _make_middleware_with_url()
        mock_msg = MagicMock()
        mock_msg.from_user.id = 123

        data = {"_t0": time.time() - 0.1}

        with patch.object(mw.log, "warning") as mock_warning:
            mw.post_process(mock_msg, data, None)
            mock_warning.assert_not_called()


class TestInstallUnifiedLayer:
    """اختبارات دالة install_unified_layer"""

    def test_install_unified_layer_with_url(self):
        """مع رابط → يفعّل زر القائمة والميدل وير"""
        with _patch_miniapps_url("https://example.com/bots"):
            mock_bot = MagicMock()
            mock_bot.get_me.return_value = MagicMock(username="TestBot")
            mock_bot.use_class_middlewares = False
            mock_bot.middlewares = None

            unified_middleware.install_unified_layer(mock_bot, "testbot")

            assert mock_bot.use_class_middlewares is True
            assert mock_bot.middlewares is not None
            mock_bot.setup_middleware.assert_called()

    def test_install_unified_layer_without_url(self):
        """بدون رابط → يفعّل التتبع فقط"""
        with _patch_miniapps_url(""):
            mock_bot = MagicMock()
            mock_bot.get_me.return_value = MagicMock(username="TestBot")
            mock_bot.use_class_middlewares = False
            mock_bot.middlewares = None

            unified_middleware.install_unified_layer(mock_bot, "testbot")

            assert mock_bot.use_class_middlewares is True
            mock_bot.setup_middleware.assert_called()

    def test_install_unified_layer_handles_exception(self):
        """يتعامل مع الاستثناءات بأمان"""
        with _patch_miniapps_url("https://example.com/bots"):
            mock_bot = MagicMock()
            mock_bot.get_me.return_value = MagicMock(username="TestBot")
            mock_bot.use_class_middlewares = True
            mock_bot.middlewares = []
            mock_bot.setup_middleware = MagicMock(side_effect=Exception("Middleware error"))

            unified_middleware.install_unified_layer(mock_bot, "testbot")


class TestSendPromo:
    """اختبار دالة _send_promo الداخلية"""

    def test_send_promo_sends_message(self):
        """_send_promo يرسل رسالة بالبطاقة"""
        mw, mock_bot = _make_middleware_with_url()

        mw._send_promo(123)
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        text = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("text", "")
        assert "تفاعلية" in text
        assert "reply_markup" in call_args[1]

    def test_send_promo_handles_exception(self):
        """_send_promo يتجاهل الاستثناءات (مستخدم محظور)"""
        mw, mock_bot = _make_middleware_with_url()
        mock_bot.send_message = MagicMock(side_effect=Exception("User blocked"))

        mw._send_promo(123)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])