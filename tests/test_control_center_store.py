# -*- coding: utf-8 -*-
"""
tests/test_control_center_store.py — Store Manager hardening tests
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from control_center import store, api
from control_center.auth import authorize
from control_center import config
from control_center.db import get_db
from control_center.migrations import ensure_ready


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Isolate test environment: separate DB, registry, webroot."""
    # Isolate database
    test_db = tmp_path / "test_boda_bot.db"
    monkeypatch.setenv("BODA_DB_PATH", str(test_db))
    monkeypatch.setattr(config, "db_path", lambda: str(test_db))

    # Isolate registry
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

    # Isolate webroot
    test_webroot = tmp_path / "webroot"
    test_webroot.mkdir()
    (test_webroot / "assets").mkdir()
    (test_webroot / "assets" / "store").mkdir(parents=True)

    # Reset BodaDatabase singleton to pick up new BODA_DB_PATH
    try:
        from database import BodaDatabase
        BodaDatabase.reset_instance()
    except ImportError:
        pass

    yield

    # Cleanup - close connections before unlink
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


def _ensure_bot_config(bot_ids):
    """Insert bot_config rows required by the store_items FK constraint."""
    db_obj = get_db()
    if not db_obj:
        return
    try:
        with db_obj._get_conn() as conn:
            for bot_id in bot_ids:
                conn.execute("""
                    INSERT OR IGNORE INTO bot_config
                    (bot_id, display_name, category, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, 1, datetime('now'), datetime('now'))
                """, (bot_id, bot_id.replace("_", " ").title(), "Testing"))
    except Exception as exc:
        print(f"bot_config setup warning: {exc}")


@pytest.fixture
def db():
    """Initialize DB and return connection."""
    ensure_ready()
    _ensure_bot_config(["testbot", "testbot2", "testbot3", "testbot4"])
    return get_db()


@pytest.fixture
def api_key(monkeypatch):
    """Set API server key for auth."""
    monkeypatch.setenv("API_SERVER_KEY", "test-secret-key-123")


@pytest.fixture
def mock_request_factory(api_key):
    """Create mock request objects."""
    class MockRequest:
        def __init__(self, method="GET", path="/", headers=None, body=b"", query=None, json_data=None):
            self.method = method
            self.path = path
            self.headers = headers or {}
            self._body = body
            self._json_data = json_data
            self.query_params = query or {}
            # Simulate handler for client_ip
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
            # Extract from path like /api/v1/store/123
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


# ── CRUD Tests ──────────────────────────────────────────────────────────────

def test_create_store_item(db):
    """Create a store item and verify it exists."""
    res = store.create_store_item(
        bot_id="testbot",
        title_ar="اختبار",
        title_en="Test",
        short_desc_ar="وصف مختصر",
        short_desc_en="Short desc",
        category="Testing",
        deep_link="https://t.me/TestBot?start=test",
    )
    assert res["ok"] is True
    item = res["item"]
    assert item["bot_id"] == "testbot"
    assert item["title_ar"] == "اختبار"
    assert item["status"] == "live"
    assert item["views"] == 0
    assert item["opens"] == 0
    assert item["clicks"] == 0

    # Verify retrieval
    fetched = store.get_store_item(item["id"])
    assert fetched["bot_id"] == "testbot"
    assert fetched["title_ar"] == "اختبار"


def test_create_duplicate_bot_fails(db):
    """Creating a second store item for same bot_id should fail."""
    store.create_store_item(bot_id="testbot", title_ar="First", deep_link="https://t.me/TestBot")
    res = store.create_store_item(bot_id="testbot", title_ar="Second", deep_link="https://t.me/TestBot")
    assert res["ok"] is False
    assert "already exists" in res["error"]


def test_update_store_item(db):
    """Update store item fields."""
    create_res = store.create_store_item(bot_id="testbot", title_ar="Original", deep_link="https://t.me/TestBot")
    item_id = create_res["item"]["id"]

    res = store.update_store_item(item_id, title_ar="محدث", category="Updated", display_order=5)
    assert res["ok"] is True
    assert res["updated"] is True

    fetched = store.get_store_item(item_id)
    assert fetched["title_ar"] == "محدث"
    assert fetched["category"] == "Updated"
    assert fetched["display_order"] == 5


