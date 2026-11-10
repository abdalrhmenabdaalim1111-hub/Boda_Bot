# =============================================================================
#  tests/test_bot_base.py — اختبارات الفئة الأساسية للبوتات
# =============================================================================
import sys
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))


class TestGetToken:
    """اختبارات دالة get_token"""

    def test_returns_empty_when_no_env(self):
        from bot_base import get_token
        with patch.dict(os.environ, {}, clear=True):
            # مفتاح غير موجود → فارغ
            assert get_token("NON_EXISTENT_KEY_XYZ") == ""

    def test_returns_fallback_when_no_env(self):
        from bot_base import get_token
        with patch.dict(os.environ, {}, clear=True):
            result = get_token("NON_EXISTENT_KEY", fallback="1234567890:ABC")
            assert result == "1234567890:ABC"

    def test_ignores_placeholder_value(self):
        from bot_base import get_token
        with patch.dict(os.environ, {"BOT_TOKEN": "ضع_التوكن_هنا"}):
            assert get_token("BOT_TOKEN") == ""

    def test_returns_real_token(self):
        from bot_base import get_token
        fake_token = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        with patch.dict(os.environ, {"BOT_TOKEN": fake_token}):
            assert get_token("BOT_TOKEN") == fake_token

    def test_strips_whitespace(self):
        from bot_base import get_token
        fake_token = "  1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef  "
        with patch.dict(os.environ, {"BOT_TOKEN": fake_token}):
            assert get_token("BOT_TOKEN") == fake_token.strip()


class TestGetLogger:
    """اختبارات دالة get_logger"""

    def test_returns_logger_instance(self):
        import logging
        from bot_base import get_logger
        log = get_logger("test_bot")
        assert isinstance(log, logging.Logger)

    def test_logger_has_handler(self):
        from bot_base import get_logger
        log = get_logger("test_bot_handler")
        assert len(log.handlers) > 0

    def test_different_bots_have_different_loggers(self):
        from bot_base import get_logger
        log1 = get_logger("bot_a")
        log2 = get_logger("bot_b")
        assert log1.name != log2.name


class TestTrackUserHelper:
    """اختبارات دالة track_user (helper)"""

    def test_track_user_does_not_raise_on_no_db(self):
        """track_user لا يرفع استثناء حتى بدون DB"""
        from bot_base import track_user
        with patch("bot_base.get_db", return_value=None):
            # لا يجب أن يرفع استثناء
            track_user("test_bot", 123456, "Test User")

    def test_record_error_does_not_raise_on_no_db(self):
        """record_error لا يرفع استثناء حتى بدون DB"""
        from bot_base import record_error
        with patch("bot_base.get_db", return_value=None):
            record_error("test_bot", Exception("Test error"), 123456)


class TestBotBase:
    """اختبارات start_polling"""

    def test_start_polling_exits_on_connection_failure(self):
        """يخرج بكود 1 عند فشل الاتصال"""
        from bot_base import start_polling
        mock_bot = MagicMock()
        mock_bot.get_me.side_effect = Exception("Connection failed")

        with pytest.raises(SystemExit) as exc_info:
            start_polling(mock_bot, "test_bot")
        assert exc_info.value.code == 1

    def test_start_polling_calls_delete_webhook(self):
        """يستدعي delete_webhook قبل البدء"""
        from bot_base import start_polling
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")
        mock_bot.infinity_polling.side_effect = KeyboardInterrupt()

        start_polling(mock_bot, "test_bot")
        mock_bot.delete_webhook.assert_called_once()

    def test_start_webhook_calls_set_webhook(self):
        """start_webhook يسجّل مسار البوت الصحيح (serve=False دون خادم)"""
        from bot_base import start_webhook
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")

        with patch.dict(os.environ, {"WEBHOOK_SECRET": ""}):
            start_webhook(mock_bot, "test_bot", "https://example.com/hook", serve=False)
        mock_bot.set_webhook.assert_called_once_with(
            url="https://example.com/hook/webhook/test_bot",
            drop_pending_updates=True)
        # serve=False: لا يُلغى الويب هوك — الإيقاف على عاتق المنادي
        mock_bot.remove_webhook.assert_not_called()

    def test_start_bot_defaults_to_polling(self):
        """start_bot يختار polling تلقائياً عندما لا يكون webhook مفعلاً"""
        from bot_base import start_bot
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")
        mock_bot.infinity_polling.side_effect = KeyboardInterrupt()

        with patch.dict(os.environ, {"USE_WEBHOOK": "false"}):
            start_bot(mock_bot, "test_bot")
            mock_bot.infinity_polling.assert_called_once()

    def test_start_bot_uses_webhook_when_enabled(self):
        """start_bot يختار webhook عند تفعيله في متغيرات البيئة"""
        from bot_base import start_bot
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")

        with patch.dict(os.environ, {"USE_WEBHOOK": "true",
                                     "WEBHOOK_URL": "https://boda.dev",
                                     "WEBHOOK_SECRET": ""}):
            start_bot(mock_bot, "test_bot", serve=False)
            mock_bot.set_webhook.assert_called_once_with(
                url="https://boda.dev/webhook/test_bot",
                drop_pending_updates=True)


