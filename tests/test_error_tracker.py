import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add Bots_Folder to path
bots_dir = Path(__file__).parent.parent / "Bots_Folder"
if str(bots_dir) not in sys.path:
    sys.path.insert(0, str(bots_dir))

import error_tracker


def test_classify_error_token():
    exc = Exception("Unauthorized: invalid token")
    cat, sev = error_tracker.classify_error(exc)
    assert cat == error_tracker.CATEGORY_TOKEN_INVALID
    assert sev == "CRITICAL"


def test_classify_error_rate_limit():
    exc = Exception("Too Many Requests: retry after 45 seconds")
    cat, sev = error_tracker.classify_error(exc)
    assert cat == error_tracker.CATEGORY_RATE_LIMIT
    assert sev == "WARNING"


def test_classify_error_user_blocked():
    exc = Exception("Forbidden: bot was blocked by the user")
    cat, sev = error_tracker.classify_error(exc)
    assert cat == error_tracker.CATEGORY_USER_BLOCKED
    assert sev == "INFO"


def test_classify_error_network():
    exc = Exception("Max retries exceeded with url /bot123/getMe (Caused by SSLError)")
    cat, sev = error_tracker.classify_error(exc)
    assert cat == error_tracker.CATEGORY_NETWORK
    assert sev == "WARNING"


def test_classify_error_external_api():
    exc = Exception("HTTP 500 from exchangerate API")
    cat, sev = error_tracker.classify_error(exc)
    assert cat == error_tracker.CATEGORY_EXTERNAL_API
    assert sev == "WARNING"


def test_classify_error_code():
    exc = KeyError("missing_key")
    cat, sev = error_tracker.classify_error(exc)
    assert cat == error_tracker.CATEGORY_CODE_ERROR
    assert sev == "ERROR"


def test_compute_fingerprint_deterministic():
    exc = ValueError("bad value")
    fp1 = error_tracker.compute_fingerprint("currency", "CODE_ERROR", exc)
    fp2 = error_tracker.compute_fingerprint("currency", "CODE_ERROR", exc)
    assert fp1 == fp2
    assert len(fp1) == 12


def test_compute_fingerprint_different_bots():
    """بوتات مختلفة → بصمات مختلفة"""
    exc = ValueError("same error")
    fp1 = error_tracker.compute_fingerprint("currency", "CODE_ERROR", exc)
    fp2 = error_tracker.compute_fingerprint("vidload", "CODE_ERROR", exc)
    assert fp1 != fp2


def test_compute_fingerprint_different_categories():
    """فئات مختلفة → بصمات مختلفة"""
    exc = ValueError("same error")
    fp1 = error_tracker.compute_fingerprint("currency", "CODE_ERROR", exc)
    fp2 = error_tracker.compute_fingerprint("currency", "NETWORK_TIMEOUT", exc)
    assert fp1 != fp2


def test_track_exception_critical(tmp_path):
    """CRITICAL → يرسل تنبيه crash"""
    from database import BodaDatabase
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    with patch("notification_system.get_notification_system") as mock_ns:
        mock_ns_instance = MagicMock()
        mock_ns.return_value = mock_ns_instance

        exc = Exception("Unauthorized: invalid token")
        res = error_tracker.track_exception("testbot", exc, user_id=99999, context="/start")
        assert res["category"] == error_tracker.CATEGORY_TOKEN_INVALID
        assert res["severity"] == "CRITICAL"
        mock_ns_instance.notify_crash.assert_called_once()


def test_track_exception_error(tmp_path):
    """ERROR → ينشئ notification"""
    from database import BodaDatabase
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    with patch("notification_system.get_notification_system") as mock_ns:
        mock_ns_instance = MagicMock()
        mock_ns.return_value = mock_ns_instance

        exc = KeyError("missing_key")
        res = error_tracker.track_exception("testbot", exc, user_id=99999, context="/test")
        assert res["category"] == error_tracker.CATEGORY_CODE_ERROR
        assert res["severity"] == "ERROR"
        mock_ns_instance.create_notification.assert_called_once()


