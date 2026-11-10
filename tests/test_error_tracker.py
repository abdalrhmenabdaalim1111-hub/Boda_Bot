import os
import sys
import pytest
from pathlib import Path

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


def test_track_exception(tmp_path):
    from database import BodaDatabase
    db_file = str(tmp_path / "test_err.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    exc = TypeError("test error for tracking")
    res = error_tracker.track_exception("testbot", exc, user_id=99999, context="/test")
    assert res["bot_name"] == "testbot"
    assert res["category"] == error_tracker.CATEGORY_CODE_ERROR

    recent = db.get_recent_errors(bot_name="testbot")
    assert len(recent) == 1
    assert recent[0]["bot_name"] == "testbot"
    assert "test error for tracking" in recent[0]["error_message"]