class TestAllowedUpdates:
    """اختبارات دعم allowed_updates في دوال التشغيل"""

    UPDATES = ["message", "callback_query"]

    def test_start_bot_accepts_allowed_updates(self):
        """start_bot لا يرفع TypeError عند تمرير allowed_updates (polling)"""
        from bot_base import start_bot
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")
        mock_bot.infinity_polling.side_effect = KeyboardInterrupt()

        with patch.dict(os.environ, {"USE_WEBHOOK": "false"}):
            start_bot(mock_bot, "test_bot", allowed_updates=self.UPDATES)
            kwargs = mock_bot.infinity_polling.call_args.kwargs
            assert kwargs.get("allowed_updates") == self.UPDATES

    def test_start_polling_forwards_allowed_updates(self):
        """start_polling يمرر allowed_updates إلى infinity_polling"""
        from bot_base import start_polling
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")
        mock_bot.infinity_polling.side_effect = KeyboardInterrupt()

        start_polling(mock_bot, "test_bot", allowed_updates=self.UPDATES)
        kwargs = mock_bot.infinity_polling.call_args.kwargs
        assert kwargs["allowed_updates"] == self.UPDATES

    def test_start_polling_omits_allowed_updates_when_none(self):
        """start_polling لا يمرر allowed_updates إن لم تُحدد"""
        from bot_base import start_polling
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")
        mock_bot.infinity_polling.side_effect = KeyboardInterrupt()

        start_polling(mock_bot, "test_bot")
        assert "allowed_updates" not in mock_bot.infinity_polling.call_args.kwargs

    def test_start_webhook_forwards_allowed_updates(self):
        """start_webhook يمرر allowed_updates إلى set_webhook"""
        from bot_base import start_webhook
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")

        with patch.dict(os.environ, {"WEBHOOK_SECRET": ""}):
            start_webhook(mock_bot, "test_bot", "https://example.com/hook",
                          allowed_updates=self.UPDATES, serve=False)
        mock_bot.set_webhook.assert_called_once_with(
            url="https://example.com/hook/webhook/test_bot",
            allowed_updates=self.UPDATES,
            drop_pending_updates=True)

    def test_start_bot_forwards_allowed_updates_to_webhook(self):
        """start_bot يمرر allowed_updates للـ webhook عند تفعيله"""
        from bot_base import start_bot
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="TestBot")

        with patch.dict(os.environ, {"USE_WEBHOOK": "true",
                                     "WEBHOOK_URL": "https://boda.dev",
                                     "WEBHOOK_SECRET": ""}):
            start_bot(mock_bot, "test_bot", allowed_updates=["poll"], serve=False)
            mock_bot.set_webhook.assert_called_once_with(
                url="https://boda.dev/webhook/test_bot",
                allowed_updates=["poll"],
                drop_pending_updates=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
