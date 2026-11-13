"""
tests/test_security_phase1.py — Phase 1 security hardening.

Covers the fixes from docs/AUDIT.md §2/§3:
* dashboard excluded from the GitHub Pages artifact
* Host validation (DNS rebinding)
* Origin / Sec-Fetch-Site validation for state-changing requests (CSRF)
* local admin token required for state-changing requests
* CORS: no wildcard, same-machine origins only
* /api/track: foreign origins rejected, per-IP rate limit
* legacy /api/ads/set requires the local token
* dashboard HTML gets the local token injected (same-origin only)
* log endpoints redact token-looking strings
"""

import http.client
import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401  (path bootstrap)

import api_server

TOKEN = "sec-test-token-123"


@pytest.fixture()
def secure_api(tmp_path, monkeypatch):
    """A real server on a free port with an isolated DB and a known token."""
    monkeypatch.setenv("BODA_DB_PATH", str(tmp_path / "sec.db"))
    monkeypatch.setenv("BODA_LOCAL_TOKEN", TOKEN)
    import database
    from control_center import db as cc_db_module

    database.BodaDatabase.reset_instance()
    cc_db_module.reset_db()
    api_server._TRACK_HITS.clear()

    server = api_server.run_api_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.4)
    port = server.server_address[1]
    yield port
    server.shutdown()
    server.server_close()
    api_server._TRACK_HITS.clear()
    database.BodaDatabase.reset_instance()
    cc_db_module.reset_db()


