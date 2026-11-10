"""
tests/test_webhook_server.py — اختبارات خادم Webhook الحقيقي متعدد البوتات
يغطي: /health، المصادقة بالسر، التوجيه الصحيح، ومعالجة التحديثات.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

bots_dir = Path(__file__).parent.parent / "Bots_Folder"
if str(bots_dir) not in sys.path:
    sys.path.insert(0, str(bots_dir))

from webhook_server import WebhookServer, SECRET_HEADER


class FakeBot:
    def __init__(self):
        self.updates = []

    def process_new_updates(self, updates):
        self.updates.extend(updates)


def _http(url, method="GET", payload=None, headers=None):
    data = None
    hdrs = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


@pytest.fixture
def server():
    srv = WebhookServer(host="127.0.0.1", port=0, secret="s3cret")
    srv.register("alpha", FakeBot())
    srv.start()
    yield srv
    srv.stop()


def _base(srv):
    return f"http://127.0.0.1:{srv.actual_port}"


def test_health_endpoint(server):
    code, payload = _http(f"{_base(server)}/health")
    assert code == 200
    assert payload["status"] == "ok"
    assert payload["mode"] == "webhook"
    assert payload["bots"] == 1


def test_webhook_path_and_public_url(server):
    assert server.webhook_path("alpha") == "/webhook/s3cret/alpha"
    url = server.public_url("https://bots.example.com/", "alpha")
    assert url == "https://bots.example.com/webhook/s3cret/alpha"


def test_webhook_without_secret_uses_plain_path():
    srv = WebhookServer(host="127.0.0.1", port=0, secret="")
    try:
        assert srv.webhook_path("beta") == "/webhook/beta"
    finally:
        srv.stop()


def test_valid_update_is_dispatched(server):
    url = f"{_base(server)}{server.webhook_path('alpha')}"
    code, payload = _http(url, method="POST",
                          payload={"update_id": 123},
                          headers={SECRET_HEADER: "s3cret"})
    assert code == 200
    assert payload["ok"] is True
    assert len(server._bots["alpha"].updates) == 1
    assert server._bots["alpha"].updates[0].update_id == 123


def test_wrong_secret_is_rejected(server):
    url = f"{_base(server)}{server.webhook_path('alpha')}"
    code, _ = _http(url, method="POST", payload={"update_id": 1},
                    headers={SECRET_HEADER: "wrong"})
    assert code == 401
    assert server._bots["alpha"].updates == []


def test_missing_secret_header_is_rejected(server):
    url = f"{_base(server)}{server.webhook_path('alpha')}"
    code, _ = _http(url, method="POST", payload={"update_id": 1})
    assert code == 401


def test_unknown_bot_returns_404(server):
    url = f"{_base(server)}/webhook/s3cret/unknown"
    code, payload = _http(url, method="POST", payload={"update_id": 1},
                          headers={SECRET_HEADER: "s3cret"})
    assert code == 404
    assert "Unknown" in payload["error"]


def test_invalid_json_returns_400(server):
    url = f"{_base(server)}{server.webhook_path('alpha')}"
    req = urllib.request.Request(
        url, data=b"not-json", method="POST",
        headers={SECRET_HEADER: "s3cret", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "يجب أن يفشل الطلب"
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_processing_error_returns_500(server):
    class BrokenBot:
        def process_new_updates(self, updates):
            raise RuntimeError("boom")

    server.register("broken", BrokenBot())
    url = f"{_base(server)}{server.webhook_path('broken')}"
    code, _ = _http(url, method="POST", payload={"update_id": 5},
                    headers={SECRET_HEADER: "s3cret"})
    assert code == 500


def test_register_unregister():
    srv = WebhookServer(host="127.0.0.1", port=0)
    try:
        srv.register("bot_x", FakeBot())
        assert srv.registered_count == 1
        assert "x" in srv.bot_names()
        srv.unregister("x")
        assert srv.registered_count == 0
    finally:
        srv.stop()
