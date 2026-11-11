# =============================================================================
#  tests/test_error_handler.py — اختبارات نظام معالجة الأخطاء الموحد
# =============================================================================
import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

from error_handler import ErrorHandler, handle_errors, log_error


class TestErrorHandler:
    def test_initial_state(self):
        h = ErrorHandler("store")
        assert h.bot_name == "store"
        assert h.error_count == 0
        assert h.last_error is None
        assert h.error_log == []

    def test_handle_error_counts_and_records(self):
        """معالجة خطأ تُحتسب وتُسجّل مع السياق"""
        h = ErrorHandler("currency")
        msg = h.handle_error(ValueError("boom"), context="payment")
        assert h.error_count == 1
        assert h.last_error is not None
        assert "خطأ في currency" in msg
        assert "payment" in msg
        assert "boom" in msg
        entry = h.error_log[0]
        assert entry["error"] == "boom"
        assert entry["context"] == "payment"
        assert entry["traceback"]            # مسار التتبع موجود
        assert entry["timestamp"]            # طابع زمني موجود

    def test_handle_error_without_context(self):
        """بدون سياق → الرسالة بلا شرطة سياق"""
        h = ErrorHandler("b")
        msg = h.handle_error(RuntimeError("x"))
        assert "خطأ في b" in msg
        assert h.error_log[0]["context"] == ""

    def test_multiple_errors_accumulate(self):
        h = ErrorHandler("b")
        h.handle_error(ValueError("1"))
        h.handle_error(KeyError("2"))
        h.handle_error(IndexError("3"))
        assert h.error_count == 3
        assert len(h.error_log) == 3

    def test_get_error_stats(self):
        """الإحصائيات: العدد وآخر خطأ وآخر 10 فقط"""
        h = ErrorHandler("b")
        for i in range(15):
            h.handle_error(ValueError(f"e{i}"))
        stats = h.get_error_stats()
        assert stats["total_errors"] == 15
        assert stats["last_error"] == "e14"
        assert len(stats["recent_errors"]) == 10  # قص الفهرس لآخر 10
        assert stats["recent_errors"][0]["error"] == "e5"

    def test_get_error_stats_empty(self):
        h = ErrorHandler("b")
        stats = h.get_error_stats()
        assert stats["total_errors"] == 0
        assert stats["last_error"] is None
        assert stats["recent_errors"] == []

    def test_clear_errors(self):
        """المسح يعيد الحالة الابتدائية"""
        h = ErrorHandler("b")
        h.handle_error(ValueError("x"))
        h.clear_errors()
        assert h.error_count == 0
        assert h.last_error is None
        assert h.error_log == []


class TestHandleErrorsDecorator:
    def test_success_passes_through(self):
        """دالة سليمة → نتيجتها تعود كما هي دون تسجيل"""
        h = ErrorHandler("b")

        @handle_errors(h)
        def add(a, b):
            return a + b

        assert add(2, 3) == 5
        assert h.error_count == 0

    def test_exception_caught_returns_none(self):
        """الاستثناء يُلتقط → None وتسجيل باسم الدالة كسياق"""
        h = ErrorHandler("b")

        @handle_errors(h)
        def fail():
            raise ValueError("bad")

        assert fail() is None
        assert h.error_count == 1
        assert h.error_log[0]["context"] == "fail"  # اسم الدالة افتراضياً

    def test_explicit_context_overrides_function_name(self):
        """سياق صريح يُستخدم بدل اسم الدالة"""
        h = ErrorHandler("b")

        @handle_errors(h, context="startup")
        def fail():
            raise ValueError("x")

        fail()
        assert h.error_log[0]["context"] == "startup"

    def test_wraps_preserves_metadata(self):
        h = ErrorHandler("b")

        @handle_errors(h)
        def documented():
            """docstring"""

        assert documented.__name__ == "documented"
        assert documented.__doc__ == "docstring"

    def test_kwargs_forwarded(self):
        h = ErrorHandler("b")

        @handle_errors(h)
        def greet(name, greeting="مرحبا"):
            return f"{greeting} {name}"

        assert greet("أحمد", greeting="أهلاً") == "أهلاً أحمد"


class TestLogError:
    def test_creates_handler_and_records(self):
        """log_error ينشئ معالجاً مؤقتاً ويسجل الخطأ"""
        with patch("error_handler.ErrorHandler.handle_error", return_value="m") as m:
            log_error("qrgen", ValueError("e"), context="gen")
        m.assert_called_once()
        assert m.call_args[0][0].args[0] == "e"
        assert m.call_args[0][1] == "gen"

    def test_log_error_without_context(self):
        with patch("error_handler.ErrorHandler.handle_error", return_value="m") as m:
            log_error("b", ValueError("e"))
        assert m.call_args[0][1] == ""


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
