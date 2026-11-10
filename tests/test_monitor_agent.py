"""
tests/test_monitor_agent.py — اختبارات وكيل المراقبة وتنبيهات Telegram
"""
import monitor_agent


# ── تقييم الحالة ─────────────────────────────────────────────────────────────
def test_evaluate_health_ok():
    ok, detail = monitor_agent.evaluate_health(
        200, {"status": "healthy", "database_ready": True})
    assert ok is True
    assert detail == "سليم"


def test_evaluate_health_accepts_ok_status():
    assert monitor_agent.evaluate_health(200, {"status": "ok"})[0] is True


def test_evaluate_health_http_error():
    ok, detail = monitor_agent.evaluate_health(503, {"status": "healthy"})
    assert ok is False
    assert "503" in detail


def test_evaluate_health_database_not_ready():
    ok, detail = monitor_agent.evaluate_health(
        200, {"status": "healthy", "database_ready": False})
    assert ok is False
    assert "قاعدة البيانات" in detail


def test_evaluate_health_invalid_payload():
    assert monitor_agent.evaluate_health(200, "text")[0] is False


def test_evaluate_health_missing_status():
    assert monitor_agent.evaluate_health(200, {})[0] is False


# ── قرار التنبيه ─────────────────────────────────────────────────────────────
def test_alert_on_first_failure():
    assert monitor_agent.should_alert(False, None, 0, 100, 1800) is True


def test_alert_on_transition_to_failure():
    assert monitor_agent.should_alert(False, True, 0, 100, 1800) is True


def test_no_repeat_alert_within_cooldown():
    assert monitor_agent.should_alert(False, False, 1000, 1100, 1800) is False


def test_repeat_alert_after_cooldown():
    assert monitor_agent.should_alert(False, False, 1000, 2900, 1800) is True


def test_alert_on_recovery_only_after_failure():
    assert monitor_agent.should_alert(True, False, 0, 100, 1800) is True
    assert monitor_agent.should_alert(True, True, 0, 100, 1800) is False


# ── صياغة الرسائل ────────────────────────────────────────────────────────────
def test_format_failure_alert():
    msg = monitor_agent.format_alert(False, "HTTP 500")
    assert "🚨" in msg
    assert "HTTP 500" in msg


def test_format_recovery_alert():
    msg = monitor_agent.format_alert(True, "سليم", {"total_users": 42})
    assert "✅" in msg
    assert "42" in msg


# ── الإرسال ──────────────────────────────────────────────────────────────────
def test_send_alert_disabled_without_config(monkeypatch):
    monkeypatch.delenv("BODA_MONITOR_BOT_TOKEN", raising=False)
    monkeypatch.delenv("BODA_ADMIN_CHAT_ID", raising=False)
    assert monitor_agent.send_telegram_alert("test") is False


# ── الفحص الشامل ─────────────────────────────────────────────────────────────
def test_check_once_with_mocked_fetch(monkeypatch):
    calls = {"health": 0, "stats": 0}

    def fake_fetch(url, timeout=8.0, headers=None):
        if url.endswith("/health"):
            calls["health"] += 1
            return 200, {"status": "healthy", "database_ready": True}
        calls["stats"] += 1
        return 200, {"total_users": 7}

    monkeypatch.setattr(monitor_agent, "fetch_json", fake_fetch)
    report = monitor_agent.check_once(
        "http://x/health", "http://x/api/stats", "key")
    assert report["ok"] is True
    assert report["stats"]["total_users"] == 7
    assert calls == {"health": 1, "stats": 1}


def test_check_once_skips_stats_when_unhealthy(monkeypatch):
    def fake_fetch(url, timeout=8.0, headers=None):
        return 500, {"status": "down"}

    monkeypatch.setattr(monitor_agent, "fetch_json", fake_fetch)
    report = monitor_agent.check_once("http://x/health", "http://x/api/stats")
    assert report["ok"] is False
    assert report["stats"] is None


def test_run_once_exit_codes(monkeypatch):
    monkeypatch.setattr(monitor_agent, "check_once",
                        lambda *a, **k: {"ok": True, "detail": "سليم",
                                         "stats": None})
    assert monitor_agent.run_once("http://x/health") == 0

    monkeypatch.setattr(monitor_agent, "check_once",
                        lambda *a, **k: {"ok": False, "detail": "HTTP 500",
                                         "stats": None})
    assert monitor_agent.run_once("http://x/health", notify=False) == 1