def test_delete_store_item(db):
    """Delete store item and verify it's gone."""
    create_res = store.create_store_item(bot_id="testbot", title_ar="ToDelete", deep_link="https://t.me/TestBot")
    item_id = create_res["item"]["id"]

    res = store.delete_store_item(item_id)
    assert res["ok"] is True

    fetched = store.get_store_item(item_id)
    assert fetched == {}


def test_reorder_store_items(db):
    """Reorder items by providing new display_order."""
    # Add testbot1/testbot2 to registry (testbot already in fixture)
    registry_path = config.ROOT_DIR / "bots_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for i in (1, 2):
        bot_id = f"testbot{i}"
        if not any(b["id"] == bot_id for b in registry):
            registry.append({
                "id": bot_id,
                "name": f"Bot {i}",
                "description": f"Test bot {i}",
                "short_desc": f"Short {i}",
                "emoji": "🤖",
                "url": f"https://t.me/TestBot{i}",
                "username": f"@TestBot{i}",
                "tag": "Testing",
                "hidden": False,
                "file": f"bot_{bot_id}.py",
                "category": "Testing",
            })
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    _ensure_bot_config(["testbot", "testbot1", "testbot2"])

    ids = []
    for i, bot_id in enumerate(["testbot", "testbot1", "testbot2"]):
        res = store.create_store_item(
            bot_id=bot_id,
            title_ar=f"Item {i}",
            deep_link="https://t.me/TestBot",
            display_order=i,
        )
        assert res["ok"], f"Failed to create item {i}: {res.get('error')}"
        ids.append(res["item"]["id"])

    # Reverse order
    res = store.reorder_store_items(list(reversed(ids)))
    assert res["ok"] is True

    # Verify order
    for idx, item_id in enumerate(reversed(ids)):
        item = store.get_store_item(item_id)
        assert item["display_order"] == idx, f"Item {item_id} has order {item['display_order']}, expected {idx}"


# ── Catalog Generation Tests ────────────────────────────────────────────────

def test_catalog_excludes_non_live(db):
    """Catalog should mark non-live items as hidden."""
    # Ensure all four bots exist in the registry
    registry_path = config.ROOT_DIR / "bots_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for i, bot_id in enumerate(["testbot", "testbot2", "testbot3", "testbot4"]):
        if not any(b["id"] == bot_id for b in registry):
            registry.append({
                "id": bot_id,
                "name": f"Bot {i}",
                "description": f"Test bot {i}",
                "short_desc": f"Short {i}",
                "emoji": "🤖",
                "url": f"https://t.me/TestBot{i}",
                "username": f"@TestBot{i}",
                "tag": "Testing",
                "hidden": False,
                "file": f"bot_{bot_id}.py",
                "category": "Testing",
            })
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    _ensure_bot_config(["testbot", "testbot2", "testbot3", "testbot4"])

    # Create items with every status
    created = [
        store.create_store_item(bot_id="testbot", title_ar="Live", deep_link="https://t.me/TestBot", status="live"),
        store.create_store_item(bot_id="testbot2", title_ar="Hidden", deep_link="https://t.me/TestBot2", status="hidden"),
        store.create_store_item(bot_id="testbot3", title_ar="Draft", deep_link="https://t.me/TestBot3", status="draft"),
        store.create_store_item(bot_id="testbot4", title_ar="Coming Soon", deep_link="https://t.me/TestBot4", status="coming_soon"),
    ]
    for i, res in enumerate(created):
        assert res["ok"], f"Create #{i} failed: {res.get('error')}"

    catalog = store.generate_catalog()

    # Should have all 4 items
    assert len(catalog) == 4, f"Expected 4 items, got {len(catalog)}: {[c.get('name', '?') for c in catalog]}"

    # Live item should be visible
    live_item = next(c for c in catalog if c["name"] == "Live")
    assert live_item["hidden"] is False, "Live item should not be hidden"

    # Non-live items should be hidden
    for name in ["Hidden", "Draft", "Coming Soon"]:
        item = next(c for c in catalog if c["name"] == name)
        assert item["hidden"] is True, f"Item {name} should be hidden"