def test_track_exception_warning_no_alert(tmp_path):
    """WARNING لا يرسل تنبيه (فقط يسجل في DB)"""
    from database import BodaDatabase
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    with patch("notification_system.get_notification_system") as mock_ns:
        mock_ns_instance = MagicMock()
        mock_ns.return_value = mock_ns_instance

        exc = Exception("Connection timeout")
        res = error_tracker.track_exception("testbot", exc, user_id=99999)
        assert res["category"] == error_tracker.CATEGORY_NETWORK
        assert res["severity"] == "WARNING"
        mock_ns_instance.notify_crash.assert_not_called()
        mock_ns_instance.create_notification.assert_not_called()


def test_track_exception_info_no_alert(tmp_path):
    """INFO لا يرسل تنبيه"""
    from database import BodaDatabase
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    with patch("notification_system.get_notification_system") as mock_ns:
        mock_ns_instance = MagicMock()
        mock_ns.return_value = mock_ns_instance

        exc = Exception("Forbidden: bot was blocked by the user")
        res = error_tracker.track_exception("testbot", exc, user_id=99999)
        assert res["category"] == error_tracker.CATEGORY_USER_BLOCKED
        assert res["severity"] == "INFO"
        mock_ns_instance.notify_crash.assert_not_called()
        mock_ns_instance.create_notification.assert_not_called()


def test_track_exception_user_blocked_marks_db(tmp_path):
    """USER_BLOCKED → يسجل الحظر في قاعدة البيانات"""
    from database import BodaDatabase
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    exc = Exception("Forbidden: bot was blocked by the user")
    error_tracker.track_exception("testbot", exc, user_id=77777)

    # التحقق من تسجيل الحظر
    assert db.get_blocked_bot_ids(77777) == ["testbot"]


def test_track_exception_throttle_alerts(tmp_path):
    """تنبيهات CRITICAL/ERROR تهدأ لمدة 5 دقائق"""
    from database import BodaDatabase
    import time
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    with patch("notification_system.get_notification_system") as mock_ns:
        mock_ns_instance = MagicMock()
        mock_ns.return_value = mock_ns_instance

        exc = KeyError("test")
        # أول استدعاء
        error_tracker.track_exception("testbot", exc)
        # ثاني استدعاء بنفس البصمة → لا تنبيه
        error_tracker.track_exception("testbot", exc)

        # يجب أن يُستدعى مرة واحدة فقط
        assert mock_ns_instance.create_notification.call_count == 1


def test_track_exception_records_in_db(tmp_path):
    """يسجل في error_events مع البصمة والتتبع"""
    from database import BodaDatabase
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    exc = ValueError("test error for tracking")
    res = error_tracker.track_exception("testbot", exc, user_id=99999, context="/test")
    assert res["bot_name"] == "testbot"
    assert res["category"] == error_tracker.CATEGORY_CODE_ERROR
    assert "fingerprint" in res

    recent = db.get_recent_errors(bot_name="testbot")
    assert len(recent) == 1
    assert recent[0]["bot_name"] == "testbot"
    assert "test error for tracking" in recent[0]["error_message"]
    assert recent[0]["fingerprint"] == res["fingerprint"]


def test_error_summary(tmp_path):
    """get_error_summary يعيد إحصائيات صحيحة"""
    from database import BodaDatabase
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    # إضافة أخطاء متنوعة
    error_tracker.track_exception("bot1", Exception("Unauthorized: bad token"))  # CRITICAL
    error_tracker.track_exception("bot1", Exception("Connection timeout"))  # WARNING
    error_tracker.track_exception("bot2", KeyError("missing"))  # ERROR

    summary = db.get_error_summary(days=7)
    assert summary["total_errors"] == 3
    assert error_tracker.CATEGORY_TOKEN_INVALID in summary["by_type"]
    assert error_tracker.CATEGORY_NETWORK in summary["by_type"]
    assert error_tracker.CATEGORY_CODE_ERROR in summary["by_type"]
    assert summary["by_bot"]["bot1"] == 2
    assert summary["by_bot"]["bot2"] == 1