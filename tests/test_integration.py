# tests/test_integration.py
"""
اختبارات التكامل: محاكاة تدفق تحديثات تيليجرام بالكامل
يغطي: /start → بوابة الاشتراك → تحقق → تفعيل الشبكة
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))


class TestIntegrationFlow:
    """اختبارات تدفق المستخدم الكامل: بدء → بوابة → تحقق → تفعيل"""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        """إعداد بيئة اختبار معزولة بقاعدة بيانات مؤقتة"""
        # إعداد متغيرات البيئة
        monkeypatch.setenv("USE_WEBHOOK", "false")
        monkeypatch.setenv("BOT_TEST_TOKEN", "1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")

        # قاعدة بيانات مؤقتة
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("BODA_DB_PATH", str(db_path))

        # إعادة تعيين singleton قاعدة البيانات لاستخدام المسار الجديد
        from database import BodaDatabase
        BodaDatabase.reset_instance()

        # إنشاء ملف network_config مؤقت
        import json
        net_cfg = tmp_path / "network_config.json"
        net_cfg.write_text(json.dumps({
            "enabled": True,
            "require_5_bots_activation": True,
            "assignment_size": 5,
            "activation_ttl_days": 7,
            "fixed_bot_ids": ["store"],
            "balance": True,
            "required_network_bots": [
                {"id": "store", "name": "متجر", "username": "@StoreBot", "url": "https://t.me/StoreBot"},
                {"id": "currency", "name": "عملات", "username": "@CurrencyBot", "url": "https://t.me/CurrencyBot"},
                {"id": "qrgen", "name": "QR", "username": "@QRBot", "url": "https://t.me/QRBot"},
                {"id": "fun_name", "name": "أسماء", "username": "@FunBot", "url": "https://t.me/FunBot"},
                {"id": "vidload", "name": "فيديو", "username": "@VidBot", "url": "https://t.me/VidBot"},
            ]
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr("growth_engine.NETWORK_CONFIG_FILE", net_cfg)

        # إعادة تعيين singleton محرك النمو لتنظيف الكاش
        import growth_engine
        growth_engine._growth_engine_instance = None

        yield

        # تنظيف بعد كل اختبار
        growth_engine._growth_engine_instance = None

    def _make_message(self, user_id=123456, text="/start", username="testuser", first_name="Test"):
        """إنشاء كائن رسالة تيليجرام وهمي"""
        msg = MagicMock()
        msg.message_id = 1
        msg.date = 1234567890
        msg.text = text
        msg.chat = MagicMock()
        msg.chat.id = user_id
        msg.chat.type = "private"
        msg.from_user = MagicMock()
        msg.from_user.id = user_id
        msg.from_user.username = username
        msg.from_user.first_name = first_name
        return msg

    def _make_callback_query(self, user_id=123456, data="verify_network_activation"):
        """إنشاء callback query وهمي"""
        call = MagicMock()
        call.id = "callback_123"
        call.from_user = MagicMock()
        call.from_user.id = user_id
        call.from_user.username = "testuser"
        call.data = data
        call.message = MagicMock()
        call.message.chat.id = user_id
        call.message.message_id = 1
        return call

    def test_new_user_gets_gate_on_start(self):
        """مستخدم جديد يتلقى بوابة التفعيل عند /start"""
        from growth_engine import get_growth_engine

        eng = get_growth_engine()
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")

        # مستخدم جديد - يجب أن تظهر البوابة
        allowed, gate_text, kb = eng.check_network_activation(mock_bot, user_id=99999, current_bot="currency")

        assert allowed is False
        assert gate_text is not None
        assert "تفعيل" in gate_text or "الشبكة" in gate_text
        assert kb is not None

    def test_user_assignment_created_on_first_gate_check(self):
        """عند أول فحص للبوابة، يتم إنشاء تعيين للمستخدم"""
        from growth_engine import get_growth_engine
        from database import get_db

        eng = get_growth_engine()
        db = get_db()
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")

        user_id = 111222

        # التأكد من نظافة الحالة
        db.clear_network_assignments(user_id)

        # قبل الفحص - لا يوجد تعيين
        assert db.get_network_assignments(user_id) == []

        # فحص البوابة
        eng.check_network_activation(mock_bot, user_id=user_id, current_bot="currency")

        # بعد الفحص - تم إنشاء تعيين
        assignment = db.get_network_assignments(user_id)
        assert len(assignment) == 5
        assert "store" in assignment  # المتجر ثابت

    def test_verify_activation_success_when_all_started(self):
        """التحقق ينجح عندما يكون المستخدم قد بدأ كل البوتات الخمسة"""
        from growth_engine import get_growth_engine
        from database import get_db

        eng = get_growth_engine()
        db = get_db()
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")

        user_id = 333444
        assignment = eng.get_or_create_assignment(user_id, current_bot="currency")

        # المستخدم بدأ كل البوتات
        for bid in assignment:
            db.track_user(bid, user_id, "Test User", "testuser")

        # التحقق يجب أن ينجح
        ok, missing = eng.verify_activation(user_id, current_bot="currency")
        assert ok is True
        assert missing == []

        # يجب أن يكون التفعيل مسجلاً
        assert db.is_network_activated(user_id)

    def test_verify_activation_fails_when_missing(self):
        """التحقق يفشل عندما يكون المستخدم لم يبدأ بعض البوتات"""
        from growth_engine import get_growth_engine
        from database import get_db

        eng = get_growth_engine()
        db = get_db()
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")

        user_id = 555666
        assignment = eng.get_or_create_assignment(user_id, current_bot="currency")

        # بدأ فقط 2 من 5
        db.track_user(assignment[0], user_id, "Test", "test")
        db.track_user(assignment[1], user_id, "Test", "test")

        ok, missing = eng.verify_activation(user_id, current_bot="currency")
        assert ok is False
        assert len(missing) == 3  # 3 ناقصة

    def test_unsubscribe_detected_and_replaced(self):
        """كشف إلغاء الاشتراك (حظر) واستبدال البوت تلقائياً"""
        from growth_engine import get_growth_engine
        from database import get_db
        from datetime import datetime, timedelta

        eng = get_growth_engine()
        db = get_db()
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")

        user_id = 777888
        assignment = eng.get_or_create_assignment(user_id, current_bot="currency")

        # بدأ الكل وتم التفعيل
        for bid in assignment:
            db.track_user(bid, user_id, "Test", "test")
        eng.verify_activation(user_id, current_bot="currency")
        assert db.is_network_activated(user_id)

        # محاكاة مرور 8 أيام: تحديث وقت التفعيل في قاعدة البيانات مباشرة
        old_time = (datetime.now() - timedelta(days=8)).isoformat()
        with db._conn_lock:
            with db._get_conn() as conn:
                conn.execute(
                    "UPDATE network_activations SET activated_at = ? WHERE user_id = ?",
                    (old_time, user_id)
                )

        # حظر بوت من الخمسة (غير المتجر وغير البوت الحالي)
        victim = [b for b in assignment if b not in ("store", "currency")][0]
        db.mark_user_blocked(victim, user_id)

        # فحص البوابة يجب أن يكشف الحظر ويعيد تعيين البوت
        eng._activation_cache.clear()
        allowed, gate_text, kb = eng.check_network_activation(mock_bot, user_id, current_bot="currency")

        assert allowed is False
        assert "لم تعد مشتركاً" in gate_text

        # البوت المحظور تم استبداله
        new_assignment = db.get_network_assignments(user_id)
        assert victim not in new_assignment
        assert len(new_assignment) == 5

    def test_current_bot_always_counted_as_started(self):
        """البوت الحالي يحسب كأن المستخدم بدأه تلقائياً"""
        from growth_engine import get_growth_engine
        from database import get_db

        eng = get_growth_engine()
        db = get_db()

        user_id = 999000
        assignment = eng.get_or_create_assignment(user_id, current_bot="currency")

        # لم يبدأ أي بوت بعد
        ok, missing = eng.verify_activation(user_id, current_bot="currency")

        # يجب أن يكون currency غير مطلوب (لأن المستخدم فيه الآن)
        missing_ids = [m['id'] for m in missing]
        assert "currency" not in missing_ids
        # يجب أن يطلب الـ 4 الآخرين
        assert len(missing) == 4


class TestMiddlewareIntegration:
    """اختبار middlewares: unified + error_tracker"""

    def test_unified_middleware_tracks_user_on_message(self):
        """الميدل وير الموحد يسجل المستخدم عند أي رسالة"""
        from unified_middleware import UnifiedBotMiddleware
        from database import get_db

        db = get_db()
        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")

        middleware = UnifiedBotMiddleware(mock_bot, "testbot")

        # محاكاة رسالة
        msg = MagicMock()
        msg.from_user.id = 111222
        msg.from_user.first_name = "Test"
        msg.from_user.last_name = ""
        msg.from_user.username = "testuser"
        msg.chat.type = "private"
        msg.text = "مرحبا"

        data = {}
        middleware.pre_process(msg, data)

        # يجب أن يكون المستخدم مسجلاً
        assert db.has_user_started("testbot", 111222)

    def test_middleware_catches_exception_in_post_process(self):
        """post_process يلتقط الاستثناءات ويرسلها لـ error_tracker"""
        from unified_middleware import UnifiedBotMiddleware

        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")

        middleware = UnifiedBotMiddleware(mock_bot, "testbot")

        # محاكاة رسالة مع استثناء
        msg = MagicMock()
        msg.from_user.id = 333444
        msg.chat.type = "private"
        msg.text = "/start"

        data = {"_t0": 0}

        # استخدام track_exception الحقيقي - يتم استيراده داخل الدالة
        with patch("error_tracker.track_exception") as mock_track:
            exc = ValueError("Test error")
            middleware.post_process(msg, data, exc)
            mock_track.assert_called_once()
            args = mock_track.call_args[0]
            assert args[0] == "testbot"
            assert isinstance(args[1], ValueError)

    def test_middleware_logs_slow_response(self):
        """post_process يسجل تحذيراً عند استجابة بطيئة"""
        from unified_middleware import UnifiedBotMiddleware

        mock_bot = MagicMock()
        mock_bot.get_me.return_value = MagicMock(username="testbot")

        middleware = UnifiedBotMiddleware(mock_bot, "testbot")

        msg = MagicMock()
        msg.from_user.id = 555666
        msg.chat.type = "private"
        msg.text = "test"

        # زمن بداية بعيد (محاكاة استجابة بطيئة)
        import time
        data = {"_t0": time.time() - 5}  # 5 ثوانٍ مضت

        with patch.object(middleware.log, "warning") as mock_warn:
            middleware.post_process(msg, data, None)
            mock_warn.assert_called_once()
            assert "بطيئة" in mock_warn.call_args[0][0]


class TestGrowthEngineUtilities:
    """اختبارات دوال مساعدة في GrowthEngine"""

    def test_balanced_pick_prefers_low_counts(self):
        """_balanced_pick يرتب المرشحين بالأقل استخداماً أولاً"""
        from growth_engine import GrowthEngine
        from database import get_db

        eng = GrowthEngine()
        db = get_db()

        # b1 لديه 100 مستخدم، b2 لديه 0
        db._fake_counts = {"b1": 100, "b2": 0, "b3": 0}

        with patch.object(db, "get_bot_user_counts", return_value={"b1": 100, "b2": 0, "b3": 0}):
            candidates = ["b1", "b2", "b3"]
            result = eng._balanced_pick(candidates)
            # b2 و b3 يجب أن يأتيا قبل b1
            assert result.index("b2") < result.index("b1")
            assert result.index("b3") < result.index("b1")

    def test_fingerprint_uniqueness(self):
        """البصمة فريدة للخطأ وتجمّع الأخطاء المتشابهة"""
        from error_tracker import compute_fingerprint, classify_error

        class DummyExc(Exception):
            pass

        exc1 = DummyExc("Connection timeout")
        exc2 = DummyExc("Connection timeout")
        exc3 = DummyExc("Different error")

        fp1 = compute_fingerprint("currency", classify_error(exc1)[0], exc1)
        fp2 = compute_fingerprint("currency", classify_error(exc2)[0], exc2)
        fp3 = compute_fingerprint("currency", classify_error(exc3)[0], exc3)

        assert fp1 == fp2  # نفس الخطأ → نفس البصمة
        assert fp1 != fp3  # خطأ مختلف → بصمة مختلفة

    def test_classify_error_all_categories(self):
        """تصنيف الأخطاء يغطي كل الفئات"""
        from error_tracker import classify_error

        test_cases = [
            ("Unauthorized: invalid token", ("AUTH_TOKEN_INVALID", "CRITICAL")),
            ("429 Too Many Requests", ("TELEGRAM_RATE_LIMIT", "WARNING")),
            ("403 Forbidden: user is deactivated", ("USER_BLOCKED_BOT", "INFO")),
            ("Connection timeout", ("NETWORK_TIMEOUT", "WARNING")),
            ("HTTP 500 from exchangerate API", ("EXTERNAL_API_ERROR", "WARNING")),
            ("Some random Python error", ("INTERNAL_CODE_ERROR", "ERROR")),
        ]

        for msg, expected in test_cases:
            exc = Exception(msg)
            cat, sev = classify_error(exc)
            assert (cat, sev) == expected, f"Failed for: {msg}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])