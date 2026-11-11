# =============================================================================
#  tests/test_rate_limiter.py — اختبارات نظام تحديد معدل الطلبات
# =============================================================================
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

import rate_limiter
from rate_limiter import RateLimiter, rate_limit


class TestRateLimiter:
    def test_allows_within_limit(self):
        """الطلبات داخل الحد مسموحة"""
        limiter = RateLimiter(max_calls=3, period=60)
        for _ in range(3):
            allowed, wait = limiter.check(1)
            assert allowed is True
            assert wait == 0.0

    def test_blocks_after_limit(self):
        """تجاوز الحد → منع مع وقت انتظار"""
        limiter = RateLimiter(max_calls=2, period=10)
        limiter.check(1)
        limiter.check(1)
        allowed, wait = limiter.check(1)
        assert allowed is False
        assert 0 < wait <= 10

    def test_wait_counts_down(self):
        """وقت الانتظار يتناقص مع مرور الوقت"""
        limiter = RateLimiter(max_calls=1, period=1)
        limiter.check(1)
        _, wait1 = limiter.check(1)
        time.sleep(0.3)
        _, wait2 = limiter.check(1)
        assert wait2 < wait1

    def test_window_expiry_restores_access(self):
        """انتهاء النافذة → السماح يعود"""
        limiter = RateLimiter(max_calls=1, period=0.2)
        limiter.check(1)
        assert limiter.check(1)[0] is False
        time.sleep(0.3)
        assert limiter.check(1)[0] is True

    def test_users_are_independent(self):
        """حد المستخدم لا يؤثر على مستخدم آخر"""
        limiter = RateLimiter(max_calls=1, period=60)
        limiter.check(1)
        assert limiter.check(1)[0] is False
        assert limiter.check(2)[0] is True

    def test_reset_clears_counter(self):
        """reset يعيد السماح فوراً"""
        limiter = RateLimiter(max_calls=1, period=60)
        limiter.check(1)
        assert limiter.check(1)[0] is False
        limiter.reset(1)
        assert limiter.check(1)[0] is True

    def test_reset_unknown_user_is_safe(self):
        limiter = RateLimiter()
        limiter.reset(999)  # لا يرفع

    def test_get_remaining_counts_down_to_zero(self):
        limiter = RateLimiter(max_calls=3, period=60)
        assert limiter.get_remaining(5) == 3
        limiter.check(5)
        assert limiter.get_remaining(5) == 2

    def test_get_remaining_after_expiry(self):
        """الطلبات القديمة خارج النافذة لا تُحتسب"""
        limiter = RateLimiter(max_calls=2, period=0.2)
        limiter.check(5)
        limiter.check(5)
        assert limiter.get_remaining(5) == 0
        time.sleep(0.3)
        assert limiter.get_remaining(5) == 2

    def test_isolated_instances(self):
        """نسختان منفصلتان بعدادين مستقلين"""
        a = RateLimiter(max_calls=1, period=60)
        b = RateLimiter(max_calls=1, period=60)
        a.check(1)
        assert b.check(1)[0] is True

    def test_concurrent_access_thread_safe(self):
        """الوصول المتزامن من عدة خيوط لا يتجاوز الحد"""
        limiter = RateLimiter(max_calls=5, period=60)
        allowed_count = {"n": 0}

        import threading
        def worker():
            if limiter.check(1)[0]:
                allowed_count["n"] += 1

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert allowed_count["n"] == 5


class TestRateLimitDecorator:
    def test_allows_and_forwards(self):
        """الطلب المسموح يصل للدالة الأصلية ويعيد نتيجتها"""
        bot = MagicMock()
        limiter = RateLimiter(max_calls=5, period=60)

        @rate_limit(bot, limiter)
        def handler(msg):
            return "ok"

        msg = MagicMock()
        msg.from_user.id = 1
        assert handler(msg) == "ok"
        bot.reply_to.assert_not_called()

    def test_blocks_and_replies(self):
        """الطلب الزائد → رد انتظار دون استدعاء الدالة"""
        bot = MagicMock()
        limiter = RateLimiter(max_calls=1, period=60)

        @rate_limit(bot, limiter)
        def handler(msg):
            return "ok"

        msg = MagicMock()
        msg.from_user.id = 1
        assert handler(msg) == "ok"          # أول طلب يمر
        assert handler(msg) is None          # الثاني يُمنع
        bot.reply_to.assert_called_once()
        assert "انتظار" in bot.reply_to.call_args[0][1]

    def test_default_limiter_used_when_none(self):
        """بدون limiter → الافتراضي المشترك يُستخدم"""
        bot = MagicMock()

        @rate_limit(bot)
        def handler(msg):
            return "ok"

        msg = MagicMock()
        msg.from_user.id = 777_000  # معرّف غير مستخدم في اختبارات أخرى
        assert handler(msg) == "ok"
        assert rate_limiter._default_limiter.get_remaining(777_000) == 9


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
