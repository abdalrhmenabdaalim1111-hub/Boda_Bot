"""
tests/test_control_center_api.py — اختبارات تكامل واجهة Control Center

تغطي:
• نقاط النظام (health / migrations / config)
• قائمة البوتات وتفاصيلها
• دورة حياة البوت (تشغيل/إيقاف/إعادة تشغيل/تفعيل) عبر HTTP
• بثّ السجلات (SSE)
• سجل التدقيق عبر HTTP
• توثيق OpenAPI
• بقاء المسارات القديمة تعمل كما هي
"""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401  (path bootstrap)
from tests.cc_fixtures import cc_supervisor  # noqa: F401  (fixture)

import api_server


# Shared with the _post helper below — matches BODA_LOCAL_TOKEN in the fixture.
LOCAL_TEST_TOKEN = "test-local-token"


@pytest.fixture()
def live_api(tmp_path, monkeypatch, cc_supervisor):
    """A real HTTP server on a free port with an isolated database."""
    monkeypatch.setenv("BODA_DB_PATH", str(tmp_path / "api.db"))
    # Phase 1: state-changing requests require the local admin token.
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


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _post(base, path, payload=None):
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json",
                                          "X-API-Key": LOCAL_TEST_TOKEN},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


# ── System ──────────────────────────────────────────────────────────────────
def test_health_endpoint(live_api):
    """نقطة فحص صحة Control Center"""
    status, payload = _get(live_api, "/api/v1/system/health")
    assert status == 200
    assert payload["ok"] is True
    assert payload["service"] == "boda-control-center"


def test_migrations_status_endpoint(live_api):
    """حالة الترحيلات عبر HTTP"""
    status, payload = _get(live_api, "/api/v1/system/migrations")
    assert status == 200
    assert payload["applied_count"] >= 1
    assert payload["pending"] == []


def test_config_endpoint_hides_secrets(live_api):
    """إعدادات Control Center لا تكشف أي سر"""
    status, payload = _get(live_api, "/api/v1/system/config")
    assert status == 200
    blob = json.dumps(payload)
    assert "BOT_STORE_TOKEN" not in blob
    assert "encryption_available" in payload


# ── Bots ────────────────────────────────────────────────────────────────────
def test_list_bots(live_api):
    """قائمة البوتات مع الحالة"""
    status, payload = _get(live_api, "/api/v1/bots")
    assert status == 200
    assert payload["count"] >= 30
    assert all("bot_id" in bot for bot in payload["bots"])


def test_bot_detail(live_api):
    """تفاصيل بوت واحد"""
    status, payload = _get(live_api, "/api/v1/bots/currency")
    assert status == 200
    assert payload["bot"]["bot_id"] == "currency"
    assert "state" in payload["bot"]


def test_enable_bot(live_api):
    """تفعيل/تعطيل بوت عبر HTTP"""
    status, payload = _post(live_api, "/api/v1/bots/currency/enable",
                             {"enabled": False})
    assert status == 200
    assert payload["enabled"] is False

    _post(live_api, "/api/v1/bots/currency/enable", {"enabled": True})


def test_bot_lifecycle_endpoints_exist(live_api):
    """نقاط التشغيل/الإيقاف/إعادة التشغيل موجودة وتستجيب"""
    for path in ("/api/v1/bots/currency/start",
                 "/api/v1/bots/currency/stop",
                 "/api/v1/bots/currency/restart"):
        status, payload = _post(live_api, path)
        assert status in (200, 409)
        assert "ok" in payload


def test_start_all_and_stop_all(live_api):
    """تشغيل/إيقاف كل البوتات"""
    status, payload = _post(live_api, "/api/v1/bots/actions/start-all")
    assert status == 200
    assert "results" in payload

    status, payload = _post(live_api, "/api/v1/bots/actions/stop-all")
    assert status == 200
    assert "results" in payload


def test_bot_logs_endpoint(live_api):
    """قراءة آخر أسطر السجلات"""
    status, payload = _get(live_api, "/api/v1/bots/currency/logs?limit=10")
    assert status == 200
    assert isinstance(payload["lines"], list)


def test_bot_logs_sse_stream(live_api):
    """بثّ السجلات عبر SSE"""
    req = urllib.request.Request(live_api + "/api/v1/bots/currency/logs/stream")
    resp = urllib.request.urlopen(req, timeout=15)
    try:
        assert resp.headers.get("Content-Type", "").startswith("text/event-stream")
        # SSE frames are "event: <name>" followed by "data: <payload>".
        chunk = ""
        for _ in range(6):
            line = resp.readline().decode("utf-8")
            if not line:
                break
            chunk += line
            if line.startswith("data:"):
                break
        assert "event:" in chunk
        assert "data:" in chunk
    finally:
        resp.close()


# ── Audit ───────────────────────────────────────────────────────────────────
def test_audit_endpoint(live_api):
    """سجل التدقيق عبر HTTP"""
    _post(live_api, "/api/v1/bots/currency/enable", {"enabled": True})
    status, payload = _get(live_api, "/api/v1/audit?limit=20")
    assert status == 200
    assert payload["total"] >= 1
    assert any(entry["action"] == "bot.enable" for entry in payload["entries"])


# ── Overview ────────────────────────────────────────────────────────────────
def test_overview_endpoint(live_api):
    """ملخص المؤشرات"""
    status, payload = _get(live_api, "/api/v1/overview")
    assert status == 200
    assert "bots" in payload
    assert payload["bots"]["total"] >= 30


# ── OpenAPI ─────────────────────────────────────────────────────────────────
def test_openapi_document(live_api):
    """وثيقة OpenAPI تحتوي كل المسارات"""
    status, payload = _get(live_api, "/openapi.json")
    assert status == 200
    assert payload["openapi"].startswith("3.1")
    assert "/api/v1/bots" in payload["paths"]
    assert "/api/v1/bots/{bot_id}/start" in payload["paths"]


def test_swagger_ui(live_api):
    """صفحة Swagger UI متاحة"""
    with urllib.request.urlopen(live_api + "/docs", timeout=15) as resp:
        html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "swagger" in html.lower()


def test_unknown_v1_route_returns_404(live_api):
    """مسار غير معروف داخل /api/v1 يعيد 404"""
    try:
        urllib.request.urlopen(live_api + "/api/v1/nope", timeout=10)
        raised = False
    except urllib.error.HTTPError as exc:
        raised = True
        assert exc.code == 404
    assert raised


# ── Backward compatibility ──────────────────────────────────────────────────
def test_legacy_routes_still_work(live_api):
    """المسارات القديمة تعمل كما كانت"""
    status, payload = _get(live_api, "/health")
    assert status == 200
    assert payload["status"] == "healthy"

    status, payload = _get(live_api, "/api/bots")
    assert status == 200
    assert isinstance(payload, list)

    status, payload = _get(live_api, "/api/stats")
    assert status == 200
    assert isinstance(payload, dict)


def test_legacy_track_endpoint_still_accepts_events(live_api):
    """نقطة التتبع القديمة ما زالت تستقبل الأحداث"""
    body = json.dumps({"bot": "currency", "event": "ad_view"}).encode("utf-8")
    req = urllib.request.Request(live_api + "/api/track", data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    assert payload["ok"] is True
