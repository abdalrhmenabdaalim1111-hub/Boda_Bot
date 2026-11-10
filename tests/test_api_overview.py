"""
tests/test_api_overview.py — اختبار /api/overview + /dashboard

يغطي:
• get_engagement_overview(): الأعداد (إجمالي/فريد/DAU/WAU/MAU/الالتصاق)،
  قمع بوابة الشبكة (مستخدمون→تعيين→تفعيل)، الإحالات، أعلى البوتات
• HTTP: /api/overview يعيد JSON سليم و/dashboard صفحة HTML عامة بدون مفتاح
  (الوصول من localhost مصرح به حسب عقد _is_authorized)

بيانات البذر: مستخدم بأعمار 0/3/10/40 يوماً تعرض توزيع دقيق للحدود الزمنية.
"""
import json
import sys
import threading
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BOTS_DIR = ROOT / "Bots_Folder"
for _p in (str(ROOT), str(BOTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import api_server  # noqa: E402
import database    # noqa: E402

NOW = datetime.now()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    """قاعدة معزولة + 5 صفوف مستخدمين (4 فريد) بأعمار last_seen متفاوتة."""
    monkeypatch.setenv("BODA_DB_PATH", str(tmp_path / "ov.db"))
    database.BodaDatabase.reset_instance()
    db = database.get_db()

    seeds = [                      # (bot, user, last_seen منذ X يوماً)
        ("bot_a", 1001, 0),        # اليوم → DAU
        ("bot_a", 1002, 3),        # خلال أسبوع → WAU
        ("bot_a", 1003, 10),       # خلال شهر → MAU
        ("bot_a", 1004, 40),       # قديم → خارج كل النوافذ
        ("bot_b", 1001, 0),        # نفس المستخدم على بوت ثانٍ
    ]
    for bot, uid, days in seeds:
        db.track_user(bot, uid, full_name=f"user{uid}")
        with db._get_conn() as conn:
            conn.execute(
                "UPDATE users SET last_seen = ? WHERE user_id = ? AND bot_name = ?",
                (_iso(NOW - timedelta(days=days)), uid, bot))

    with db._get_conn() as conn:
        conn.execute(
            "INSERT INTO network_assignments (user_id, bot_id, assigned_at) VALUES (?,?,?)",
            (1001, "storebot", _iso(NOW - timedelta(days=1))))
        conn.execute(
            "INSERT INTO network_assignments (user_id, bot_id, assigned_at) VALUES (?,?,?)",
            (1002, "currency", _iso(NOW - timedelta(days=1))))
        conn.execute(
            "INSERT INTO network_activations (user_id, activated_at, is_active) VALUES (?,?,1)",
            (1001, _iso(NOW - timedelta(days=1))))
        for referred in (1002, 1003):
            conn.execute(
                "INSERT OR IGNORE INTO referrals (referrer_id, referred_id, bot_name, created_at) "
                "VALUES (?,?,?,?)",
                (1001, referred, "bot_a", _iso(NOW - timedelta(days=1))))

    yield db
    database.BodaDatabase.reset_instance()


def test_overview_counts_and_windows(seeded_db):
    ov = api_server.get_engagement_overview()
    u = ov["users"]
    assert u["total"] == 5                      # صفوف (مستخدم، بوت)
    assert u["distinct_users"] == 4
    assert u["dau"] == 1                        # 1001 فقط ظهر اليوم
    assert u["wau"] == 2                        # + 1002 (منذ 3 أيام)
    assert u["mau"] == 3                        # + 1003 (منذ 10 أيام)
    # 1004 (منذ 40 يوماً) خارج كل النوافذ
    assert ov["retention_dau_mau_percent"] == 33.3   # 1 / 3 * 100


def test_overview_funnel_and_referrals(seeded_db):
    ov = api_server.get_engagement_overview()
    f = ov["funnel"]
    assert f["users"] == 4
    assert f["assigned"] == 2
    assert f["assigned_percent"] == 50.0
    assert f["activated"] == 1
    assert f["activated_percent"] == 25.0

    r = ov["referrals"]
    assert r["total"] == 2
    assert r["unique_referrers"] == 1           # الداعي الوحيد 1001


def test_overview_top_bots(seeded_db):
    ov = api_server.get_engagement_overview()
    tops = ov["top_bots"]
    assert tops[0] == {"bot_name": "bot_a", "users": 4, "active_30d": 3}
    assert tops[1] == {"bot_name": "bot_b", "users": 1, "active_30d": 1}


def test_overview_includes_ab_section(seeded_db):
    ov = api_server.get_engagement_overview()
    ab = ov["ab_testing"]
    assert ab["ok"] is True
    assert set(ab["variants"].keys()) == {"A", "B"}
    assert ab["days"] == 30


@pytest.fixture()
def api_env(seeded_db, monkeypatch):
    """خادم API حقيقي على منفذ مؤقت (الوصول إما localhost — مصرح)."""
    monkeypatch.setattr(api_server, "API_SERVER_KEY", "testkey123")
    srv = api_server.run_api_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()
    srv.server_close()


def test_http_overview_payload(api_env):
    with urllib.request.urlopen(f"{api_env}/api/overview", timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    assert body["users"]["total"] == 5
    assert body["funnel"]["activated"] == 1
    assert body["ab_testing"]["ok"] is True


def test_http_dashboard_is_public_html(api_env):
    with urllib.request.urlopen(f"{api_env}/dashboard", timeout=10) as resp:
        ctype = resp.headers.get("Content-Type", "")
        html = resp.read().decode("utf-8")
    assert resp.status == 200
    assert ctype.startswith("text/html")
    assert "لوحة التحليلات" in html
    assert "boda_api_key" in html        # مفتاح التخزين المحلي في الصفحة


def test_http_overview_listed_in_404(api_env):
    try:
        urllib.request.urlopen(f"{api_env}/api/no_such_endpoint", timeout=10)
        raised = False
    except urllib.error.HTTPError as e:  # noqa: F821
        raised = True
        payload = e.read().decode("utf-8")
    assert raised
    assert "/api/overview" in payload and "/dashboard" in payload
