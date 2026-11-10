"""
tests/test_control_center_migrations.py — اختبارات الترحيلات العكسية

تغطي:
• تطبيق الترحيلات على قاعدة بيانات فارغة
• عدم إعادة التطبيق (idempotency)
• التراجع (down) يعيد القاعدة لحالتها الأصلية
• النسخة الاحتياطية قبل الترحيل
• حالة الترحيلات (status)
"""

import sqlite3
from pathlib import Path

import pytest

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401  (path bootstrap)

from control_center import migrations
from control_center.db import connect


@pytest.fixture()
def empty_db(tmp_path):
    path = tmp_path / "migrate.db"
    conn = connect(str(path))
    yield conn
    conn.close()


def test_apply_migrations_creates_ledger(empty_db):
    """تطبيق الترحيلات ينشئ سجل الترحيلات والجداول الجديدة"""
    applied = migrations.apply_migrations(empty_db, backup=False)
    assert len(applied) == len(migrations.MIGRATIONS)
    assert applied[0].version == 1

    tables = {
        r[0] for r in empty_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
    }
    for expected in ("schema_migrations", "bot_config", "audit_log",
                     "cc_users", "cc_sessions", "bot_templates"):
        assert expected in tables


def test_apply_migrations_is_idempotent(empty_db):
    """تطبيق الترحيلات مرتين لا يكرر شيئاً"""
    migrations.apply_migrations(empty_db, backup=False)
    before = empty_db.execute(
        "SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    second = migrations.apply_migrations(empty_db, backup=False)
    after = empty_db.execute(
        "SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert second == []
    assert before == after


def test_rollback_reverts_schema(empty_db):
    """التراجع ينفّذ سكربت down ويزيل الصف من السجل"""
    migrations.apply_migrations(empty_db, backup=False)
    rolled = migrations.rollback(empty_db, steps=1)
    assert len(rolled) == 1

    tables = {
        r[0] for r in empty_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "bot_config" not in tables
    assert "audit_log" not in tables

    versions = [r[0] for r in empty_db.execute(
        "SELECT version FROM schema_migrations")]
    assert 1 not in versions


def test_rollback_all_then_reapply(empty_db):
    """التراجع الكامل ثم إعادة التطبيق يعيد قاعدة بيانات سليمة"""
    migrations.apply_migrations(empty_db, backup=False)
    migrations.rollback(empty_db, steps=len(migrations.MIGRATIONS))
    assert migrations.pending_migrations(empty_db)

    applied = migrations.apply_migrations(empty_db, backup=False)
    assert len(applied) == len(migrations.MIGRATIONS)
    assert migrations.status(empty_db)["applied_count"] == len(migrations.MIGRATIONS)


def test_status_reports_pending_and_applied(empty_db):
    """حالة الترحيلات تصف ما طُبق وما تبقى"""
    status = migrations.status(empty_db)
    assert status["current_version"] == 0
    assert status["pending"]

    migrations.apply_migrations(empty_db, backup=False)
    status = migrations.status(empty_db)
    assert status["current_version"] == max(m.version for m in migrations.MIGRATIONS)
    assert status["pending"] == []
    assert status["applied_count"] == len(migrations.MIGRATIONS)


def test_backup_created_before_migration(tmp_path, monkeypatch):
    """تُنشأ نسخة احتياطية مؤرّخة قبل تطبيق الترحيلات"""
    from control_center import config
    monkeypatch.setattr(config, "BACKUPS_DIR", tmp_path / "backups")

    db_file = tmp_path / "backupme.db"
    conn = connect(str(db_file))
    conn.execute("CREATE TABLE demo (id INTEGER)")
    conn.commit()
    conn.close()

    path = migrations.backup_database(str(db_file))
    assert path
    assert "pre_migration_" in path
    assert Path(path).exists()


def test_backup_is_a_complete_snapshot(tmp_path):
    """
    النسخة الاحتياطية تحتوي كل البيانات — لا مجرد ترويسة الملف.

    في وضع WAL تبقى البيانات الملتزمة في ملف ‎-wal‎، فنسخ ملف ‎.db‎
    مباشرةً ينتج نسخة **ناقصة**. لذلك نستخدم واجهة SQLite الاحتياطية.
    """
    db_file = tmp_path / "wal.db"
    conn = connect(str(db_file))
    conn.execute("CREATE TABLE demo (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO demo (id, name) VALUES (1, 'kept')")
    conn.commit()

    path = migrations.backup_database(conn=conn)
    conn.close()

    assert path
    backup = sqlite3.connect(path)
    try:
        rows = backup.execute("SELECT id, name FROM demo").fetchall()
        tables = [r[0] for r in backup.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
    finally:
        backup.close()

    assert "demo" in tables
    assert rows == [(1, "kept")]


def test_backup_lands_next_to_a_non_production_database(tmp_path):
    """قاعدة غير إنتاجية تأخذ نسختها بجانبها لا في مجلد Backups"""
    db_file = tmp_path / "isolated.db"
    conn = connect(str(db_file))
    path = migrations.backup_database(conn=conn)
    conn.close()

    assert path
    assert Path(path).parent == tmp_path


def test_ensure_ready_never_raises(empty_db, monkeypatch):
    """ensure_ready لا يرمي استثناءات حتى عند الفشل"""
    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "apply_migrations", _boom)
    report = migrations.ensure_ready()
    assert report["ok"] is False
    assert "boom" in report["error"]