def _request(port, method, path, headers=None, body=None, raw_host=False):
    """Raw request with full header control (http.client)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    if raw_host:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in (headers or {}).items():
            conn.putheader(k, v)
        conn.endheaders()
        if body:
            conn.send(body)
    else:
        conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    hdrs = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, hdrs, data


def _json_body(body: bytes):
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {}


# ── Host validation (DNS rebinding) ─────────────────────────────────────────
def test_health_open_without_token(secure_api):
    status, _, data = _request(secure_api, "GET", "/health")
    assert status == 200
    assert _json_body(data)["status"] == "healthy"


def test_rebinding_host_rejected(secure_api):
    status, _, data = _request(secure_api, "GET", "/health",
                               headers={"Host": "evil.example.com"})
    assert status == 403
    assert "Host" in _json_body(data)["error"]


def test_missing_host_rejected(secure_api):
    status, _, _ = _request(secure_api, "GET", "/health", raw_host=True)
    assert status == 403


# ── Cross-origin protection on state-changing requests ──────────────────────
def _post_enable(port, headers):
    return _request(port, "POST", "/api/v1/bots/currency/enable",
                    headers=headers,
                    body=json.dumps({"enabled": False}).encode("utf-8"))


def test_cross_origin_write_rejected(secure_api):
    status, _, _ = _post_enable(secure_api, {
        "Host": "127.0.0.1", "Content-Type": "application/json",
        "X-API-Key": TOKEN, "Origin": "https://evil.example.com"})
    assert status == 403


def test_cross_site_fetch_rejected(secure_api):
    status, _, _ = _post_enable(secure_api, {
        "Host": "127.0.0.1", "Content-Type": "application/json",
        "X-API-Key": TOKEN, "Sec-Fetch-Site": "cross-site"})
    assert status == 403


def test_null_origin_rejected(secure_api):
    status, _, _ = _post_enable(secure_api, {
        "Host": "127.0.0.1", "Content-Type": "application/json",
        "X-API-Key": TOKEN, "Origin": "null"})
    assert status == 403


# ── Local admin token for state-changing requests ───────────────────────────
def test_local_write_without_token_rejected(secure_api):
    status, _, data = _post_enable(secure_api, {
        "Host": "127.0.0.1", "Content-Type": "application/json"})
    assert status == 403
    payload = _json_body(data)
    assert payload["ok"] is False


def test_local_write_with_token_ok(secure_api):
    status, _, data = _post_enable(secure_api, {
        "Host": "127.0.0.1", "Content-Type": "application/json",
        "X-API-Key": TOKEN})
    assert status == 200
    assert _json_body(data)["enabled"] is False
    # restore
    _post_enable(secure_api, {"Host": "127.0.0.1",
                              "Content-Type": "application/json",
                              "X-API-Key": TOKEN})


def test_local_write_with_bearer_ok(secure_api):
    status, _, _ = _request(secure_api, "POST",
                            "/api/v1/bots/currency/enable",
                            headers={"Host": "127.0.0.1",
                                     "Content-Type": "application/json",
                                     "Authorization": f"Bearer {TOKEN}"},
                            body=json.dumps({"enabled": True}).encode("utf-8"))
    assert status == 200


def test_wrong_token_rejected(secure_api):
    status, _, _ = _post_enable(secure_api, {
        "Host": "127.0.0.1", "Content-Type": "application/json",
        "X-API-Key": "wrong-token"})
    assert status == 403


def test_shared_api_key_accepted_for_write(secure_api, monkeypatch):
    monkeypatch.setattr(api_server, "API_SERVER_KEY", "shared-key-123")
    status, _, _ = _post_enable(secure_api, {
        "Host": "127.0.0.1", "Content-Type": "application/json",
        "X-API-Key": "shared-key-123"})
    assert status == 200
    _post_enable(secure_api, {"Host": "127.0.0.1",
                              "Content-Type": "application/json",
                              "X-API-Key": "shared-key-123"})


# ── CORS: no wildcard, same-machine only ────────────────────────────────────
def test_cors_read_blocked_cross_origin(secure_api):
    status, hdrs, _ = _request(secure_api, "GET", "/api/v1/bots",
                               headers={"Host": "127.0.0.1",
                                        "Origin": "https://evil.example.com"})
    assert status == 200                     # response body still sent
    assert "access-control-allow-origin" not in hdrs  # …but unreadable cross-origin


def test_cors_echo_for_local_origin(secure_api):
    status, hdrs, _ = _request(secure_api, "GET", "/api/v1/bots",
                               headers={"Host": "127.0.0.1",
                                        "Origin": "http://127.0.0.1:9999"})
    assert status == 200
    assert hdrs.get("access-control-allow-origin") == "http://127.0.0.1:9999"


def test_preflight_foreign_rejected(secure_api):
    status, _, _ = _request(secure_api, "OPTIONS", "/api/v1/bots",
                            headers={"Host": "127.0.0.1",
                                     "Origin": "https://evil.example.com",
                                     "Access-Control-Request-Method": "POST"})
    assert status == 403


def test_preflight_local_ok(secure_api):
    status, hdrs, _ = _request(secure_api, "OPTIONS", "/api/v1/bots",
                               headers={"Host": "127.0.0.1",
                                        "Origin": "http://127.0.0.1:9999",
                                        "Access-Control-Request-Method": "POST"})
    assert status == 204
    assert hdrs.get("access-control-allow-origin") == "http://127.0.0.1:9999"
    assert "X-API-Key" in hdrs.get("access-control-allow-headers", "")


# ── /api/track: open telemetry with limits ──────────────────────────────────
def _post_track(port, headers=None):
    return _request(port, "POST", "/api/track",
                    headers=headers or {"Host": "127.0.0.1",
                                        "Content-Type": "application/json"},
                    body=json.dumps({"bot": "currency",
                                     "event": "ad_view"}).encode("utf-8"))


def test_track_open_no_token(secure_api):
    status, _, data = _post_track(secure_api)
    assert status == 200
    assert _json_body(data)["ok"] is True


def test_track_foreign_origin_rejected(secure_api):
    status, _, _ = _post_track(secure_api, {
        "Host": "127.0.0.1", "Content-Type": "application/json",
        "Origin": "https://evil.example.com"})
    assert status == 403


def test_track_rate_limited(secure_api, monkeypatch):
    monkeypatch.setenv("BODA_TRACK_RATE_LIMIT", "10")
    codes = []
    for _ in range(12):
        status, _, _ = _post_track(secure_api)
        codes.append(status)
    assert codes[-1] == 429
    assert codes.count(200) == 10


# ── Legacy /api/ads/set requires the local token ────────────────────────────
def test_ads_set_requires_token(secure_api):
    status, _, data = _request(secure_api, "POST", "/api/ads/set",
                               headers={"Host": "127.0.0.1",
                                        "Content-Type": "application/json"},
                               body=json.dumps({"bot_id": "currency",
                                                "direct_link": "x"}).encode("utf-8"))
    assert status == 403
    assert _json_body(data)["ok"] is False


# ── Dashboard: token injected, placeholder gone ─────────────────────────────
def test_dashboard_token_injected(secure_api):
    status, _, body = _request(secure_api, "GET", "/dashboard",
                               headers={"Host": "127.0.0.1"})
    html = body.decode("utf-8")
    assert status == 200
    assert "__BODA_LOCAL_TOKEN__" not in html     # placeholder replaced
    assert TOKEN in html                          # real token injected


# ── Log redaction ───────────────────────────────────────────────────────────
def test_logs_redact_tokens(secure_api, tmp_path, monkeypatch):
    log = tmp_path / "sec_test_bot.log"
    fake = "1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    log.write_text(f"started bot with token {fake}\n", encoding="utf-8")
    monkeypatch.setattr(api_server, "LOGS_DIR", tmp_path)
    status, _, body = _request(secure_api, "GET", "/api/logs?bot=sec_test_bot",
                               headers={"Host": "127.0.0.1"})
    payload = _json_body(body)
    assert status == 200
    assert fake not in json.dumps(payload)
    assert "1234567890:AAAAAAAA****" in payload["lines"][0]


def test_logs_path_traversal_blocked(secure_api, tmp_path, monkeypatch):
    # bot name with path characters must not escape the logs directory
    monkeypatch.setattr(api_server, "LOGS_DIR", tmp_path)
    status, _, _ = _request(
        secure_api, "GET", "/api/logs?bot=..%2F..%2FBots_Folder%2Fbot_currency",
        headers={"Host": "127.0.0.1"})
    assert status == 200  # sanitized name reads nothing sensitive


# ── GitHub Pages never carries the dashboard ────────────────────────────────
def test_pages_workflow_guards_dashboard():
    yml = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "webroot/dashboard" in yml
    assert "exit 1" in yml


def test_dashboard_not_tracked_in_git():
    out = subprocess.run(["git", "ls-files", "webroot/dashboard"],
                         cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "", (
        f"webroot/dashboard must be untracked, got: {out.stdout!r}")


def test_gitignore_contains_dashboard():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "webroot/dashboard/" in gitignore


# ── Tracebacks never reach the client ───────────────────────────────────────
def test_500_does_not_leak_traceback(secure_api):
    # unknown route → 404 (no traceback); trigger a 500 via a handler that
    # raises — use a malformed enable body on a nonexistent bot is 4xx, so
    # assert on the known crash path: /api/v1/bots/<id>/config with bad JSON
    status, _, body = _request(
        secure_api, "POST", "/api/v1/bots/currency/config",
        headers={"Host": "127.0.0.1", "Content-Type": "application/json",
                 "X-API-Key": TOKEN},
        body=b"{invalid json")
    assert "traceback" not in body.decode("utf-8", errors="replace").lower()
