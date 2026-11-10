"""
control_center/migrations.py — reversible, numbered schema migrations.

The project had no migration system: ``Bots_Folder/database.py`` bootstraps
its schema with inline ``CREATE TABLE IF NOT EXISTS`` statements. That stays
exactly as it is (backward compatibility), and this module adds a proper
ledger on top of it.

Rules
-----
* Every migration has a numeric version, a name, an ``up`` script and a
  ``down`` script.
* Migrations run inside a transaction, one at a time, and each applied
  version is recorded in ``schema_migrations``.
* A timestamped backup of the SQLite file is taken before the first migration
  of a run touches the database.
* ``down`` scripts are the exact inverse of ``up`` — dropping what ``up``
  created — so a rollback never leaves half a schema behind.
"""

import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config
from .db import connect

LEDGER_TABLE = "schema_migrations"


@dataclass(frozen=True)
class Migration:
    """A single reversible schema change."""

    version: int
    name: str
    up: tuple = field(default_factory=tuple)
    down: tuple = field(default_factory=tuple)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.version:03d}_{self.name}"


# ─────────────────────────────────────────────────────────────────────────────
# Migration catalogue
# ─────────────────────────────────────────────────────────────────────────────
MIGRATIONS: tuple = (
    Migration(
        version=1,
        name="control_center_foundation",
        up=(
            # ── Ledger ──────────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    INTEGER PRIMARY KEY,
                name       TEXT    NOT NULL,
                applied_at TEXT    NOT NULL,
                checksum   TEXT
            )
            """,
            # ── Per-bot runtime configuration ───────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS bot_config (
                bot_id       TEXT PRIMARY KEY,
                display_name TEXT,
                category     TEXT,
                enabled      INTEGER NOT NULL DEFAULT 1,
                token_enc    TEXT,
                token_hint   TEXT,
                token_env    TEXT,
                features     TEXT,
                ad_group     TEXT,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
            """,
            # ── Audit log ──────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT    NOT NULL,
                actor       TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                target_type TEXT,
                target_id   TEXT,
                details     TEXT,
                ip          TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(occurred_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)",
            "CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log(target_type, target_id)",
            # ── Control Center accounts and roles ───────────────────────────
            """
            CREATE TABLE IF NOT EXISTS cc_users (
                username       TEXT PRIMARY KEY,
                password_hash  TEXT    NOT NULL,
                role           TEXT    NOT NULL DEFAULT 'viewer',
                enabled        INTEGER NOT NULL DEFAULT 1,
                failed_logins  INTEGER NOT NULL DEFAULT 0,
                locked_until   TEXT,
                last_login_at  TEXT,
                created_at     TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cc_sessions (
                token_hash TEXT PRIMARY KEY,
                username   TEXT NOT NULL,
                role       TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                ip         TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_cc_sessions_user ON cc_sessions(username)",
            # ── Bot templates (New Bot Wizard) ─────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS bot_templates (
                id          TEXT PRIMARY KEY,
                name        TEXT    NOT NULL,
                description TEXT,
                body        TEXT    NOT NULL,
                is_builtin  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
            """,
        ),
        down=(
            "DROP TABLE IF EXISTS bot_templates",
            "DROP TABLE IF EXISTS cc_sessions",
            "DROP TABLE IF EXISTS cc_users",
            "DROP INDEX IF EXISTS idx_audit_target",
            "DROP INDEX IF EXISTS idx_audit_action",
            "DROP INDEX IF EXISTS idx_audit_time",
            "DROP TABLE IF EXISTS audit_log",
            "DROP TABLE IF EXISTS bot_config",
            # NOTE: the ledger itself is never dropped — it must survive the
            # rollback so the migration can be applied again later.
        ),
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT    NOT NULL,
            applied_at TEXT    NOT NULL,
            checksum   TEXT
        )
        """
    )


def applied_versions(conn: sqlite3.Connection) -> set:
    """Set of migration versions already applied to the database."""
    _ensure_ledger(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(r[0]) for r in rows}


def pending_migrations(conn: sqlite3.Connection) -> list:
    """Migrations that still have to run, ordered by version."""
    done = applied_versions(conn)
    return sorted((m for m in MIGRATIONS if m.version not in done),
                  key=lambda m: m.version)


def current_version(conn: sqlite3.Connection) -> int:
    """Highest applied migration version (0 when the database is fresh)."""
    applied = applied_versions(conn)
    return max(applied) if applied else 0


def _checksum(migration: Migration) -> str:
    import hashlib
    raw = "|".join(migration.up).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def backup_database(db_file: str | None = None) -> str:
    """
    Take a timestamped copy of the SQLite file before a schema change.

    Returns the path of the backup, or an empty string when it could not be
    created (the caller decides whether that is fatal).
    """
    source = Path(db_file or config.db_path())
    if not source.exists():
        return ""
    try:
        config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = config.BACKUPS_DIR / f"pre_migration_{stamp}.db"
        shutil.copy2(source, target)
        return str(target)
    except OSError:
        return ""


def _run_script(conn: sqlite3.Connection, script) -> None:
    """Execute one statement of a migration script."""
    statement = script.strip()
    if not statement:
        return
    conn.execute(statement)


def apply_migrations(conn: sqlite3.Connection | None = None,
                     backup: bool = True,
                     logger=None) -> list:
    """
    Apply every pending migration.

    Returns the list of applied :class:`Migration` objects (empty when the
    database was already up to date).
    """
    own_conn = conn is None
    if own_conn:
        conn = connect()
    try:
        pending = pending_migrations(conn)
        if not pending:
            return []

        backup_path = backup_database() if backup else ""
        if backup_path and logger:
            logger.info(f"💾 نسخة احتياطية قبل الترحيل: {Path(backup_path).name}")

        applied = []
        for migration in pending:
            now = datetime.now().isoformat()
            try:
                conn.execute("BEGIN")
                for statement in migration.up:
                    _run_script(conn, statement)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations "
                    "(version, name, applied_at, checksum) VALUES (?, ?, ?, ?)",
                    (migration.version, migration.name, now, _checksum(migration)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            applied.append(migration)
            if logger:
                logger.info(f"✅ تم تطبيق الترحيل {migration}")
        return applied
    finally:
        if own_conn:
            conn.close()


def rollback(conn: sqlite3.Connection | None = None,
             steps: int = 1,
             logger=None) -> list:
    """
    Roll back the ``steps`` most recent migrations.

    The rollback path is exercised by the test-suite, so a broken ``down``
    script is caught before it ever touches a live database.
    """
    own_conn = conn is None
    if own_conn:
        conn = connect()
    try:
        done = sorted(applied_versions(conn), reverse=True)
        targets = [m for m in MIGRATIONS if m.version in done[:max(1, steps)]]
        targets.sort(key=lambda m: m.version, reverse=True)

        rolled = []
        for migration in targets:
            try:
                conn.execute("BEGIN")
                for statement in migration.down:
                    _run_script(conn, statement)
                conn.execute("DELETE FROM schema_migrations WHERE version=?",
                             (migration.version,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            rolled.append(migration)
            if logger:
                logger.info(f"↩️ تم التراجع عن الترحيل {migration}")
        return rolled
    finally:
        if own_conn:
            conn.close()


def status(conn: sqlite3.Connection | None = None) -> dict:
    """Human readable migration status for the Settings page."""
    own_conn = conn is None
    if own_conn:
        conn = connect()
    try:
        done = applied_versions(conn)
        rows = conn.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        return {
            "current_version": current_version(conn),
            "latest_available": max((m.version for m in MIGRATIONS), default=0),
            "applied": [dict(r) for r in rows],
            "pending": [str(m) for m in pending_migrations(conn)],
            "total": len(MIGRATIONS),
            "applied_count": len(done),
        }
    finally:
        if own_conn:
            conn.close()


def ensure_ready(logger=None) -> dict:
    """
    Entry point used by the API on start-up: apply pending migrations.

    Failures are swallowed and reported, never raised — a broken migration
    must not take the whole Control Center down.
    """
    try:
        applied = apply_migrations(logger=logger)
        return {"ok": True, "applied": [str(m) for m in applied]}
    except Exception as exc:  # pragma: no cover - defensive
        if logger:
            logger.error(f"❌ فشل تطبيق الترحيلات: {exc}")
        return {"ok": False, "error": str(exc), "applied": []}
