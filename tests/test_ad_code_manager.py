"""tests/test_ad_code_manager.py — Phase A1 tests for the Ad Code Manager."""

import os
import tempfile

import pytest

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401

from control_center import migrations
from control_center.db import connect, reset_db
from control_center.ads import (
    Ad, AdLibrary, VALID_FORMATS, VALID_SLOTS, VALID_SCOPES,
    validate_snippet, ValidationResult,
    apply_injection, remove_markers, dry_run, rollback_file,
    make_block, list_blocks, list_backups,
    resolve_ad_for_bot, resolve_ads_for_bot, effective_ad, effective_map,
)


@pytest.fixture()
def cc_db(tmp_path, monkeypatch):
    db_file = tmp_path / "acm.db"
    monkeypatch.setenv("BODA_DB_PATH", str(db_file))
    reset_db()
    conn = connect(str(db_file))
    migrations.apply_migrations(conn, backup=False)
    conn.close()
    reset_db()
    yield str(db_file)
    reset_db()


# ── Migration ────────────────────────────────────────────────────────────────

def test_migration_002_creates_tables(cc_db):
    conn = connect(cc_db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "ads" in tables
    assert "ad_assignments" in tables
    assert "ad_events" in tables


def test_migration_002_rollback(cc_db):
    conn = connect(cc_db)
    # Migration 002 created the ads tables, but the catalogue has grown since
    # (gate foundation, store manager, ...). Rolling back "1 step" only undoes
    # the newest migration, so compute how many steps are needed to actually
    # undo version 2 and verify its down script drops the ads tables.
    current = migrations.current_version(conn)
    migrations.rollback(conn, steps=max(1, current - 1))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "ads" not in tables
    assert "ad_assignments" not in tables
    assert "ad_events" not in tables


# ── Model CRUD ───────────────────────────────────────────────────────────────

def test_create_and_get_ad(cc_db):
    lib = AdLibrary()
    ad = Ad(name="Test", format="custom", slot="body_end", snippet="<div>hi</div>")
    lib.create(ad)
    got = lib.get(ad.ad_id)
    assert got is not None
    assert got.name == "Test"
    assert got.snippet == "<div>hi</div>"


def test_list_ads(cc_db):
    lib = AdLibrary()
    lib.create(Ad(name="A", slot="head", snippet="<script></script>"))
    lib.create(Ad(name="B", slot="body_end", snippet="<div></div>"))
    assert len(lib.list()) == 2
    assert len(lib.list(slot="head")) == 1


def test_update_ad(cc_db):
    lib = AdLibrary()
    ad = Ad(name="Old", slot="body_end", snippet="<div></div>")
    lib.create(ad)
    updated = lib.update(ad.ad_id, name="New", enabled=False)
    assert updated.name == "New"
    assert updated.enabled is False
    got = lib.get(ad.ad_id)
    assert got.name == "New"
    assert got.enabled is False


def test_delete_ad(cc_db):
    lib = AdLibrary()
    ad = Ad(name="Del", slot="body_end", snippet="<div></div>")
    lib.create(ad)
    assert lib.delete(ad.ad_id) is True
    assert lib.get(ad.ad_id) is None
    assert lib.delete(ad.ad_id) is False


def test_assign_and_resolve(cc_db):
    lib = AdLibrary()
    ad = Ad(name="Global Ad", slot="body_end", snippet="<div>g</div>")
    lib.create(ad)
    lib.assign(ad.ad_id, "global")
    resolved = resolve_ad_for_bot("currency", "body_end", library=lib)
    assert resolved is not None
    assert resolved.ad_id == ad.ad_id


def test_bot_overrides_global(cc_db):
    lib = AdLibrary()
    g = Ad(name="Global", slot="body_end", snippet="<div>g</div>")
    b = Ad(name="Bot-specific", slot="body_end", snippet="<div>b</div>")
    lib.create(g)
    lib.create(b)
    lib.assign(g.ad_id, "global")
    lib.assign(b.ad_id, "bot", "currency")
    resolved = resolve_ad_for_bot("currency", "body_end", library=lib)
    assert resolved.ad_id == b.ad_id
    # another bot gets global
    resolved2 = resolve_ad_for_bot("qrgen", "body_end", library=lib)
    assert resolved2.ad_id == g.ad_id


def test_unassign(cc_db):
    lib = AdLibrary()
    ad = Ad(name="A", slot="body_end", snippet="<div></div>")
    lib.create(ad)
    lib.assign(ad.ad_id, "global")
    assert len(lib.assignments_for(ad.ad_id)) == 1
    lib.unassign(ad.ad_id, "global")
    assert len(lib.assignments_for(ad.ad_id)) == 0


def test_effective_map(cc_db):
    lib = AdLibrary()
    ad = Ad(name="A", slot="head", snippet="<script></script>")
    lib.create(ad)
    lib.assign(ad.ad_id, "global")
    emap = effective_map("currency", library=lib)
    assert set(emap.keys()) == set(VALID_SLOTS)
    assert emap["head"]["ad_id"] == ad.ad_id
    assert emap["body_end"]["ad_id"] is None


def test_record_event_and_stats(cc_db):
    lib = AdLibrary()
    ad = Ad(name="A", slot="body_end", snippet="<div></div>")
    lib.create(ad)
    lib.record_event(ad.ad_id, "currency", "view")
    lib.record_event(ad.ad_id, "currency", "view")
    lib.record_event(ad.ad_id, "currency", "click")
    stats = lib.stats(ad.ad_id)
    assert stats["impressions"] == 2
    assert stats["clicks"] == 1
    assert stats["ctr"] == 50.0


# ── Validator ────────────────────────────────────────────────────────────────

def test_validator_empty():
    vr = validate_snippet("")
    assert vr.ok is False
    assert "empty" in vr.errors[0]


def test_validator_size_limit():
    vr = validate_snippet("x" * 100, size_limit=50)
    assert vr.ok is False
    assert "too large" in vr.errors[0]


def test_validator_token_rejected():
    vr = validate_snippet("token=1234567890:AAF-fakeTokenValue_1234567890abcdef")
    assert vr.ok is False
    assert "token" in vr.errors[0].lower()


def test_validator_balanced_tags():
    vr = validate_snippet("<div><span>hi</span></div>")
    assert not any("unbalanced" in w for w in vr.warnings)
    vr2 = validate_snippet("<div><span>hi</div>")
    assert any("unbalanced" in w for w in vr2.warnings)


def test_validator_dangerous_patterns():
    vr = validate_snippet('<script>eval("x")</script>')
    assert any("eval" in w for w in vr.warnings)
    vr2 = validate_snippet('<script>document.write("http://evil.com")</script>')
    assert any("document.write" in w for w in vr2.warnings)


def test_validator_domain_allowlist():
    vr = validate_snippet('<script src="https://evil.com/ad.js"></script>',
                          allowed_domains=["good.com"])
    assert any("allow-list" in w for w in vr.warnings)
    vr2 = validate_snippet('<script src="https://good.com/ad.js"></script>',
                           allowed_domains=["good.com"])
    assert not any("allow-list" in w for w in vr2.warnings)


def test_validator_empty_allowlist_warns():
    vr = validate_snippet('<script src="https://cdn.example.com/ad.js"></script>',
                          allowed_domains=[])
    assert any("allow-list is empty" in w for w in vr.warnings)


# ── Injector ─────────────────────────────────────────────────────────────────

def test_inject_insert():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        f.write("<html><head></head><body></body></html>")
        path = f.name
    try:
        result = apply_injection(path, [("body_end", "ad1", "<div>hi</div>")])
        assert result["ok"] is True
        assert result["changed"] is True
        content = open(path, encoding="utf-8").read()
        assert "AD:BEGIN slot=body_end id=ad1" in content
        assert "AD:END slot=body_end" in content
    finally:
        os.unlink(path)


def test_inject_idempotent():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        f.write("<html><head></head><body></body></html>")
        path = f.name
    try:
        apply_injection(path, [("body_end", "ad1", "<div>hi</div>")])
        r2 = apply_injection(path, [("body_end", "ad1", "<div>hi</div>")])
        assert r2["ok"] is True
        assert r2["changed"] is False
    finally:
        os.unlink(path)


def test_inject_update():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        f.write("<html><head></head><body></body></html>")
        path = f.name
    try:
        apply_injection(path, [("body_end", "ad1", "<div>v1</div>")])
        apply_injection(path, [("body_end", "ad1", "<div>v2</div>")])
        content = open(path, encoding="utf-8").read()
        assert "v2" in content
        assert "v1" not in content
        assert content.count("AD:BEGIN slot=body_end") == 1
    finally:
        os.unlink(path)


def test_inject_remove():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        f.write("<html><head></head><body></body></html>")
        path = f.name
    try:
        apply_injection(path, [("body_end", "ad1", "<div>hi</div>")])
        # Remove by passing empty blocks + remove_slots
        apply_injection(path, [], remove_slots=["body_end"])
        content = open(path, encoding="utf-8").read()
        assert "AD:BEGIN" not in content
    finally:
        os.unlink(path)


def test_inject_multiple_slots():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        f.write("<html><head></head><body></body></html>")
        path = f.name
    try:
        apply_injection(path, [
            ("head", "ad_head", "<script>console.log(1)</script>"),
            ("body_end", "ad_body", "<div>body</div>"),
        ])
        content = open(path, encoding="utf-8").read()
        assert "AD:BEGIN slot=head" in content
        assert "AD:BEGIN slot=body_end" in content
    finally:
        os.unlink(path)


def test_inject_backup_created():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        f.write("<html><head></head><body></body></html>")
        path = f.name
    try:
        result = apply_injection(path, [("body_end", "ad1", "<div>hi</div>")])
        assert result["backup"] != ""
        assert os.path.exists(result["backup"])
        backups = list_backups(path)
        assert len(backups) >= 1
    finally:
        os.unlink(path)


def test_inject_rollback():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        f.write("<html><head></head><body>original</body></html>")
        path = f.name
    try:
        apply_injection(path, [("body_end", "ad1", "<div>hi</div>")])
        rb = rollback_file(path)
        assert rb["ok"] is True
        content = open(path, encoding="utf-8").read()
        assert "original" in content
        assert "AD:BEGIN" not in content
    finally:
        os.unlink(path)


def test_inject_dry_run():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        f.write("<html><head></head><body></body></html>")
        path = f.name
    try:
        diff = dry_run(path, "<html><head></head><body>changed</body></html>")
        assert "---" in diff
        assert "+++" in diff
    finally:
        os.unlink(path)


def test_inject_invalid_snippet_aborts():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8") as f:
        original = "<html><head></head><body></body></html>"
        f.write(original)
        path = f.name
    try:
        result = apply_injection(path, [("body_end", "ad1", "")])
        assert result["ok"] is False
        content = open(path, encoding="utf-8").read()
        assert content == original
    finally:
        os.unlink(path)


def test_inject_missing_file():
    result = apply_injection("/nonexistent/file.html", [("body_end", "ad1", "<div></div>")])
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_inject_preserves_encoding():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False,
                                    encoding="utf-8", newline="\n") as f:
        f.write("<html><head></head><body>café</body></html>")
        path = f.name
    try:
        apply_injection(path, [("body_end", "ad1", "<div>é</div>")])
        content = open(path, encoding="utf-8").read()
        assert "café" in content
        assert "é" in content
    finally:
        os.unlink(path)


# ── Generator preserves ads ──────────────────────────────────────────────────

def test_generator_preserves_injected_ads():
    """Running build_mini_apps.py must not destroy injected ad markers."""
    import subprocess, sys
    from pathlib import Path

    root = Path(__file__).parent.parent
    page = root / "webroot" / "currency" / "index.html"
    # Inject a marker
    apply_injection(str(page), [("body_end", "gen_test_ad", "<div>gen ad</div>")])
    assert "gen_test_ad" in page.read_text(encoding="utf-8")

    # Run the generator
    result = subprocess.run(
        [sys.executable, "tools/build_mini_apps.py"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(root))
    assert result.returncode == 0, result.stderr

    # Marker must survive
    content = page.read_text(encoding="utf-8")
    assert "gen_test_ad" in content, "Generator destroyed injected ad marker!"

    # Cleanup: remove the test marker
    apply_injection(str(page), [], remove_slots=["body_end"])
