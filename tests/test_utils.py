# =============================================================================
#  tests/test_utils.py — اختبارات أدوات بوابة الاشتراك الموحدة (utils)
#  تغطي: التفويض لمحرك النمو، استنتاج معرّف البوت، الفشل المفتوح، إرسال البوابة
# =============================================================================
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

import utils


# ── app_kb ────────────────────────────────────────────────────────────────────

class TestAppKb:
    def test_contains_store_button(self):
        kb = utils.app_kb()
        btn = kb.keyboard[0][0]
        assert "متجر" in btn.text
        assert btn.url == utils.STORE_URL


# ── _engine ───────────────────────────────────────────────────────────────────

class TestEngineLoader:
    def test_returns_singleton(self):
        fake = object()
        with patch("growth_engine.get_growth_engine", return_value=fake):
            assert utils._engine() is fake

    def test_returns_none_on_import_failure(self):
        with patch.dict(sys.modules, {"growth_engine": None}):
            assert utils._engine() is None


# ── _current_bot_id ───────────────────────────────────────────────────────────

class TestCurrentBotId:
    def test_cached_value_short_circuits(self):
        """المعرّف المخزّن على كائن البوت يُعاد فوراً دون استدعاء API"""
        bot = MagicMock()
        bot._boda_bot_id = "currency"
        assert utils._current_bot_id(bot) == "currency"
        bot.get_me.assert_not_called()

    def test_resolved_from_registry_username(self):
        """مطابقة يوزر البوت في الريجستري → معرّف البوت"""
        bot = MagicMock()
        del bot._boda_bot_id  # إزالة الخاصية التلقائية — لا كاش
        bot.get_me.return_value = MagicMock(username="CurrencyBot")
        engine = MagicMock()
        engine._load_registry_pool.return_value = [
            {"id": "currency", "username": "@CurrencyBot"},
            {"id": "store", "username": "@BodaStoreeBot"},
        ]
        with patch("utils._engine", return_value=engine):
            assert utils._current_bot_id(bot) == "currency"
        assert bot._boda_bot_id == "currency"  # cache تأكيد

    def test_fallback_to_username_when_not_in_registry(self):
        """بوت غير موجود في الريجستري → اليوزر نفسه معرّفاً"""
        bot = MagicMock()
        del bot._boda_bot_id
        bot.get_me.return_value = MagicMock(username="UnknownBot")
        engine = MagicMock()
        engine._load_registry_pool.return_value = [{"id": "store", "username": "@BodaStoreeBot"}]
        with patch("utils._engine", return_value=engine):
            assert utils._current_bot_id(bot) == "unknownbot"

    def test_get_me_exception_returns_empty(self):
        bot = MagicMock()
        bot.get_me.side_effect = Exception("api down")
        del bot._boda_bot_id  # MagicMock لا يملكه فعلياً
        assert utils._current_bot_id(bot) == ""


# ── is_subscribed ─────────────────────────────────────────────────────────────

class TestIsSubscribed:
    def _bot_with_id(self):
        bot = MagicMock()
        bot._boda_bot_id = "testbot"
        return bot

    def test_engine_missing_fails_open(self):
        with patch("utils._engine", return_value=None):
            assert utils.is_subscribed(self._bot_with_id(), 1) is True

    def test_engine_disabled_fails_open(self):
        engine = MagicMock()
        engine.is_enabled.return_value = False
        with patch("utils._engine", return_value=engine):
            assert utils.is_subscribed(self._bot_with_id(), 1) is True
        engine.check_network_activation.assert_not_called()

    def test_delegates_to_growth_engine(self):
        """التفويض الصحيح: نفس البوت والمستخدم والمعرّف الحالي"""
        engine = MagicMock()
        engine.is_enabled.return_value = True
        engine.check_network_activation.return_value = (False, "GATE", None)
        with patch("utils._engine", return_value=engine):
            assert utils.is_subscribed(self._bot_with_id(), 42) is False
        engine.check_network_activation.assert_called_once()
        args = engine.check_network_activation.call_args
        assert args[0][1] == 42                 # user_id
        assert args[1]["current_bot"] == "testbot"

    def test_engine_exception_fails_open(self):
        """استثناء داخل المحرك → السماح (لا نعطل البوت)"""
        engine = MagicMock()
        engine.is_enabled.return_value = True
        engine.check_network_activation.side_effect = RuntimeError("boom")
        with patch("utils._engine", return_value=engine):
            assert utils.is_subscribed(self._bot_with_id(), 7) is True


# ── send_subscription_prompt ──────────────────────────────────────────────────

class TestSendSubscriptionPrompt:
    def _bot_with_id(self):
        bot = MagicMock()
        bot._boda_bot_id = "testbot"
        return bot

    def test_engine_missing_sends_temp_error(self):
        bot = self._bot_with_id()
        with patch("utils._engine", return_value=None):
            utils.send_subscription_prompt(bot, 100)
        bot.send_message.assert_called_once()
        assert "خطأ تقني مؤقت" in bot.send_message.call_args[0][1]

    def test_allowed_user_gets_nothing(self):
        """مفعّل بالفعل → لا رسالة"""
        engine = MagicMock()
        engine.check_network_activation.return_value = (True, None, None)
        bot = self._bot_with_id()
        with patch("utils._engine", return_value=engine):
            utils.send_subscription_prompt(bot, 200)
        bot.send_message.assert_not_called()

    def test_gate_sent_with_keyboard(self):
        """غير مفعّل → بوابة بلوحة المفاتيح وصيغة HTML"""
        engine = MagicMock()
        engine.check_network_activation.return_value = (False, "بوابة", "KB")
        bot = self._bot_with_id()
        with patch("utils._engine", return_value=engine):
            utils.send_subscription_prompt(bot, 300)
        bot.send_message.assert_called_once_with(300, "بوابة",
                                                 reply_markup="KB", parse_mode="HTML")

    def test_send_exception_swallowed(self):
        """فشل الإرسال (مستخدم محظور) لا يرفع استثناء"""
        engine = MagicMock()
        engine.check_network_activation.return_value = (False, "بوابة", None)
        bot = self._bot_with_id()
        bot.send_message.side_effect = Exception("blocked")
        with patch("utils._engine", return_value=engine):
            utils.send_subscription_prompt(bot, 400)  # لا يرفع


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