# ── Ad Marker Preservation Tests ────────────────────────────────────────────

def test_ad_marker_idempotent_injection(tmp_path):
    """Regenerating pages with injector should preserve marker blocks without duplicates.

    Injector contract: blocks with the SAME slot are replaced in place;
    blocks in DIFFERENT slots coexist.
    """
    from control_center.ads.injector import inject_markers, list_blocks

    # Create test HTML with existing markers
    test_html = """<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
    <!-- AD:BEGIN slot=head id=ad1 -->
    <script src="https://ads.example.com/ad1.js"></script>
    <!-- AD:END slot=head -->
</head>
<body>
    <div>Content</div>
    <!-- AD:BEGIN slot=banner_bottom id=ad2 -->
    <div class="ad-banner">Ad 2</div>
    <!-- AD:END slot=banner_bottom -->
</body>
</html>"""

    # First injection - add a new marker in a different slot
    blocks1 = [("body_end", "ad3_new", "<script src='new.js'></script>")]
    result1 = inject_markers(test_html, blocks1)

    # Verify original markers preserved + new one added in body_end slot
    blocks_after = list_blocks(result1)
    slot_ids = {(b["slot"], b["ad_id"]) for b in blocks_after}
    assert ("head", "ad1") in slot_ids  # Original preserved
    assert ("banner_bottom", "ad2") in slot_ids  # Original preserved
    assert ("body_end", "ad3_new") in slot_ids  # New added in different slot

    # Second injection with same slot (head) - should REPLACE the existing head marker, not duplicate
    blocks2 = [("head", "ad1_new", "<script src='updated.js'></script>")]
    result2 = inject_markers(result1, blocks2)

    blocks_after2 = list_blocks(result2)
    head_blocks = [b for b in blocks_after2 if b["slot"] == "head"]
    assert len(head_blocks) == 1, f"Should have exactly 1 head marker, got {len(head_blocks)}"
    assert head_blocks[0]["ad_id"] == "ad1_new", "Should have the new ad_id"
    # Verify head content was updated
    assert "updated.js" in result2
    assert "ad1.js" not in result2  # Original head content replaced

    # Other slots must be untouched: banner_bottom preserved, body_end keeps new.js
    final_slots = {(b["slot"], b["ad_id"]) for b in blocks_after2}
    assert ("banner_bottom", "ad2") in final_slots
    assert ("body_end", "ad3_new") in final_slots
    assert "new.js" in result2  # body_end content coexists (different slot)

    # Third injection: repeating the SAME block must not duplicate it (idempotency)
    result3 = inject_markers(result2, blocks2)
    blocks_after3 = list_blocks(result3)
    assert len([b for b in blocks_after3 if b["slot"] == "head"]) == 1, "Re-injecting same block must stay idempotent"


def test_build_preserves_ad_markers(tmp_path, monkeypatch):
    """Build process should preserve ad markers in generated pages."""
    from tools.build_mini_apps import render_app

    # Create a simple app with ad markers
    app = {"id": "testapp", "emoji": "🧪", "name": "Test", "short_desc": "Test", "tag": "Test"}

    ads_cfg = {"banner": None, "sponsor": None, "every": 3, "monetag_script": ""}

    html = render_app(app, ads_cfg, "", "TestBot")

    # Inject a marker
    from control_center.ads.injector import inject_markers
    markers = [("body_end", "test_ad", '<div class="preserved-ad">Preserved</div>')]
    html_with_markers = inject_markers(html, markers)

    # Save to temp location
    test_dir = tmp_path / "webroot" / "testapp"
    test_dir.mkdir(parents=True)
    (test_dir / "index.html").write_text(html_with_markers, encoding="utf-8")

    # Simulate rebuild - the build process would call inject_markers with preserved markers
    from control_center.ads.injector import list_blocks
    preserved = list_blocks(html_with_markers)

    # Rebuild: render new HTML
    html_new = render_app(app, ads_cfg, "", "TestBot")

    # Re-inject preserved markers
    blocks = [(b["slot"], b["ad_id"], "PRESERVED_CONTENT") for b in preserved]
    html_rebuilt = inject_markers(html_new, blocks)

    # Verify marker was preserved in rebuilt HTML
    assert "PRESERVED_CONTENT" in html_rebuilt or "preserved-ad" in html_rebuilt


