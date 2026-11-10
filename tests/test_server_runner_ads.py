"""
tests/test_server_runner_ads.py — اختبارات مزامنة إعلانات Monetag التلقائية وخادم السيرفر
يتحقق من:
1. المزامنة الاستباقية preflight_sync_mini_apps().
2. مراقب الملفات AdConfigWatcher والـ Hot Reload التلقائي.
3. استجابة WebhookServer لتطبيقات الويب المصغرة (/apps/<bot_id>) وترويسات منع الكاش.
4. واجهة برمجة التطبيقات (/api/ads/status و /api/ads/set) والتحديث الحي لملفات HTML.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).parent.parent.resolve()
BOTS_DIR = BASE_DIR / "Bots_Folder"
DATA_DIR = BASE_DIR / "Data"
WEBROOT_DIR = BASE_DIR / "webroot"
WEBAPPS_DIR = BASE_DIR / "webapps"

if str(BOTS_DIR) not in sys.path:
    sys.path.insert(0, str(BOTS_DIR))

import server_runner
from ad_manager import get_ad_manager
from ad_watcher import AdConfigWatcher, start_ad_watcher, sync_mini_apps
from webhook_server import WebhookServer


class DummyBot:
    def process_new_updates(self, updates):
        pass


def _http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TestClient/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8")


def _http_post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "TestClient/1.0"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.headers, json.loads(e.read().decode("utf-8"))


# ── 1. اختبار المزامنة الاستباقية preflight_sync_mini_apps ───────────────────
def test_preflight_sync_mini_apps():
    """التحقق من أن مزامنة البداية تعمل وتُنشئ وتُحدّث ملفات التطبيقات بنجاح."""
    server_runner.preflight_sync_mini_apps()
    currency_app = WEBROOT_DIR / "currency" / "index.html"
    store_app = WEBROOT_DIR / "store" / "index.html"
    assert currency_app.exists(), "يجب أن يكون ملف currency/index.html موجوداً"
    assert store_app.exists(), "يجب أن يكون ملف store/index.html موجوداً"
    content = currency_app.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


# ── 2. اختبار مراقب ملفات الإعلانات AdConfigWatcher ─────────────────────────
def test_ad_config_watcher_sync():
    """التحقق من أن AdConfigWatcher يرصد التعديلات وينفذ المزامنة بنجاح."""
    synced_reports = []
    watcher = AdConfigWatcher(check_interval=0.1, on_sync=lambda r: synced_reports.append(r))

    # فحص أولي: لا تغييرات
    assert watcher.check_and_sync() is False

    # محاكاة تعديل على ملف monetag_config.json
    monetag_file = DATA_DIR / "monetag_config.json"
    if monetag_file.exists():
        # لمس الملف لتحديث وقت التعديل
        now = time.time()
        os.utime(monetag_file, (now, now))

        # الفحص التالي يجب أن يرصد التغيير
        changed = watcher.check_and_sync()
        assert changed is True
        assert len(synced_reports) == 1
        assert synced_reports[0].get("ok") is True


# ── 3. اختبار تشغيل وإيقاف مراقب الإعلانات في خيط خلفي ─────────────────────
def test_start_ad_watcher_thread():
    """التحقق من بدء خيط AdWatcher وإيقافه النظيف عند تفعيل stop_event."""
    stop_event = threading.Event()
    t = start_ad_watcher(stop_event, check_interval=0.1)
    assert t.is_alive()
    time.sleep(0.2)
    stop_event.set()
    t.join(timeout=2.0)
    assert not t.is_alive()


# ── 4. اختبار خادم WebhookServer لتقديم تطبيقات الويب المصغرة ───────────────
def test_webhook_server_serves_miniapp():
    """التحقق من أن WebhookServer يقدم صفحات HTML بترويسات No-Cache لمستخدمي تيليجرام."""
    srv = WebhookServer(host="127.0.0.1", port=0)
    srv.register("currency", DummyBot())
    srv.start()
    try:
        base_url = f"http://127.0.0.1:{srv.actual_port}"

        # طلب تطبيق currency
        status, headers, body = _http_get(f"{base_url}/apps/currency")
        assert status == 200
        assert "text/html" in headers.get("Content-Type", "")
        assert "no-cache" in headers.get("Cache-Control", "")
        assert "محول العملات" in body or "currency" in body.lower()

        # طلب تطبيق غير موجود
        status_404, _, body_404 = _http_get(f"{base_url}/apps/nonexistent_bot_xyz")
        assert status_404 == 404
        assert "التطبيق غير موجود" in body_404 or "MiniApp Not Found" in body_404
    finally:
        srv.stop()


# ── 5. اختبار واجهة برمجة الإعلانات /api/ads/status و /api/ads/set ──────────
def test_webhook_server_ad_endpoints():
    """التحقق من استعراض وتحديث إعلانات Monetag عبر WebhookServer وحقنها الحي."""
    srv = WebhookServer(host="127.0.0.1", port=0)
    srv.register("test_bot", DummyBot())
    srv.start()
    try:
        base_url = f"http://127.0.0.1:{srv.actual_port}"

        # 1. استعراض الحالات
        req = urllib.request.Request(f"{base_url}/api/ads/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert "apps" in data

        # 2. تحديث إعلان لبوت currency
        test_zone = "99887766"
        test_link = "https://monetag.example.com/test_click"
        payload = {
            "bot_id": "currency",
            "direct_link": test_link,
            "zone_id": test_zone,
            "active": True
        }
        status, _, res = _http_post_json(f"{base_url}/api/ads/set", payload)
        assert status == 200
        assert res["ok"] is True

        # التحقق من أن ملف HTML لـ currency قد حُقنت فيه الشفرة الجديدة مباشرة
        currency_html = (WEBROOT_DIR / "currency" / "index.html").read_text(encoding="utf-8")
        assert test_zone in currency_html or test_link in currency_html
    finally:
        srv.stop()
