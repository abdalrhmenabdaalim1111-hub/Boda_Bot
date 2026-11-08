"""
rate_limiter.py — نظام تحديد معدل الطلبات
يحمي البوتات من الإساءة والإرسال المتكرر
"""
import time
import threading
from collections import defaultdict, deque
from typing import Dict, Tuple


class RateLimiter:
    """
    تحديد معدل الطلبات لكل مستخدم.
    
    Example:
        limiter = RateLimiter(max_calls=5, period=60)
        
        @bot.message_handler(...)
        def handle(msg):
            allowed, wait_time = limiter.check(msg.from_user.id)
            if not allowed:
                bot.reply_to(msg, f"⏳ انتظر {wait_time:.0f} ثانية قبل الإرسال مجدداً.")
                return
            # ... باقي الكود
    """

    def __init__(self, max_calls: int = 5, period: float = 60.0):
        """
        Args:
            max_calls: عدد الطلبات المسموح بها
            period:    الفترة الزمنية بالثواني
        """
        self.max_calls = max_calls
        self.period    = period
        self._lock     = threading.Lock()
        # user_id → deque of timestamps
        self._calls: Dict[int, deque] = defaultdict(lambda: deque())

    def check(self, user_id: int) -> Tuple[bool, float]:
        """
        التحقق مما إذا كان الطلب مسموحاً.

        Returns:
            (allowed, wait_seconds)
            allowed=True  → الطلب مسموح
            allowed=False → يجب الانتظار wait_seconds ثانية
        """
        now = time.monotonic()
        with self._lock:
            q = self._calls[user_id]

            # إزالة الطلبات القديمة خارج النافذة
            while q and now - q[0] > self.period:
                q.popleft()

            if len(q) < self.max_calls:
                q.append(now)
                return True, 0.0
            else:
                # وقت الانتظار حتى يمكن إرسال طلب جديد
                wait = self.period - (now - q[0])
                return False, max(0.0, wait)

    def reset(self, user_id: int):
        """إعادة تعيين عداد المستخدم (للمسؤولين مثلاً)"""
        with self._lock:
            self._calls.pop(user_id, None)

    def get_remaining(self, user_id: int) -> int:
        """عدد الطلبات المتبقية للمستخدم"""
        now = time.monotonic()
        with self._lock:
            q = self._calls[user_id]
            while q and now - q[0] > self.period:
                q.popleft()
            return max(0, self.max_calls - len(q))


# ── Decorators جاهزة ──────────────────────────────────────────────────────────
_default_limiter = RateLimiter(max_calls=10, period=60)

def rate_limit(bot, limiter: RateLimiter = None):
    """
    Decorator لتطبيق Rate Limiting على handler.
    
    Example:
        @bot.message_handler(commands=['start'])
        @rate_limit(bot)
        def start(msg): ...
    """
    if limiter is None:
        limiter = _default_limiter

    def decorator(func):
        def wrapper(message):
            uid = message.from_user.id
            allowed, wait = limiter.check(uid)
            if not allowed:
                bot.reply_to(
                    message,
                    f"⏳ يرجى الانتظار <b>{wait:.0f}</b> ثانية قبل الإرسال مجدداً.",
                    parse_mode="HTML"
                )
                return
            return func(message)
        return wrapper
    return decorator


if __name__ == "__main__":
    # اختبار سريع
    limiter = RateLimiter(max_calls=3, period=10)
    uid = 12345
    for i in range(5):
        allowed, wait = limiter.check(uid)
        status = "✅ مسموح" if allowed else f"❌ انتظر {wait:.1f}s"
        print(f"طلب {i+1}: {status}")