# ── Security / Auth Tests ──────────────────────────────────────────────────

def test_api_endpoints_require_admin_for_writes(mock_request_factory):
    """Write endpoints should require admin role."""
    from control_center.auth import authorize

    # Mock request with API key from non-localhost (should allow admin access)
    req = mock_request_factory(method="POST", path="/api/v1/store", headers={"X-API-Key": "test-secret-key-123"}, json_data={})
    req.handler.client_address = ("192.168.1.1", 12345)  # Non-local IP

    # Create requires admin - API key from non-local should grant access
    allowed, payload = authorize(req, roles=("admin",))
    assert allowed is True, f"API key should allow admin access from non-localhost, got: {allowed}, {payload}"

    # Request without API key from non-localhost should be denied
    req_no_auth = mock_request_factory(method="POST", path="/api/v1/store", headers={}, json_data={})
    req_no_auth.handler.client_address = ("192.168.1.1", 12345)  # Non-local IP
    allowed, payload = authorize(req_no_auth, roles=("admin",))
    assert allowed is False, "Should be denied without auth from non-localhost"
    assert payload.get("status") == 403


def test_api_read_endpoints_public(mock_request_factory):
    """Read endpoints should allow public access."""
    # No auth required for reads
    req = mock_request_factory(method="GET", path="/api/v1/store", headers={})

    # Just verify authorize doesn't block with empty roles
    from control_center.auth import authorize
    allowed, _ = authorize(req, roles=())
    assert allowed is True, "Public read should not require auth"


def test_export_requires_admin(mock_request_factory):
    """Store export includes internal stats — must be admin-only."""
    from control_center.api import export_store_api

    # No API key from non-localhost → denied
    req = mock_request_factory(method="GET", path="/api/v1/store/export?format=json", headers={})
    req.handler.client_address = ("192.168.1.1", 12345)
    resp = export_store_api(req)
    assert getattr(resp, "status", 200) == 403, "Export without auth must be denied"

    # With valid API key → allowed
    req_ok = mock_request_factory(
        method="GET", path="/api/v1/store/export?format=json",
        headers={"X-API-Key": "test-secret-key-123"},
    )
    req_ok.handler.client_address = ("192.168.1.1", 12345)
    resp_ok = export_store_api(req_ok)
    assert getattr(resp_ok, "status", 200) == 200


def test_image_upload_rejects_svg(mock_request_factory):
    """SVG uploads must be rejected: SVG can embed <script> (XSS vector)."""
    from control_center.api import upload_store_image_api

    boundary = "----testboundary"
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"evil.svg\"\r\n"
        f"Content-Type: image/svg+xml\r\n\r\n"
        f"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    req = mock_request_factory(
        method="POST", path="/api/v1/store/upload-image",
        headers={"X-API-Key": "test-secret-key-123",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
        body=body,
    )
    req.handler.client_address = ("192.168.1.1", 12345)

    resp = upload_store_image_api(req)
    assert getattr(resp, "status", 200) == 400, "SVG upload must be rejected"


def test_image_upload_optimizes_png(mock_request_factory):
    """Large PNG uploads are transcoded to WebP and downscaled to ≤512px."""
    from io import BytesIO
    from control_center.api import upload_store_image_api
    from control_center import config as cc_config

    # Build a 1200x800 red PNG in memory
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (1200, 800), (200, 30, 30)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    boundary = "----testboundary"
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"big.png\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + png_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = mock_request_factory(
        method="POST", path="/api/v1/store/upload-image",
        headers={"X-API-Key": "test-secret-key-123",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
        body=body,
    )
    req.handler.client_address = ("192.168.1.1", 12345)

    resp = upload_store_image_api(req)
    assert getattr(resp, "status", 200) == 200, "Valid PNG upload should succeed"

    data = resp.body if isinstance(resp.body, dict) else json.loads(resp.body)
    assert data["ok"] is True
    assert data["filename"].endswith(".webp"), f"Expected WebP transcode, got {data['filename']}"

    saved = cc_config.ROOT_DIR / "webroot" / "assets" / "store" / data["filename"]
    assert saved.exists()
    with Image.open(saved) as im:
        assert max(im.size) <= 512, f"Image not downscaled: {im.size}"


