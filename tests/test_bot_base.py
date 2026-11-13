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


class TestBotBaseRemainingBranches:
    """تغطية الفروع المتبقية: fallbacks ومعالجات الأعطال"""

    def test_get_logger_import_error_fallback(self):
        """49-60: غياب logger_config → logger محلي بسيط بنفس الواجهة"""
        import logging
        import bot_base
        with patch.dict(sys.modules, {"logger_config": None}):
            log = bot_base.get_logger("fallback_bot")
        assert isinstance(log, logging.Logger)
        assert len(log.handlers) > 0

    def test_get_db_import_error_returns_none(self):
        """71-72: فشل استيراد database → None (لا يرفع)"""
        import bot_base
        with patch.dict(sys.modules, {"database": None}):
            assert bot_base.get_db() is None

    def test_record_error_calls_db(self):
        """110: record_error يسجل الخطأ في DB عند توفرها"""
        import bot_base
        mock_db = MagicMock()
        with patch("bot_base.get_db", return_value=mock_db):
            bot_base.record_error("b", ValueError("boom"), user_id=5)
        mock_db.record_error.assert_called_once_with("b", "boom", 5)

    def test_record_error_swallows_db_exception(self):
        """111-112: استثناء داخل record_error يُبتلع"""
        import bot_base
        with patch("bot_base.get_db", side_effect=RuntimeError("db down")):
            bot_base.record_error("b", ValueError("boom"))  # لا يرفع

    def test_prepare_bot_import_errors_isolated(self):
        """126-141: فشل استيراد أي نظام موحد لا يوقف الباقي"""
        import bot_base

        # ad_manager مفقود → الباقي يعمل
        bot1 = MagicMock()
        with patch.dict(sys.modules, {"ad_manager": None}), \
                patch("growth_engine.attach_growth_engine") as ge, \
                patch("unified_middleware.install_unified_layer") as ul:
            bot_base.prepare_bot(bot1, "b")
            ge.assert_called_once_with(bot1, "b")
            ul.assert_called_once_with(bot1, "b")

        # growth_engine مفقود → الباقي يعمل
        bot2 = MagicMock()
        with patch.dict(sys.modules, {"growth_engine": None}), \
                patch("ad_manager.attach_unified_ads") as ads, \
                patch("unified_middleware.install_unified_layer") as ul2:
            bot_base.prepare_bot(bot2, "b")
            ads.assert_called_once_with(bot2, "b")
            ul2.assert_called_once_with(bot2, "b")

        # unified_middleware مفقود → الباقي يعمل
        bot3 = MagicMock()
        with patch.dict(sys.modules, {"unified_middleware": None}), \
                patch("ad_manager.attach_unified_ads") as ads3, \
                patch("growth_engine.attach_growth_engine") as ge3:
            bot_base.prepare_bot(bot3, "b")
            ads3.assert_called_once_with(bot3, "b")
            ge3.assert_called_once_with(bot3, "b")

    def test_start_polling_crash_tracks_and_reraises(self):
        """195-202: خطأ فادح في polling → track_exception ثم إعادة الرفع"""
        import bot_base
        bot = MagicMock()
        bot.get_me.return_value = MagicMock(username="T")
        bot.infinity_polling.side_effect = RuntimeError("crash")
        with patch("bot_base.get_db", return_value=None), \
                patch("error_tracker.track_exception") as tr:
            with pytest.raises(RuntimeError):
                bot_base.start_polling(bot, "b")
            tr.assert_called_once()
            assert tr.call_args.kwargs.get("context") == "polling_crash"

    def test_start_polling_session_lifecycle(self):
        """175-176 + 204-208: تسجيل الجلسة/إيقافها، وفشل record_bot_start لا يوقف"""
        import bot_base
        bot = MagicMock()
        bot.get_me.return_value = MagicMock(username="T")
        bot.infinity_polling.side_effect = KeyboardInterrupt

        db = MagicMock()
        db.record_bot_start.return_value = 42
        with patch("bot_base.get_db", return_value=db):
            bot_base.start_polling(bot, "b")
        db.record_bot_stop.assert_called_once_with(42)

        # فشل record_bot_start → الجلسة None ولا يُسجل إيقاف، لكن البوت يعمل
        db2 = MagicMock()
        db2.record_bot_start.side_effect = RuntimeError("db")
        with patch("bot_base.get_db", return_value=db2):
            bot_base.start_polling(bot, "b")  # KeyboardInterrupt داخلياً
        db2.record_bot_stop.assert_not_called()

    def test_start_webhook_exits_on_connection_failure(self):
        """240-247: فشل الاتصال في webhook → SystemExit(1)"""
        import bot_base
        bot = MagicMock()
        bot.get_me.side_effect = Exception("no net")
        with patch("bot_base.get_db", return_value=None):
            with pytest.raises(SystemExit) as ei:
                bot_base.start_webhook(bot, "b", "https://x.example", serve=False)
        assert ei.value.code == 1

    def test_start_webhook_record_start_failure(self):
        """254-255: فشل record_bot_start لا يوقف الويب هوك"""
        import bot_base
        bot = MagicMock()
        bot.get_me.return_value = MagicMock(username="T")
        db = MagicMock()
        db.record_bot_start.side_effect = RuntimeError("db")
        with patch("bot_base.get_db", return_value=db), \
                patch.dict(os.environ, {"WEBHOOK_SECRET": ""}):
            bot_base.start_webhook(bot, "b", "https://x.example", serve=False)
        bot.set_webhook.assert_called_once()

    def test_start_webhook_serve_true_lifecycle(self):
        """263-265 + 274 + 279-285 + 296-301: دورة خادم webhook كاملة مع سر"""
        import bot_base
        bot = MagicMock()
        bot.get_me.return_value = MagicMock(username="T")
        db = MagicMock()
        db.record_bot_start.return_value = 7
        server = MagicMock()
        server.webhook_path.return_value = "/webhook/b"
        server.actual_port = 8443

        with patch("webhook_server.WebhookServer", return_value=server), \
                patch("bot_base.get_db", return_value=db), \
                patch.dict(os.environ, {"WEBHOOK_SECRET": "s3cret"}), \
                patch("bot_base.time.sleep", side_effect=KeyboardInterrupt):
            bot_base.start_webhook(bot, "b", "https://x.example", serve=True)

        server.register.assert_called_once_with("b", bot)
        server.start.assert_called_once()
        bot.set_webhook.assert_called_once_with(
            url="https://x.example/webhook/b",
            drop_pending_updates=True, secret_token="s3cret")
        bot.remove_webhook.assert_called_once()
        server.stop.assert_called_once()
        db.record_bot_stop.assert_called_once_with(7)

    def test_start_webhook_crash_tracks_and_reraises(self):
        """286-293: خطأ في webhook → track_exception ثم إعادة الرفع"""
        import bot_base
        bot = MagicMock()
        bot.get_me.return_value = MagicMock(username="T")
        bot.set_webhook.side_effect = RuntimeError("hook fail")
        with patch("bot_base.get_db", return_value=None), \
                patch.dict(os.environ, {"WEBHOOK_SECRET": ""}), \
                patch("error_tracker.track_exception") as tr:
            with pytest.raises(RuntimeError):
                bot_base.start_webhook(bot, "b", "https://x.example", serve=False)
            tr.assert_called_once()
            assert tr.call_args.kwargs.get("context") == "webhook_crash"

    def test_miniapps_helpers_import_error(self):
        """336-340 + 345-349: غياب unified_middleware → قيم احتياطية آمنة"""
        import bot_base
        with patch.dict(sys.modules, {"unified_middleware": None}):
            assert bot_base.get_miniapps_url("x") == ""
            assert bot_base.webapp_keyboard("x") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
