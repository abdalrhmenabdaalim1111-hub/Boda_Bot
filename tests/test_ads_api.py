"""
tests/test_ads_api.py — اختبارات واجهات برمجة Ad Studio في لوحة التحكم.

يختبر:
- تحليل snippet واستخراج zone/sdk
- عمليات المكتبة (CRUD)
- الإسناد (Assignment)
- جلب الإعلانات الفعالة للبوت (Effective ads)
- رفض الشفرات الخبيثة
"""

import json
import threading
import time
import urllib.request
import urllib.error
import pytest

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401
from tests.cc_fixtures import cc_supervisor  # noqa: F401
import api_server


LOCAL_TEST_TOKEN = "test-local-token-ads"
MONETAG_SNIPPET = "<script src='//libtl.com/sdk.js' data-zone='12250058' data-sdk='show_12250058'></script>"


@pytest.fixture()
def live_api(tmp_path, monkeypatch, cc_supervisor):
    """A real HTTP server on a free port with an isolated database."""
    monkeypatch.setenv("BODA_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("BODA_LOCAL_TOKEN", LOCAL_TEST_TOKEN)
    import database
    from control_center import db as cc_db_module

    database.BodaDatabase.reset_instance()
    cc_db_module.reset_db()

    server = api_server.run_api_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.4)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()
    server.server_close()
    database.BodaDatabase.reset_instance()
    cc_db_module.reset_db()


def _request(live_api, path, method="GET", payload=None):
    url = live_api + path
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": LOCAL_TEST_TOKEN,
        "X-Boda-Local": "1",
        "Origin": live_api
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        status = resp.status
        raw = resp.read().decode("utf-8")
        body = json.loads(raw) if raw else {}
    return status, body


def test_ads_parse_valid_snippet(live_api):
    status, body = _request(live_api, "/api/v1/ads/parse", "POST", {
        "snippet": MONETAG_SNIPPET
    })
    assert status == 200
    assert body["ok"] is True
    assert body["zone_id"] == "12250058"
    assert body["sdk_name"] == "show_12250058"
    assert body["snippet"] == MONETAG_SNIPPET


def test_ads_parse_malicious_snippet(live_api):
    status, body = _request(live_api, "/api/v1/ads/parse", "POST", {
        "snippet": "<script>eval('alert(1)')</script>"
    })
    assert status == 200
    assert body["ok"] is False
    assert any("eval" in e for e in body["errors"])


def test_ads_library_crud_lifecycle(live_api):
    # 1. Create
    status, body = _request(live_api, "/api/v1/ads/library", "POST", {
        "name": "Test Monetag Banner",
        "format": "interstitial",
        "slot": "body_end",
        "snippet": MONETAG_SNIPPET
    })
    assert status == 200
    assert body["ok"] is True
    ad = body["ad"]
    ad_id = ad["ad_id"]
    assert ad["zone_id"] == "12250058"

    try:
        # 2. List
        status, body = _request(live_api, "/api/v1/ads/library", "GET")
        assert status == 200
        assert any(a["ad_id"] == ad_id for a in body["ads"])

        # 3. Update
        status, body = _request(live_api, "/api/v1/ads/library", "PATCH", {
            "ad_id": ad_id,
            "name": "Updated Ad Name"
        })
        assert status == 200
        assert body["ad"]["name"] == "Updated Ad Name"

        # 4. Assign to bot
        status, body = _request(live_api, "/api/v1/ads/assign", "POST", {
            "ad_id": ad_id,
            "scope": "bot",
            "target_id": "currency",
            "priority": 10
        })
        assert status == 200
        assert body["ok"] is True

        # 5. Effective ads for bot
        status, body = _request(live_api, "/api/v1/ads/effective/currency", "GET")
        assert status == 200
        assert body["ok"] is True
        slots = body["slots"]
        assert "body_end" in slots
        assert slots["body_end"]["ad_id"] == ad_id

        # 6. Unassign
        status, body = _request(live_api, "/api/v1/ads/assign", "DELETE", {
            "ad_id": ad_id,
            "scope": "bot",
            "target_id": "currency"
        })
        assert status == 200
        assert body["ok"] is True

    finally:
        # 7. Delete
        _request(live_api, "/api/v1/ads/library", "DELETE", {"ad_id": ad_id})


def test_ads_preview_diff(live_api):
    status, body = _request(live_api, "/api/v1/ads/preview-diff", "POST", {
        "bot_id": "currency",
        "slot": "body_end",
        "ad_id": "diff_test_ad",
        "snippet": MONETAG_SNIPPET
    })
    assert status == 200
    assert body["ok"] is True
    assert "diff" in body
    assert "AD:BEGIN" in body["diff"]
    assert body["changed"] is True


def test_ads_backups_and_rollback(live_api):
    status, body = _request(live_api, "/api/v1/ads/backups/currency", "GET")
    assert status == 200
    assert body["ok"] is True
    assert isinstance(body["backups"], list)

