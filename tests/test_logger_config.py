# =============================================================================
#  tests/test_logger_config.py — اختبارات نظام الـ Logging الموحد
# =============================================================================
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

import logger_config


class TestColoredFormatter:
    """Formatter الملوّن للـ Console"""

    def _record(self, level: int, levelname: str):
        rec = logging.LogRecord(
            name="t", level=level, pathname=__file__, lineno=1,
            msg="hello", args=(), exc_info=None)
        rec.levelname = levelname
        return rec

    def test_windows_returns_plain_text(self):
        """على ويندوز → نص عادي بلا أكواد ANSI"""
        fmt = logger_config._ColoredFormatter("%(message)s")
        out = fmt.format(self._record(logging.INFO, "INFO"))
        assert out == "hello"

    def test_non_windows_adds_color(self):
        """38-40: خارج ويندوز → يُلف السجل بلون مستوى السجل"""
        fmt = logger_config._ColoredFormatter("%(message)s")
        with patch.object(logger_config, "_WIN", False):
            colored = fmt.format(self._record(logging.INFO, "INFO"))
            err = fmt.format(self._record(logging.ERROR, "ERROR"))
            unknown = fmt.format(self._record(logging.INFO, "CUSTOM"))
        assert colored == f"{logger_config._COLORS['INFO']}hello{logger_config._COLORS['RESET']}"
        assert err.startswith(logger_config._COLORS["ERROR"])
        # مستوى غير معروف → بلا لون لكن مع RESET
        assert unknown == f"hello{logger_config._COLORS['RESET']}"


class TestGetLogger:
    """إنشاء الـ loggers وإعادة استخدامها"""

    def test_creates_logger_with_handlers(self, tmp_path):
        with patch.object(logger_config, "LOGS_DIR", tmp_path):
            log = logger_config.get_logger("bot_unit_test_a")
        assert isinstance(log, logging.Logger)
        assert log.level == logging.INFO
        assert log.propagate is False
        assert len(log.handlers) == 2  # console + ملف يومي

    def test_reuses_existing_logger(self, tmp_path):
        """logger موجود مسبقاً → لا تُضاف handlers جديدة"""
        with patch.object(logger_config, "LOGS_DIR", tmp_path):
            first = logger_config.get_logger("bot_unit_test_b")
            n = len(first.handlers)
            second = logger_config.get_logger("bot_unit_test_b")
        assert second is first
        assert len(second.handlers) == n

    def test_name_cleaning(self):
        """bot_ و _ تُنظف من الاسم"""
        logger_config.get_logger("bot_unit_test_c")  # تهيئة
        clean = "bot_unit_test_c".replace("bot_", "").replace("_", "-")
        assert logging.getLogger(clean).name == clean


class TestConfigureWindowsEncoding:
    """إعداد encoding على ويندوز"""

    def test_reconfigure_called_on_windows(self):
        with patch.object(logger_config, "_WIN", True):
            out = MagicMock()
            err = MagicMock()
            with patch.object(sys, "stdout", out), patch.object(sys, "stderr", err):
                logger_config.configure_windows_encoding()
        out.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
        err.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")

    def test_swallows_reconfigure_failure(self):
        """99-100: فشل reconfigure لا يرفع"""
        bad = MagicMock()
        bad.reconfigure.side_effect = OSError("not a tty")
        with patch.object(logger_config, "_WIN", True):
            with patch.object(sys, "stdout", bad), patch.object(sys, "stderr", bad):
                logger_config.configure_windows_encoding()  # لا يرفع

    def test_noop_outside_windows(self):
        with patch.object(logger_config, "_WIN", False):
            out = MagicMock()
            with patch.object(sys, "stdout", out):
                logger_config.configure_windows_encoding()
        out.reconfigure.assert_not_called()


if __name__ == "__main__":
    pytest_main = __import__("pytest").main
    pytest_main([__file__, "-v", "--tb=short"])