# ── Validation & Sanitization Tests ────────────────────────────────────────

def test_url_scheme_allowlist(db):
    """Only https, tg, mailto schemes should be allowed in URLs."""
    # Valid https
    res = store.create_store_item(bot_id="testbot", title_ar="Valid", deep_link="https://t.me/TestBot")
    assert res["ok"] is True

    # Update with tg scheme
    res = store.update_store_item(res["item"]["id"], deep_link="tg://resolve?domain=TestBot")
    assert res["ok"] is True

    # mailto
    res = store.update_store_item(res["item"]["id"], deep_link="mailto:test@example.com")
    assert res["ok"] is True

    # Dangerous schemes rejected
    res = store.update_store_item(res["item"]["id"], deep_link="javascript:alert(1)")
    assert res["ok"] is False
    assert "scheme" in res["error"].lower() or "url" in res["error"].lower()

    res2 = store.create_store_item(bot_id="testbot2", title_ar="Bad", deep_link="http://insecure.example.com")
    assert res2["ok"] is False, "http:// (not in allowlist) should be rejected"


def test_field_length_limits(db):
    """Fields should be truncated to configured limits."""
    long_title = "أ" * 200  # 200 chars Arabic (> MAX_TITLE_LENGTH=100)
    res = store.create_store_item(bot_id="testbot", title_ar=long_title, deep_link="https://t.me/TestBot")
    assert res["ok"] is True
    assert len(res["item"]["title_ar"]) <= store.MAX_TITLE_LENGTH


def test_script_injection_blocked(db):
    """Script tags in descriptions should be sanitized."""
    malicious = "Test <script>alert('xss')</script> description"
    res = store.create_store_item(bot_id="testbot", title_ar="Test", short_desc_ar=malicious, deep_link="https://t.me/TestBot")
    assert res["ok"] is True  # Should accept but sanitize
    # If accepted, verify sanitization
    item = store.get_store_item(res["item"]["id"])
    assert "<script>" not in item["short_desc_ar"], f"Script tag not sanitized: {item['short_desc_ar']}"
    # Also test with update
    res2 = store.update_store_item(item["id"], long_desc_ar="<script>evil()</script>")
    assert res2["ok"] is True
    item2 = store.get_store_item(item["id"])
    assert "<script>" not in item2["long_desc_ar"], f"Script tag not sanitized on update: {item2['long_desc_ar']}"


# ── Stats Tests ────────────────────────────────────────────────────────────

def test_stats_show_zero_when_no_data(db):
    """Stats should be 0 when no tracking data exists."""
    # No stats endpoints should fabricate numbers
    stats = store.get_store_stats()
    assert stats["total_views"] == 0
    assert stats["total_opens"] == 0
    assert stats["total_clicks"] == 0
    assert stats["total"] == 0


# ── Full Publish Safety Tests ──────────────────────────────────────────────

