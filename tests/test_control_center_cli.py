"""
tests/test_control_center_cli.py — اختبارات أوامر مركز التحكم في dev_tools

تغطي:
• cc-status / cc-bots / cc-audit / cc-logs / cc-lifecycle
• التعامل مع خادم غير متاح (رسالة خطأ واضحة بدل انهيار)
"""

import json
import threading
import time
import urllib.request

import pytest

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401  (path bootstrap)
from tests.cc_fixtures import cc_supervisor  # noqa: F401  (fixture)

import api_server
import dev_tools


@pytest.fixture()
def live_cli(tmp_path, monkeypatch, cc_supervisor):
    """A running Control Center API plus a CLI pointed at it."""
    monkeypatch.setenv("BODA_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("BODA_CC_URL", "")
    monkeypatch.setenv("BODA_LOCAL_TOKEN", "cli-test-token")

    import database
    from control_center import db as cc_db_module

    database.BodaDatabase.reset_instance()
    cc_db_module.reset_db()

    server = api_server.run_api_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.4)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("BODA_CC_URL", base)

    yield base

    server.shutdown()
    server.server_close()
    database.BodaDatabase.reset_instance()
    cc_db_module.reset_db()


def test_cc_status(live_cli, capsys):
    """cc-status يعرض حالة مركز التحكم"""
    assert dev_tools.cmd_cc_status() == 0
    output = capsys.readouterr().out
    assert "مركز التحكم" in output
    assert "الترحيلات" in output


def test_cc_bots(live_cli, capsys):
    """cc-bots يعرض جدول البوتات"""
    assert dev_tools.cmd_cc_bots() == 0
    output = capsys.readouterr().out
    assert "البوتات" in output
    assert "currency" in output


def test_cc_audit_after_a_mutation(live_cli, capsys):
    """التغييرات تُسجَّل في سجل التدقيق ويظهرها cc-audit"""
    body = json.dumps({"enabled": False}).encode("utf-8")
    req = urllib.request.Request(
        live_cli + "/api/v1/bots/currency/enable", data=body,
        headers={"Content-Type": "application/json",
                 "X-API-Key": "cli-test-token"}, method="POST")
    urllib.request.urlopen(req, timeout=15).read()

    assert dev_tools.cmd_cc_audit(10) == 0
    output = capsys.readouterr().out
    assert "bot.disable" in output


def test_cc_lifecycle(live_cli, capsys):
    """cc-lifecycle يبدأ ويوقف بوتاً"""
    assert dev_tools.cmd_cc_lifecycle("start", "currency") == 0
    assert dev_tools.cmd_cc_lifecycle("stop", "currency") == 0
    output = capsys.readouterr().out
    assert "start" in output or "stop" in output


def test_cc_lifecycle_requires_bot_id(live_cli):
    """الأمر بدون معرّف بوت يعطي رسالة استخدام واضحة"""
    assert dev_tools.cmd_cc_lifecycle("start", "") == 1


def test_cc_logs(live_cli, capsys):
    """cc-logs يقرأ سجل بوت"""
    assert dev_tools.cmd_cc_logs("currency", 10) == 0
    output = capsys.readouterr().out
    assert "currency" in output


def test_cli_reports_unreachable_server(monkeypatch, capsys):
    """عند عدم تشغيل الخادم تظهر رسالة واضحة لا انهيار"""
    monkeypatch.setenv("BODA_CC_URL", "http://127.0.0.1:9")
    assert dev_tools.cmd_cc_status() == 1
    output = capsys.readouterr().out
    assert "api_server.py" in output


def test_cc_migrate(live_cli, capsys):
    """cc-migrate يعرض حالة الترحيلات"""
    assert dev_tools.cmd_cc_migrate() == 0
    output = capsys.readouterr().out
    assert "الترحيلات" in output
