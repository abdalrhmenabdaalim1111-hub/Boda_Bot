"""
tests/test_api_server.py — اختبارات خادم API والمراقبة الصحية
"""
import pytest
import json
import urllib.request
import threading
import time
import api_server

@pytest.fixture(scope="module")
def live_server():
    """تشغيل خادم الـ API على منفذ تجريبي حر لاختبار الاستجابات الحقيقية"""
    test_port = 8899
    server = api_server.run_api_server(host="127.0.0.1", port=test_port)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    yield f"http://127.0.0.1:{test_port}"
    server.shutdown()
    server.server_close()


def test_health_endpoint(live_server):
    """اختبار نقطة النهاية /health"""
    url = f"{live_server}/health"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "healthy"
        assert "version" in data
        assert "python" in data


def test_bots_endpoint(live_server):
    """اختبار نقطة النهاية /api/bots"""
    url = f"{live_server}/api/bots"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        bots = json.loads(resp.read().decode("utf-8"))
        assert isinstance(bots, list)
        assert len(bots) > 0
        assert any(b.get("id") == "currency" for b in bots)


def test_stats_endpoint(live_server):
    """اختبار نقطة النهاية /api/stats"""
    url = f"{live_server}/api/stats"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert isinstance(data, dict)


def test_not_found_endpoint(live_server):
    """اختبار طلب مسار غير موجود (404)"""
    url = f"{live_server}/api/unknown_endpoint"
    try:
        urllib.request.urlopen(url)
        assert False, "Should raise HTTPError"
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_readiness_endpoint(live_server):
    """فحص /ready: 200 عند الجاهزية و503 عند غياب البيئة/قاعدة البيانات"""
    url = f"{live_server}/ready"
    try:
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ready"] is True
    except urllib.error.HTTPError as e:
        assert e.code == 503
        data = json.loads(e.read().decode("utf-8"))
        assert data["ready"] is False
    assert "checks" in data
    assert "database_ready" in data["checks"]