def test_full_publish_preview_returns_diff(db, monkeypatch):
    """full-publish-preview should report changes WITHOUT committing anything."""
    # One live item so the catalog has content
    res = store.create_store_item(bot_id="testbot", title_ar="Preview", deep_link="https://t.me/TestBot")
    assert res["ok"]

    # Mock the heavy build step; preview logic itself is what we verify
    monkeypatch.setattr(store, "build_store_pages", lambda: {"ok": True, "stdout": "mock build"})

    # init a throwaway git repo so git status/diff work in isolation
    subprocess.run(["git", "init", "-q"], cwd=str(config.ROOT_DIR), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(config.ROOT_DIR), capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(config.ROOT_DIR), capture_output=True)

    result = store.full_publish_preview()

    assert result["ok"] is True, f"preview failed: {result}"
    assert "changed_files" in result
    assert "diff" in result
    # The freshly written catalog must appear among the changes
    assert any("catalog.json" in f for f in result["changed_files"]), result["changed_files"]

    # SAFETY: nothing must have been committed by a *preview*
    log = subprocess.run(["git", "log", "--oneline"], cwd=str(config.ROOT_DIR),
                         capture_output=True, text=True)
    assert log.stdout.strip() == "", f"Preview must not commit; log: {log.stdout!r}"


# ── Delete Safety Tests ────────────────────────────────────────────────────

def test_delete_creates_backup(db):
    """Deleting an item should create a backup."""
    res = store.create_store_item(bot_id="testbot", title_ar="Backup Me", deep_link="https://t.me/TestBot")
    assert res["ok"]
    item_id = res["item"]["id"]

    del_res = store.delete_store_item(item_id)
    assert del_res["ok"] is True

    # A backup file must exist under ROOT_DIR/Backups/store_items (ROOT_DIR is tmp_path)
    backup_dir = config.ROOT_DIR / "Backups" / "store_items"
    backups = list(backup_dir.glob(f"store_item_{item_id}_*.json"))
    assert backups, f"No backup created in {backup_dir}"

    saved = json.loads(backups[0].read_text(encoding="utf-8"))
    assert saved["deleted_item"]["bot_id"] == "testbot"
    assert saved["deleted_item"]["title_ar"] == "Backup Me"
    assert "deleted_at" in saved


# ── Import/Export Tests ────────────────────────────────────────────────────

def test_export_json_format(db):
    """Export should produce valid JSON with all fields."""
    store.create_store_item(bot_id="testbot", title_ar="Export Test", deep_link="https://t.me/TestBot")

    items = store.list_store_items()
    assert len(items) >= 1

    # Check structure
    item = items[0]
    assert "id" in item
    assert "bot_id" in item
    assert "title_ar" in item
    assert "deep_link" in item
    assert "tags" in item
    assert "badges" in item


def test_import_upserts_by_bot_id(db):
    """Import should update existing items by bot_id."""
    # Create initial
    res1 = store.create_store_item(bot_id="testbot", title_ar="Original", deep_link="https://t.me/TestBot")
    assert res1["ok"]
    item_id = res1["item"]["id"]

    # Upsert via update path (import by bot_id resolves to the same item)
    existing = store.get_store_item_by_bot("testbot")
    assert existing and existing["id"] == item_id

    res2 = store.update_store_item(existing["id"], title_ar="Updated via Import")
    assert res2["ok"]

    after = store.get_store_item_by_bot("testbot")
    assert after["title_ar"] == "Updated via Import"
    # Still exactly one item for this bot
    same = [i for i in store.list_store_items() if i["bot_id"] == "testbot"]
    assert len(same) == 1


# ── Integration: End-to-End ────────────────────────────────────────────────

def test_store_item_lifecycle_e2e(db):
    """Full lifecycle: create -> read -> update -> reorder -> delete."""
    # Create
    res = store.create_store_item(
        bot_id="testbot",
        title_ar="E2E Test",
        title_en="E2E",
        short_desc_ar="E2E Desc",
        category="E2E",
        deep_link="https://t.me/TestBot",
        display_order=10,
    )
    assert res["ok"]
    item_id = res["item"]["id"]

    # Read
    item = store.get_store_item(item_id)
    assert item["title_ar"] == "E2E Test"

    # Update
    res = store.update_store_item(item_id, title_ar="E2E Updated", category="E2E Updated")
    assert res["ok"]
    item = store.get_store_item(item_id)
    assert item["title_ar"] == "E2E Updated"

    # Reorder
    res = store.reorder_store_items([item_id])
    assert res["ok"]

    # Delete
    res = store.delete_store_item(item_id)
    assert res["ok"]

    # Verify gone
    item = store.get_store_item(item_id)
    assert item == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
