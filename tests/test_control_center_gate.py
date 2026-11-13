# -*- coding: utf-8 -*-
"""
tests/test_control_center_gate.py — Subscription Gate hardening tests (Phase 3-4).

Covers:
- Channels library CRUD (sub_channels)
- Gate profiles & slots + effective-profile resolution (bot > category > global)
- Membership cache (TTL, expiry, cleanup, CHECK-safe statuses)
- Gate events: privacy hashing, taxonomy validation, funnel math
- Exports (CSV escaping / JSON)
- Compliance checker (honest-copy policy, docs/GATE_POLICY.md §3)
- API layer: admin-only writes, open reads, audit trail
- Bots side: fail-open policy, shared cache key, shared hash salt,
  category resolution, inactive-channel filtering, event taxonomy,
  gate message rendering (no broken buttons)
"""

import csv
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from control_center import gate, api, config
from control_center.auth import authorize
from control_center.db import get_db
from control_center.migrations import ensure_ready

from Bots_Folder.gate_core import GateCore, user_id_hash as bots_user_hash
from Bots_Folder.gate_middleware import GateMiddleware


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Isolate test environment: separate DB, registry."""
    test_db = tmp_path / "test_boda_bot.db"
    monkeypatch.setenv("BODA_DB_PATH", str(test_db))
    monkeypatch.setattr(config, "db_path", lambda: str(test_db))

    test_registry = tmp_path / "bots_registry.json"
    registry_data = [
        {
            "id": "testbot",
            "name": "Test Bot",
            "description": "A test bot",
            "short_desc": "Test bot short",
            "emoji": "🤖",
            "url": "https://t.me/TestBot",
            "username": "@TestBot",
            "tag": "Testing",
            "hidden": False,
            "file": "bot_testbot.py",
            "category": "Testing",
        }
    ]
    test_registry.write_text(json.dumps(registry_data, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)

    try:
        from database import BodaDatabase
        BodaDatabase.reset_instance()
    except ImportError:
        pass

    yield

    try:
        from database import BodaDatabase
        BodaDatabase.reset_instance()
    except ImportError:
        pass
    if test_db.exists():
        try:
            test_db.unlink()
        except PermissionError:
            pass  # Windows: file may be locked


def _ensure_bot_config(bot_ids, features=None):
    """Insert bot_config rows (required by FK + gate feature flag).

    Upserts ``features`` so a bot can be re-configured within one test.
    """
    db_obj = get_db()
    if not db_obj:
        return
    features = features if features is not None else {}
    try:
        with db_obj._get_conn() as conn:
            for bot_id in bot_ids:
                conn.execute("""
                    INSERT INTO bot_config
                    (bot_id, display_name, category, features, enabled, created_at, updated_at)
                    VALUES (?, ?, 'Testing', ?, 1, datetime('now'), datetime('now'))
                    ON CONFLICT(bot_id) DO UPDATE SET
                        features = excluded.features
                """, (bot_id, bot_id.replace("_", " ").title(), json.dumps(features)))
    except Exception as exc:
        print(f"bot_config setup warning: {exc}")


@pytest.fixture
def db():
    """Initialize DB with migrations and bot_config rows."""
    ensure_ready()
    _ensure_bot_config(["testbot", "otherbot"])
    return get_db()


@pytest.fixture
def api_key(monkeypatch):
    """Set API server key for auth."""
    monkeypatch.setenv("API_SERVER_KEY", "test-secret-key-123")


@pytest.fixture
def mock_request_factory(api_key):
    """Create mock request objects (same shape as the store tests)."""
    class MockRequest:
        def __init__(self, method="GET", path="/", headers=None, body=b"", query=None,
                     json_data=None, params=None):
            self.method = method
            self.path = path
            self.headers = headers or {}
            self._body = body
            self._json_data = json_data
            self.query_params = query or {}
            self._params = params or {}  # router-extracted path params
            class Handler:
                client_address = ("127.0.0.1", 12345)
            self.handler = Handler()

        def header(self, name, default=""):
            return self.headers.get(name, default)

        @property
        def body(self):
            return self._body

        def json(self):
            if self._json_data is not None:
                return self._json_data
            if self._body:
                return json.loads(self._body)
            return {}

        def q(self, name, default=""):
            return self.query_params.get(name, default)

        def q_int(self, name, default=0):
            val = self.query_params.get(name, default)
            return int(val) if val else default

        def param(self, name):
            if name in self._params:
                return self._params[name]
            import re
            match = re.search(rf"/{name}/(\d+)", self.path)
            return match.group(1) if match else None

        def client_ip(self):
            return "127.0.0.1"

    def make_request(user_role=None, **kwargs):
        req = MockRequest(**kwargs)
        if user_role:
            req.user = {"role": user_role, "username": f"test_{user_role}"}
        else:
            req.user = None
        return req

    return make_request


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_channel(db, n=1, **overrides):
    """Create a gate channel and return its row."""
    fields = {
        "title": f"قناة {n}",
        "chat_type": "channel",
        "chat_id": -1000000000 - n,
        "username": f"@chan{n}",
    }
    fields.update(overrides)
    res = gate.create_channel(**fields)
    assert res.get("ok"), f"channel create failed: {res}"
    return res["channel"]


def _make_profile(db, name, scope_type, scope_value=None, slots=(), **overrides):
    """Create a gate profile (with slot channel dicts) and return it."""
    res = gate.create_profile(name=name, scope_type=scope_type,
                              scope_value=scope_value, slots=list(slots), **overrides)
    assert res.get("ok"), f"profile create failed: {res}"
    return res["profile"]


def _fetch_events(where="", params=()):
    db_obj = get_db()
    with db_obj._get_conn() as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM gate_events {where}", params).fetchall()]


def _fetch_cache(user_id, channel_id):
    db_obj = get_db()
    with db_obj._get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM membership_cache WHERE user_id=? AND channel_id=?",
            (user_id, channel_id)).fetchone()
        return dict(row) if row else None


# ═════════════════════════════════════════════════════════════════════════════
# A. Channels Library (control_center/gate.py)
# ═════════════════════════════════════════════════════════════════════════════

def test_create_and_get_channel(db):
    ch = _make_channel(db, 1, username="@bodachan", invite_link="https://t.me/+abc")
    assert ch["id"] > 0
    assert ch["chat_type"] == "channel"
    assert ch["chat_id"] == -1000000001
    assert ch["username"] == "@bodachan"
    assert ch["invite_link"] == "https://t.me/+abc"
    assert ch["is_active"] == 1
    assert ch["language"] == "ar"

    fetched = gate.get_channel(ch["id"])
    assert fetched["title"] == "قناة 1"


def test_create_channel_requires_fields(db):
    res = gate.create_channel(title="only title")
    assert res["ok"] is False
    assert "chat_type" in res["error"]


def test_create_channel_rejects_duplicate_chat_id(db):
    _make_channel(db, 1)
    res = gate.create_channel(title="مكرر", chat_type="channel", chat_id=-1000000001)
    assert res["ok"] is False


def test_update_channel(db):
    ch = _make_channel(db, 1)
    res = gate.update_channel(ch["id"], title="عنوان جديد", invite_link="https://t.me/+xyz")
    assert res["ok"] is True and res["updated"] is True
    fetched = gate.get_channel(ch["id"])
    assert fetched["title"] == "عنوان جديد"
    assert fetched["invite_link"] == "https://t.me/+xyz"


def test_delete_channel_is_soft(db):
    ch = _make_channel(db, 1)
    res = gate.delete_channel(ch["id"])
    assert res["ok"] is True
    fetched = gate.get_channel(ch["id"])
    assert fetched["is_active"] == 0  # row kept, deactivated
    active = gate.list_channels(active_only=True)
    assert all(c["id"] != ch["id"] for c in active)


def test_list_channels(db):
    c1 = _make_channel(db, 1)
    c2 = _make_channel(db, 2)
    gate.delete_channel(c2["id"])
    # migration 6 seeds one placeholder channel too — assert relative to our rows
    all_ids = {c["id"] for c in gate.list_channels()}
    active_ids = {c["id"] for c in gate.list_channels(active_only=True)}
    assert {c1["id"], c2["id"]} <= all_ids
    assert c1["id"] in active_ids
    assert c2["id"] not in active_ids


def test_channel_health_structure(db):
    ch = _make_channel(db, 1, checker_bot_admin=1)
    health = gate.validate_channel_health(ch["id"])
    assert health["ok"] is True
    assert health["checker_is_admin"] is True
    assert health["chat_type"] == "channel"


# ═════════════════════════════════════════════════════════════════════════════
# B. Profiles & Effective-Profile Resolution
# ═════════════════════════════════════════════════════════════════════════════

def test_create_profile_with_ordered_slots(db):
    ch1 = _make_channel(db, 1)
    ch2 = _make_channel(db, 2)
    profile = _make_profile(db, "p1", "global",
                            slots=[{"channel_id": ch2["id"]}, {"channel_id": ch1["id"]}])
    assert profile["mode"] == "all"
    assert profile["required_count"] == 5
    positions = [s["position"] for s in profile["slots"]]
    assert positions == [1, 2]  # ordered by position
    # slots enriched with channel info
    assert profile["slots"][0]["channel"]["id"] == ch2["id"]


def test_update_profile_replaces_slots(db):
    ch1 = _make_channel(db, 1)
    ch2 = _make_channel(db, 2)
    profile = _make_profile(db, "p1", "bot", scope_value="testbot",
                            slots=[{"channel_id": ch1["id"]}])
    res = gate.update_profile(profile["id"],
                              slots=[{"channel_id": ch2["id"], "is_pinned": 1}])
    assert res["ok"] is True
    fetched = gate.get_profile(profile["id"])
    assert len(fetched["slots"]) == 1
    assert fetched["slots"][0]["channel_id"] == ch2["id"]
    assert fetched["slots"][0]["is_pinned"] == 1


def test_delete_profile_is_soft(db):
    profile = _make_profile(db, "p1", "global")
    assert gate.delete_profile(profile["id"])["ok"] is True
    fetched = gate.get_profile(profile["id"])
    assert fetched["is_active"] == 0
    assert gate.list_profiles() == []  # only active profiles listed


def test_effective_profile_order_bot_beats_category_beats_global(db):
    ch = _make_channel(db, 1)
    g = _make_profile(db, "global_p", "global", slots=[{"channel_id": ch["id"]}])
    c = _make_profile(db, "cat_p", "category", scope_value="Testing")
    b = _make_profile(db, "bot_p", "bot", scope_value="testbot")

    # 1. bot wins
    eff = gate.get_effective_profile("testbot", "Testing")
    assert eff["id"] == b["id"]

    # 2. deactivate bot profile → category wins
    gate.update_profile(b["id"], is_active=0)
    eff = gate.get_effective_profile("testbot", "Testing")
    assert eff["id"] == c["id"]

    # 3. deactivate category → global wins
    gate.update_profile(c["id"], is_active=0)
    eff = gate.get_effective_profile("testbot", "Testing")
    assert eff["id"] == g["id"]

    # 4. deactivate global → nothing
    gate.update_profile(g["id"], is_active=0)
    assert gate.get_effective_profile("testbot", "Testing") == {}


def test_effective_profile_category_only_when_provided(db):
    _make_profile(db, "cat_p", "category", scope_value="Testing")
    # no category passed and no bot profile → global absent → empty
    assert gate.get_effective_profile("testbot", None) == {}
    # category passed → resolved
    eff = gate.get_effective_profile("testbot", "Testing")
    assert eff["scope_type"] == "category"


def test_effective_profile_drops_inactive_channel_slots(db):
    ch_active = _make_channel(db, 1)
    ch_dead = _make_channel(db, 2)
    profile = _make_profile(db, "p1", "global", slots=[
        {"channel_id": ch_active["id"]},
        {"channel_id": ch_dead["id"]},
    ])
    gate.delete_channel(ch_dead["id"])  # soft delete

    eff = gate.get_effective_profile("testbot")
    assert eff["id"] == profile["id"]
    slot_channels = [s["channel_id"] for s in eff["slots"]]
    assert ch_dead["id"] not in slot_channels
    assert ch_active["id"] in slot_channels

    # management view keeps both slots
    mgmt = gate.get_profile(profile["id"])
    assert len(mgmt["slots"]) == 2


# ═════════════════════════════════════════════════════════════════════════════
# C. Membership Cache
# ═════════════════════════════════════════════════════════════════════════════

def test_cache_roundtrip_and_expiry(db):
    ch = _make_channel(db, 1)
    assert gate.set_cached_membership(42, ch["id"], "member")["ok"] is True
    assert gate.is_user_member_cached(42, ch["id"]) is True

    # expire it
    db_obj = get_db()
    with db_obj._get_conn() as conn:
        conn.execute("UPDATE membership_cache SET expires_at=?",
                     ((datetime.now() - timedelta(hours=1)).isoformat(),))
    assert gate.is_user_member_cached(42, ch["id"]) is False


def test_cache_only_member_counts(db):
    ch = _make_channel(db, 1)
    gate.set_cached_membership(42, ch["id"], "not_member")
    assert gate.is_user_member_cached(42, ch["id"]) is False


def test_cache_normalizes_left_status(db):
    """'left' violates the CHECK constraint — must be stored as 'not_member'."""
    ch = _make_channel(db, 1)
    res = gate.set_cached_membership(42, ch["id"], "left")
    assert res["ok"] is True, "left status must not violate CHECK constraint"
    row = _fetch_cache(42, ch["id"])
    assert row["status"] == "not_member"


def test_clear_expired_cache(db):
    ch = _make_channel(db, 1)
    gate.set_cached_membership(1, ch["id"], "member")
    gate.set_cached_membership(2, ch["id"], "member", ttl_hours=-1)  # already expired
    deleted = gate.clear_expired_cache()
    assert deleted == 1
    assert _fetch_cache(1, ch["id"]) is not None
    assert _fetch_cache(2, ch["id"]) is None


# ═════════════════════════════════════════════════════════════════════════════
# D. Gate Events & Funnel
# ═════════════════════════════════════════════════════════════════════════════

def test_record_event_hashes_user_id(db):
    res = gate.record_gate_event("testbot", 123456, "gate_shown",
                                 profile_id=1, metadata={"lang": "ar"})
    assert res["ok"] is True, f"record_gate_event must work: {res}"

    events = _fetch_events()
    assert len(events) == 1
    # raw user id must never appear — only the salted hash
    assert "123456" not in events[0]["user_id_hash"]
    assert events[0]["user_id_hash"] == gate._user_id_hash(123456)
    assert json.loads(events[0]["metadata"]) == {"lang": "ar"}


def test_record_event_rejects_unknown_type(db):
    res = gate.record_gate_event("testbot", 1, "not_a_real_event")
    assert res["ok"] is False
    assert "Invalid event type" in res["error"]


def test_funnel_aggregation_and_math(db):
    for _ in range(10):
        gate.record_gate_event("testbot", 1, "gate_shown")
    for _ in range(4):
        gate.record_gate_event("testbot", 1, "verified")
    for _ in range(2):
        gate.record_gate_event("testbot", 1, "failed_open")
    for _ in range(3):
        gate.record_gate_event("otherbot", 2, "gate_shown")

    funnel = gate.get_gate_funnel()
    tb = funnel["testbot"]
    assert tb["gate_shown"] == 10
    assert tb["verified"] == 4
    assert tb["failed_open"] == 2
    # drop-off = (10 - 4 - 2) / 10
    assert tb["drop_off_pct"] == 40.0
    assert tb["conversion_pct"] == 40.0
    assert funnel["otherbot"]["gate_shown"] == 3

    # bot filter
    only = gate.get_gate_funnel(bot_id="otherbot")
    assert list(only.keys()) == ["otherbot"]


def test_funnel_drop_off_clamped_non_negative(db):
    """verified+failed_open can exceed shown — drop_off must clamp at 0."""
    for _ in range(2):
        gate.record_gate_event("testbot", 1, "gate_shown")
    for _ in range(5):
        gate.record_gate_event("testbot", 1, "verified")

    funnel = gate.get_gate_funnel(bot_id="testbot")
    assert funnel["testbot"]["drop_off_pct"] == 0


def test_funnel_days_window(db):
    gate.record_gate_event("testbot", 1, "gate_shown")
    db_obj = get_db()
    with db_obj._get_conn() as conn:
        conn.execute(
            "UPDATE gate_events SET created_at=?",
            ((datetime.now() - timedelta(days=40)).isoformat(),))

    assert gate.get_gate_funnel(days=30) == {}
    assert gate.get_gate_funnel(days=60)["testbot"]["gate_shown"] == 1


def test_channel_joins(db):
    ch = _make_channel(db, 1)
    gate.record_gate_event("testbot", 1, "join_clicked", channel_id=ch["id"])
    gate.record_gate_event("testbot", 2, "join_clicked", channel_id=ch["id"])
    joins = gate.get_channel_joins()
    assert joins == [{"channel_id": ch["id"], "joins": 2}]


# ═════════════════════════════════════════════════════════════════════════════
# E. Privacy & Exports
# ═════════════════════════════════════════════════════════════════════════════

def test_csv_export_escapes_metadata(db):
    """Metadata JSON contains commas — naive string join would corrupt the CSV."""
    gate.record_gate_event("testbot", 1, "gate_shown",
                           metadata={"note": "hello, world, with commas"})
    csv_text = gate.export_gate_events_csv()
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0][0] == "bot_id"
    assert len(rows) == 2
    assert len(rows[1]) == 7  # all 7 columns intact despite embedded commas
    assert rows[1][5] == '{"note": "hello, world, with commas"}'


def test_json_export_parsable_and_hashed(db):
    gate.record_gate_event("testbot", 42, "verified")
    data = json.loads(gate.export_gate_events_json())
    assert len(data) == 1
    assert data[0]["event"] == "verified"
    # stored hash equals the salted hash — never the raw id
    assert data[0]["user_id_hash"] == gate._user_id_hash(42)
    assert len(data[0]["user_id_hash"]) == 16


def test_salt_consistency_across_modules(monkeypatch, db):
    """Both sides must produce identical hashes for the same user (funnel joins)."""
    monkeypatch.setenv("BODA_GATE_SALT", "custom-test-salt")
    assert gate._user_id_hash(999) == bots_user_hash(999)

    monkeypatch.delenv("BODA_GATE_SALT", raising=False)
    assert gate._user_id_hash(999) == bots_user_hash(999)


# ═════════════════════════════════════════════════════════════════════════════
# F. Compliance (docs/GATE_POLICY.md §3)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text,category", [
    ("هذا الدواء يشفي المريض تماما", "medical"),
    ("this cream will cure your illness", "medical"),
    ("ربح مضمون بدون مخاطرة", "financial"),
    ("guaranteed profit every month", "financial"),
    ("نتيجة مؤكدة 100%", "guarantee"),
    ("verify you are human to continue", "deceptive"),
    ("أثبت أنك لست بوت", "deceptive"),
])
def test_compliance_flags_risky_copy(db, text, category):
    warnings = gate._compliance_check(text)
    assert any(w["category"] == category for w in warnings), \
        f"'{text}' must trigger the {category} warning"


def test_compliance_allows_honest_copy(db):
    assert gate._compliance_check("انضم للقناة لتستخدم البوت") == []
    assert gate._compliance_check("Join the channel to use this bot") == []
    assert gate._compliance_check("") == []


# ═════════════════════════════════════════════════════════════════════════════
# G. Health & Alerts
# ═════════════════════════════════════════════════════════════════════════════

def test_gate_health_reports_issues(db):
    _make_channel(db, 1, checker_bot_admin=0)  # checker not admin → issue
    health = gate.get_gate_health()
    assert health["total_channels"] == 1
    assert health["healthy_channels"] == 0
    assert len(health["issues"]) == 1
    assert health["status"] == "critical"


def test_gate_health_ok_when_checker_admin(db):
    _make_channel(db, 1, checker_bot_admin=1)
    health = gate.get_gate_health()
    assert health["status"] == "healthy"
    assert health["issues"] == []


def test_check_and_alert_channels(db):
    _make_channel(db, 1, checker_bot_admin=0)
    result = gate.check_and_alert_channels()
    assert result["alerts"][0]["type"] == "checker_not_admin"


# ═════════════════════════════════════════════════════════════════════════════
# H. API Layer
# ═════════════════════════════════════════════════════════════════════════════

def test_gate_write_endpoints_require_admin(db, mock_request_factory):
    """All mutating gate endpoints must reject unauthenticated non-local calls."""
    endpoints = [
        (api.create_gate_channel_api, "POST", "/api/v1/gate/channels",
         {"title": "x", "chat_type": "channel", "chat_id": -100}),
        (api.update_gate_channel_api, "PATCH", "/api/v1/gate/channels/1", {}),
        (api.delete_gate_channel_api, "DELETE", "/api/v1/gate/channels/1", None),
        (api.test_gate_channel_api, "POST", "/api/v1/gate/channels/1/test", None),
        (api.generate_gate_invite_api, "POST", "/api/v1/gate/channels/1/invite", {}),
        (api.create_gate_profile_api, "POST", "/api/v1/gate/profiles", {}),
        (api.update_gate_profile_api, "PATCH", "/api/v1/gate/profiles/1", {}),
        (api.delete_gate_profile_api, "DELETE", "/api/v1/gate/profiles/1", None),
        (api.gate_health_check_all_api, "POST", "/api/v1/gate/health/check-all", None),
    ]
    for handler, method, path, payload in endpoints:
        req = mock_request_factory(method=method, path=path, json_data=payload)
        req.handler.client_address = ("192.168.1.1", 12345)  # non-local, no key
        resp = handler(req)
        assert getattr(resp, "status", 200) == 403, \
            f"{handler.__name__} must require admin (got {getattr(resp, 'status', 200)})"


def test_gate_write_endpoint_allows_api_key(db, mock_request_factory):
    req = mock_request_factory(
        method="POST", path="/api/v1/gate/channels",
        headers={"X-API-Key": "test-secret-key-123"},
        json_data={"title": "قناة API", "chat_type": "channel", "chat_id": -100999})
    req.handler.client_address = ("192.168.1.1", 12345)
    resp = api.create_gate_channel_api(req)
    assert getattr(resp, "status", 200) == 200
    assert resp.body["ok"] is True
    # really created
    assert gate.get_channel(resp.body["channel"]["id"])["title"] == "قناة API"


def test_gate_read_endpoints_open(db, mock_request_factory):
    req = mock_request_factory(method="GET", path="/api/v1/gate/channels")
    resp = api.list_gate_channels_api(req)
    assert resp.status == 200 and resp.body["ok"] is True

    req = mock_request_factory(method="GET", path="/api/v1/gate/profiles")
    assert api.list_gate_profiles_api(req).status == 200

    req = mock_request_factory(method="GET", path="/api/v1/gate/stats")
    assert api.gate_stats_api(req).status == 200

    req = mock_request_factory(method="GET", path="/api/v1/gate/health")
    assert api.gate_health_api(req).status == 200


def test_api_create_channel_writes_audit(db, mock_request_factory):
    req = mock_request_factory(
        method="POST", path="/api/v1/gate/channels",
        headers={"X-API-Key": "test-secret-key-123"},
        json_data={"title": "مراجعة", "chat_type": "channel", "chat_id": -100555})
    req.handler.client_address = ("192.168.1.1", 12345)
    api.create_gate_channel_api(req)

    db_obj = get_db()
    with db_obj._get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM audit_log WHERE action='gate.channel.create'").fetchone()
    assert row is not None, "channel creation must be audited"


def test_api_effective_profile_uses_registry_category(db, mock_request_factory):
    ch = _make_channel(db, 1)
    _make_profile(db, "cat_p", "category", scope_value="Testing",
                  slots=[{"channel_id": ch["id"]}])

    req = mock_request_factory(method="GET", path="/api/v1/gate/profiles/bot/testbot",
                               params={"bot_id": "testbot"})
    resp = api.get_bot_effective_profile_api(req)
    assert resp.status == 200
    assert resp.body["profile"]["scope_type"] == "category"


def test_api_compliance_endpoint(db, mock_request_factory):
    req = mock_request_factory(
        method="POST", path="/api/v1/gate/compliance/check",
        json_data={"text": "ربح مضمون"})
    resp = api.compliance_check_api(req)
    assert resp.status == 200
    assert resp.body["safe"] is False
    assert len(resp.body["warnings"]) > 0


def test_api_export_returns_csv(db, mock_request_factory):
    gate.record_gate_event("testbot", 1, "gate_shown")
    req = mock_request_factory(method="GET", path="/api/v1/gate/stats/export?format=csv")
    resp = api.gate_stats_export_api(req)
    assert resp.status == 200
    assert "text/csv" in resp.content_type
    assert resp.body.startswith("bot_id,user_id_hash,event")


# ═════════════════════════════════════════════════════════════════════════════
# I. Bots side — GateCore (fail-open, cache keys, resolution)
# ═════════════════════════════════════════════════════════════════════════════

def _core(db, bot_id="testbot"):
    core = GateCore(db, bot_id=bot_id)
    return core


def test_get_chat_member_maps_errors(db, monkeypatch):
    core = _core(db)

    # the chat_id passed to get_chat_member doubles as the reply selector
    replies = {
        "ok_member": {"ok": True, "result": {"status": "member"}},
        "err_not_found": {"ok": False, "description": "Bad Request: chat not found"},
        "err_not_admin": {"ok": False, "description": "Bad Request: not an administrator"},
        "err_network": {"ok": False, "error": "timeout"},  # no description!
    }
    monkeypatch.setattr(core, "_call", lambda method, payload: replies[payload["chat_id"]])

    assert core.get_chat_member(1, "ok_member") == "member"
    assert core.get_chat_member(1, "err_not_found") == "error_not_found"
    assert core.get_chat_member(1, "err_not_admin") == "error_not_admin"
    # generic failures (network/timeout) must NOT be reported as 'left'
    # — that would block users and violate the fail-open policy.
    assert core.get_chat_member(1, "err_network") == "error_api"


def test_is_subscribed_fail_open_and_event(db, monkeypatch):
    """Infrastructure errors let the user through AND record failed_open."""
    core = _core(db, bot_id="testbot")
    monkeypatch.setattr(core, "get_chat_member", lambda uid, cid: "error_api")

    assert core.is_subscribed(7, -100123, channel_id=1) is True

    events = _fetch_events("WHERE event='failed_open'")
    assert len(events) == 1
    assert events[0]["bot_id"] == "testbot"
    assert events[0]["user_id_hash"] == bots_user_hash(7)
    # fail-open is never cached → next message re-checks
    assert _fetch_cache(7, 1) is None


def test_is_subscribed_left_caches_not_member(db, monkeypatch):
    """'left' must be cached as 'not_member' (CHECK-compliant)."""
    core = _core(db)
    monkeypatch.setattr(core, "get_chat_member", lambda uid, cid: "left")

    assert core.is_subscribed(7, -100123, channel_id=1) is False
    row = _fetch_cache(7, 1)
    assert row is not None
    assert row["status"] == "not_member"


def test_is_subscribed_cache_key_uses_db_id(db, monkeypatch):
    """Cache rows keyed by sub_channels.id — the raw @username would break the FK."""
    core = _core(db)
    monkeypatch.setattr(core, "get_chat_member", lambda uid, cid: "member")

    ch = _make_channel(db, 3)  # id=N
    core.is_subscribed(7, "@somechannel", channel_id=ch["id"])

    row = _fetch_cache(7, ch["id"])
    assert row is not None, "cache must be keyed by sub_channels.id"
    assert row["status"] == "member"
    # and no FK-violating row with the username was written
    db_obj = get_db()
    with db_obj._get_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) c FROM membership_cache WHERE channel_id NOT IN (SELECT id FROM sub_channels)"
        ).fetchone()["c"]
    assert n == 0


def test_is_subscribed_cache_hit_skips_api(db, monkeypatch):
    core = _core(db)
    calls = []
    monkeypatch.setattr(core, "get_chat_member",
                        lambda uid, cid: calls.append(1) or "member")

    core.is_subscribed(7, -100123, channel_id=1)  # miss → API
    core.is_subscribed(7, -100123, channel_id=1)  # hit → cache
    assert len(calls) == 1


def test_core_effective_profile_resolves_category_from_bot_config(db):
    """Category profiles must apply on the bot side too (not just bot→global)."""
    ch = _make_channel(db, 1)
    # bot_config for testbot has category 'Testing' (fixture)
    _make_profile(db, "cat_p", "category", scope_value="Testing",
                  slots=[{"channel_id": ch["id"]}])

    core = _core(db)
    profile = core.get_effective_profile("testbot")
    assert profile is not None
    assert profile["scope_type"] == "category"
    assert profile["slots"][0]["channel_chat_id"] == ch["chat_id"]


def test_core_effective_profile_bot_beats_category(db):
    _make_profile(db, "cat_p", "category", scope_value="Testing")
    _make_profile(db, "bot_p", "bot", scope_value="testbot")
    core = _core(db)
    assert core.get_effective_profile("testbot")["scope_type"] == "bot"


def test_core_effective_profile_filters_inactive_channels(db):
    ch_live = _make_channel(db, 1)
    ch_dead = _make_channel(db, 2)
    _make_profile(db, "global_p", "global", slots=[
        {"channel_id": ch_live["id"]}, {"channel_id": ch_dead["id"]}])
    gate.delete_channel(ch_dead["id"])

    core = _core(db)
    profile = core.get_effective_profile("testbot")
    ids = [s["channel_id"] for s in profile["slots"]]
    assert ch_dead["id"] not in ids
    assert ch_live["id"] in ids


# ═════════════════════════════════════════════════════════════════════════════
# J. Bots side — GateMiddleware (enforcement behaviour)
# ═════════════════════════════════════════════════════════════════════════════

def _message(user_id=7, lang="ar", chat_id=7):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, language_code=lang),
        chat=SimpleNamespace(id=chat_id),
    )


def _callback(user_id=7, profile_id=1, lang="ar", data=None):
    return SimpleNamespace(
        id="cb-1",
        from_user=SimpleNamespace(id=user_id, language_code=lang),
        message=SimpleNamespace(chat=SimpleNamespace(id=7), message_id=42),
        data=data if data is not None else f"gate_verify:{profile_id}",
    )


def _middleware(db, bot_id="testbot", features=None):
    _ensure_bot_config([bot_id], features=features if features is not None else {"growth_gate": True})
    mw = GateMiddleware(MagicMock(), bot_id, db=db)
    return mw


def test_should_enforce_flag_matrix(db):
    mw = _middleware(db, "flagoff", features={})
    assert mw.should_enforce(1) is False

    mw2 = _middleware(db, "flagon", features={"growth_gate": True})
    assert mw2.should_enforce(1) is True

    # no bot_config row at all → not enforced
    mw3 = GateMiddleware(MagicMock(), "neverconfigured", db=db)
    assert mw3.should_enforce(1) is False


def test_gate_blocks_when_missing_subscription(db, monkeypatch):
    ch = _make_channel(db, 1)
    _make_profile(db, "global_p", "global", slots=[{"channel_id": ch["id"]}])

    mw = _middleware(db)
    monkeypatch.setattr(mw.core, "is_subscribed", lambda *a, **k: False)

    msg = _message()
    assert mw.check_and_show_gate(msg) is True  # blocked
    assert mw.bot.send_message.called

    events = _fetch_events()
    assert [e["event"] for e in events] == ["gate_shown"]
    # hash matches control_center's hashing (shared salt)
    assert events[0]["user_id_hash"] == gate._user_id_hash(7)

    # channel title listed in the gate text
    text = mw.bot.send_message.call_args[0][1]
    assert "قناة 1" in text


def test_gate_passes_when_subscribed(db, monkeypatch):
    ch = _make_channel(db, 1)
    _make_profile(db, "global_p", "global", slots=[{"channel_id": ch["id"]}])

    mw = _middleware(db)
    monkeypatch.setattr(mw.core, "is_subscribed", lambda *a, **k: True)

    assert mw.check_and_show_gate(_message()) is False
    assert not mw.bot.send_message.called
    assert _fetch_events() == []


def test_gate_passes_when_flag_off(db, monkeypatch):
    mw = _middleware(db, "flagoff2", features={"growth_gate": False})
    # no profile at all — should_enforce returns False before profile lookup
    assert mw.check_and_show_gate(_message()) is False


def test_gate_passes_when_no_profile(db, monkeypatch):
    mw = _middleware(db)
    monkeypatch.setattr(mw.core, "get_effective_profile", lambda *a: None)
    assert mw.check_and_show_gate(_message()) is False


def test_gate_message_buttons_all_valid(db, monkeypatch):
    """A slot with neither invite_link nor username must not emit t.me/ button."""
    ch_linked = _make_channel(db, 1, username="@linked")
    ch_private = _make_channel(db, 2, username="")  # private, no invite link
    _make_profile(db, "global_p", "global", slots=[
        {"channel_id": ch_linked["id"]}, {"channel_id": ch_private["id"]}])

    mw = _middleware(db)
    monkeypatch.setattr(mw.core, "is_subscribed", lambda *a, **k: False)
    mw.check_and_show_gate(_message())

    assert mw.bot.send_message.called
    kwargs = mw.bot.send_message.call_args[1]
    markup = kwargs["reply_markup"]
    urls = []
    for row in markup.keyboard:
        for btn in row:
            url = btn.get("url") if isinstance(btn, dict) else btn.url
            if url:
                urls.append(url)
    # only the linked channel + no broken bare t.me/ links
    assert urls == ["https://t.me/linked"]
    # the private channel is still listed in the text so the user knows
    text = mw.bot.send_message.call_args[0][1]
    assert "قناة 2" in text


def test_verify_callback_success_taxonomy(db, monkeypatch):
    ch = _make_channel(db, 1)
    profile = _make_profile(db, "global_p", "global", slots=[{"channel_id": ch["id"]}])

    mw = _middleware(db)
    monkeypatch.setattr(mw.core, "is_subscribed", lambda *a, **k: True)

    mw.handle_verify_callback(_callback(profile_id=profile["id"]))

    events = [e["event"] for e in _fetch_events()]
    assert "verify_clicked" in events   # the attempt
    assert "verified" in events         # the outcome
    assert mw.bot.answer_callback_query.called
    assert mw.bot.edit_message_text.called


def test_verify_callback_failure_records_only_valid_taxonomy(db, monkeypatch):
    ch = _make_channel(db, 1)
    profile = _make_profile(db, "global_p", "global", slots=[{"channel_id": ch["id"]}])

    mw = _middleware(db)
    monkeypatch.setattr(mw.core, "is_subscribed", lambda *a, **k: False)

    mw.handle_verify_callback(_callback(profile_id=profile["id"]))

    events = {e["event"] for e in _fetch_events()}
    assert "verify_clicked" in events
    assert "verified" not in events
    # every stored event must be a schema-valid value (CHECK constraint)
    assert events.issubset(set(gate.EVENT_TYPES))
    assert mw.bot.answer_callback_query.called
    assert not mw.bot.edit_message_text.called


def test_verify_callback_malformed_data_answers_safe(db):
    mw = _middleware(db)
    mw.handle_verify_callback(_callback(data="gate_verify:not-a-number"))
    assert mw.bot.answer_callback_query.called
    # no crash, no event
    assert _fetch_events() == []


def test_middleware_hash_matches_control_center(db, monkeypatch):
    ch = _make_channel(db, 1)
    _make_profile(db, "global_p", "global", slots=[{"channel_id": ch["id"]}])
    mw = _middleware(db)
    monkeypatch.setattr(mw.core, "is_subscribed", lambda *a, **k: False)

    mw.check_and_show_gate(_message(user_id=31337))

    events = _fetch_events()
    assert events[0]["user_id_hash"] == gate._user_id_hash(31337)
    assert events[0]["user_id_hash"] == bots_user_hash(31337)
