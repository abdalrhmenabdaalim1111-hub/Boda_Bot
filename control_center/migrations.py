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
    # ── Phase A1: Ad Code Manager ───────────────────────────────────────────
    Migration(
        version=2,
        name="ad_code_manager",
        up=(
            "CREATE TABLE IF NOT EXISTS ads ("
            "  ad_id       TEXT PRIMARY KEY,"
            "  name        TEXT    NOT NULL,"
            "  provider    TEXT    NOT NULL DEFAULT 'monetag',"
            "  format      TEXT    NOT NULL DEFAULT 'custom',"
            "  slot        TEXT    NOT NULL DEFAULT 'body_end',"
            "  snippet     TEXT    NOT NULL,"
            "  zone_id     TEXT,"
            "  direct_link TEXT,"
            "  notes       TEXT,"
            "  enabled     INTEGER NOT NULL DEFAULT 1,"
            "  cpm_rate    REAL    NOT NULL DEFAULT 0,"
            "  created_at  TEXT    NOT NULL,"
            "  updated_at  TEXT    NOT NULL,"
            "  created_by  TEXT"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_ads_slot ON ads(slot)",
            "CREATE INDEX IF NOT EXISTS idx_ads_enabled ON ads(enabled)",
            "CREATE TABLE IF NOT EXISTS ad_assignments ("
            "  id         INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  ad_id      TEXT    NOT NULL,"
            "  scope      TEXT    NOT NULL,"
            "  target_id  TEXT,"
            "  priority   INTEGER NOT NULL DEFAULT 0,"
            "  created_at TEXT    NOT NULL,"
            "  FOREIGN KEY (ad_id) REFERENCES ads(ad_id) ON DELETE CASCADE"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_ad_assign_scope ON ad_assignments(scope, target_id)",
            "CREATE INDEX IF NOT EXISTS idx_ad_assign_ad ON ad_assignments(ad_id)",
            "CREATE TABLE IF NOT EXISTS ad_events ("
            "  id          INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  ad_id       TEXT    NOT NULL,"
            "  bot_id      TEXT    NOT NULL,"
            "  event_type  TEXT    NOT NULL,"
            "  user_id     INTEGER,"
            "  occurred_at TEXT    NOT NULL"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_ad_events_ad ON ad_events(ad_id)",
            "CREATE INDEX IF NOT EXISTS idx_ad_events_bot ON ad_events(bot_id)",
            "CREATE INDEX IF NOT EXISTS idx_ad_events_time ON ad_events(occurred_at DESC)",
        ),
        down=(
            "DROP INDEX IF EXISTS idx_ad_events_time",
            "DROP INDEX IF EXISTS idx_ad_events_bot",
            "DROP INDEX IF EXISTS idx_ad_events_ad",
            "DROP TABLE IF EXISTS ad_events",
            "DROP INDEX IF EXISTS idx_ad_assign_ad",
            "DROP INDEX IF EXISTS idx_ad_assign_scope",
            "DROP TABLE IF EXISTS ad_assignments",
            "DROP INDEX IF EXISTS idx_ads_enabled",
            "DROP INDEX IF EXISTS idx_ads_slot",
            "DROP TABLE IF EXISTS ads",
        ),
    ),
    # ── Phase 1.3: Gate Foundation (Subscription Gate Core) ────────────────────
    Migration(
        version=3,
        name="gate_foundation",
        up=(
            # ── Gate Channels Library ─────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS sub_channels (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                title               TEXT NOT NULL,
                chat_type           TEXT NOT NULL CHECK(chat_type IN ('channel','group','supergroup')),
                chat_id             INTEGER NOT NULL UNIQUE,
                username            TEXT,
                invite_link         TEXT,
                language            TEXT NOT NULL DEFAULT 'ar',
                is_active           INTEGER NOT NULL DEFAULT 1,
                checker_bot_admin   INTEGER NOT NULL DEFAULT 0,
                last_validated      TEXT,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_sub_channels_active ON sub_channels(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_sub_channels_chat_id ON sub_channels(chat_id)",
            # ── Gate Profiles (Global / Bot / Category) ───────────────────────
            """
            CREATE TABLE IF NOT EXISTS gate_profiles (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                name                TEXT NOT NULL UNIQUE,
                scope_type          TEXT NOT NULL CHECK(scope_type IN ('global','bot','category')),
                scope_value         TEXT,
                mode                TEXT NOT NULL DEFAULT 'all' CHECK(mode IN ('all','at_least_n','soft')),
                required_count      INTEGER NOT NULL DEFAULT 5,
                soft_free_uses      INTEGER NOT NULL DEFAULT 0,
                is_active           INTEGER NOT NULL DEFAULT 1,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_gate_profiles_scope ON gate_profiles(scope_type, scope_value)",
            # ── Gate Slots (5 positions per profile) ──────────────────────────
            """
            CREATE TABLE IF NOT EXISTS gate_slots (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id          INTEGER NOT NULL REFERENCES gate_profiles(id) ON DELETE CASCADE,
                position            INTEGER NOT NULL CHECK(position BETWEEN 1 AND 5),
                channel_id          INTEGER NOT NULL REFERENCES sub_channels(id) ON DELETE CASCADE,
                is_required         INTEGER NOT NULL DEFAULT 1,
                is_pinned           INTEGER NOT NULL DEFAULT 0,
                display_order       INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(profile_id, position)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_gate_slots_profile ON gate_slots(profile_id)",
            # ── Shared Membership Cache (cross-bot) ───────────────────────────
            """
            CREATE TABLE IF NOT EXISTS membership_cache (
                user_id             INTEGER NOT NULL,
                channel_id          INTEGER NOT NULL REFERENCES sub_channels(id) ON DELETE CASCADE,
                status              TEXT NOT NULL CHECK(status IN ('member','not_member','unknown')),
                checked_at          TEXT NOT NULL,
                expires_at          TEXT NOT NULL,
                PRIMARY KEY (user_id, channel_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_membership_expires ON membership_cache(expires_at)",
            # ── Gate Events (Audit & Funnel Analytics) ────────────────────────
            """
            CREATE TABLE IF NOT EXISTS gate_events (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id              TEXT NOT NULL,
                user_id_hash        TEXT NOT NULL,
                event               TEXT NOT NULL CHECK(event IN (
                    'gate_shown','join_clicked','verify_clicked','verified','failed_open','skipped_admin'
                )),
                channel_id          INTEGER,
                profile_id          INTEGER,
                metadata            TEXT,
                created_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_gate_events_bot_time ON gate_events(bot_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_gate_events_user_time ON gate_events(user_id_hash, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_gate_events_channel ON gate_events(channel_id)",
        ),
        down=(
            "DROP INDEX IF EXISTS idx_gate_events_channel",
            "DROP INDEX IF EXISTS idx_gate_events_user_time",
            "DROP INDEX IF EXISTS idx_gate_events_bot_time",
            "DROP TABLE IF EXISTS gate_events",
            "DROP INDEX IF EXISTS idx_membership_expires",
            "DROP TABLE IF EXISTS membership_cache",
            "DROP INDEX IF EXISTS idx_gate_slots_profile",
            "DROP TABLE IF EXISTS gate_slots",
            "DROP INDEX IF EXISTS idx_gate_profiles_scope",
            "DROP TABLE IF EXISTS gate_profiles",
            "DROP INDEX IF EXISTS idx_sub_channels_chat_id",
            "DROP INDEX IF EXISTS idx_sub_channels_active",
            "DROP TABLE IF EXISTS sub_channels",
        ),
    ),
    # ── Phase 1.4: Store Manager ──────────────────────────────────────────────
    Migration(
        version=4,
        name="store_manager",
        up=(
            """
            CREATE TABLE IF NOT EXISTS store_items (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id              TEXT NOT NULL UNIQUE REFERENCES bot_config(bot_id) ON DELETE CASCADE,
                title_ar            TEXT NOT NULL,
                title_en            TEXT,
                short_desc_ar       TEXT,
                short_desc_en       TEXT,
                long_desc_ar        TEXT,
                long_desc_en        TEXT,
                icon_url            TEXT,
                cover_url           TEXT,
                category            TEXT NOT NULL DEFAULT 'أخرى',
                tags                TEXT,
                badges              TEXT,
                display_order       INTEGER NOT NULL DEFAULT 0,
                status              TEXT NOT NULL DEFAULT 'live' CHECK(status IN ('live','hidden','coming_soon')),
                deep_link           TEXT,
                miniapp_url         TEXT,
                views               INTEGER NOT NULL DEFAULT 0,
                opens               INTEGER NOT NULL DEFAULT 0,
                clicks              INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_store_items_status ON store_items(status)",
            "CREATE INDEX IF NOT EXISTS idx_store_items_category ON store_items(category)",
            "CREATE INDEX IF NOT EXISTS idx_store_items_order ON store_items(display_order)",
        ),
        down=(
            "DROP INDEX IF EXISTS idx_store_items_order",
            "DROP INDEX IF EXISTS idx_store_items_category",
            "DROP INDEX IF EXISTS idx_store_items_status",
            "DROP TABLE IF EXISTS store_items",
        ),
    ),
    # ── Phase 1.5: Bot Profile Fields (per-language) ──────────────────────────
    Migration(
        version=5,
        name="bot_profile_fields",
        up=(
            # Add per-language profile fields to bot_config
            "ALTER TABLE bot_config ADD COLUMN profile_name_ar TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_name_en TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_desc_ar TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_desc_en TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_short_ar TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_short_en TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_commands_ar TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_commands_en TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_menu_ar TEXT",
            "ALTER TABLE bot_config ADD COLUMN profile_menu_en TEXT",
        ),
        down=(
            # SQLite doesn't support DROP COLUMN directly; recreate table without these columns
            "PRAGMA foreign_keys=OFF",
            """
            CREATE TABLE bot_config_old AS
            SELECT bot_id, display_name, category, enabled, token_enc, token_hint, token_env,
                   features, ad_group, created_at, updated_at
            FROM bot_config
            """,
            "DROP TABLE bot_config",
            """
            CREATE TABLE bot_config (
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
            "INSERT INTO bot_config SELECT * FROM bot_config_old",
            "DROP TABLE bot_config_old",
            "PRAGMA foreign_keys=ON",
        ),
    ),
    # ── Phase 1.6: Gate Config Defaults & Indexes ─────────────────────────────
    Migration(
        version=6,
        name="gate_config_defaults",
        up=(
            # Default global gate profile (disabled by default, will be enabled via dashboard)
            """
            INSERT OR IGNORE INTO gate_profiles (name, scope_type, scope_value, mode, required_count, soft_free_uses, is_active, created_at, updated_at)
            VALUES ('global_default', 'global', NULL, 'all', 5, 0, 0, datetime('now'), datetime('now'))
            """,
            # Default Store channel entry (placeholder - real chat_id set via dashboard)
            """
            INSERT OR IGNORE INTO sub_channels (id, title, chat_type, chat_id, username, language, is_active, checker_bot_admin, created_at, updated_at)
            VALUES (1, 'متجر بودا', 'channel', 0, '@BodaStoreeBot', 'ar', 0, 0, datetime('now'), datetime('now'))
            """,
            # Pin Store channel to slot 1 in global profile
            """
            INSERT OR IGNORE INTO gate_slots (profile_id, position, channel_id, is_required, is_pinned, display_order, created_at)
            SELECT 1, 1, 1, 1, 1, 0, datetime('now')
            WHERE EXISTS (SELECT 1 FROM gate_profiles WHERE id=1)
              AND EXISTS (SELECT 1 FROM sub_channels WHERE id=1)
            """,
        ),
        down=(
            "DELETE FROM gate_slots WHERE profile_id=1 AND position=1 AND channel_id=1",
            "DELETE FROM sub_channels WHERE id=1",
            "DELETE FROM gate_profiles WHERE name='global_default'",
        ),
    ),
    # ── Phase 2.1: store_items accepts 'draft' status ─────────────────────────
    # The dashboard & API already expose a "draft" (مسودة) status, but the v4
    # CHECK constraint only allowed ('live','hidden','coming_soon'), so any
    # create/update with status='draft' failed at the DB level. SQLite cannot
    # ALTER a CHECK, so the table is rebuilt with the extended constraint.
    Migration(
        version=7,
        name="store_items_draft_status",
        up=(
            "PRAGMA foreign_keys=OFF",
            """
            CREATE TABLE store_items_new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id              TEXT NOT NULL UNIQUE REFERENCES bot_config(bot_id) ON DELETE CASCADE,
                title_ar            TEXT NOT NULL,
                title_en            TEXT,
                short_desc_ar       TEXT,
                short_desc_en       TEXT,
                long_desc_ar        TEXT,
                long_desc_en        TEXT,
                icon_url            TEXT,
                cover_url           TEXT,
                category            TEXT NOT NULL DEFAULT 'أخرى',
                tags                TEXT,
                badges              TEXT,
                display_order       INTEGER NOT NULL DEFAULT 0,
                status              TEXT NOT NULL DEFAULT 'live' CHECK(status IN ('live','hidden','coming_soon','draft')),
                deep_link           TEXT,
                miniapp_url         TEXT,
                views               INTEGER NOT NULL DEFAULT 0,
                opens               INTEGER NOT NULL DEFAULT 0,
                clicks              INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """,
            "INSERT INTO store_items_new SELECT * FROM store_items",
            "DROP TABLE store_items",
            "ALTER TABLE store_items_new RENAME TO store_items",
            "CREATE INDEX IF NOT EXISTS idx_store_items_status ON store_items(status)",
            "CREATE INDEX IF NOT EXISTS idx_store_items_category ON store_items(category)",
            "CREATE INDEX IF NOT EXISTS idx_store_items_order ON store_items(display_order)",
            "PRAGMA foreign_keys=ON",
        ),
        down=(
            "PRAGMA foreign_keys=OFF",
            # draft rows cannot exist under the old constraint; fold them into hidden
            "UPDATE store_items SET status='hidden' WHERE status='draft'",
            """
            CREATE TABLE store_items_old (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id              TEXT NOT NULL UNIQUE REFERENCES bot_config(bot_id) ON DELETE CASCADE,
                title_ar            TEXT NOT NULL,
                title_en            TEXT,
                short_desc_ar       TEXT,
                short_desc_en       TEXT,
                long_desc_ar        TEXT,
                long_desc_en        TEXT,
                icon_url            TEXT,
                cover_url           TEXT,
                category            TEXT NOT NULL DEFAULT 'أخرى',
                tags                TEXT,
                badges              TEXT,
                display_order       INTEGER NOT NULL DEFAULT 0,
                status              TEXT NOT NULL DEFAULT 'live' CHECK(status IN ('live','hidden','coming_soon')),
                deep_link           TEXT,
                miniapp_url         TEXT,
                views               INTEGER NOT NULL DEFAULT 0,
                opens               INTEGER NOT NULL DEFAULT 0,
                clicks              INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """,
            "INSERT INTO store_items_old SELECT * FROM store_items",
            "DROP TABLE store_items",
            "ALTER TABLE store_items_old RENAME TO store_items",
            "CREATE INDEX IF NOT EXISTS idx_store_items_status ON store_items(status)",
            "CREATE INDEX IF NOT EXISTS idx_store_items_category ON store_items(category)",
            "CREATE INDEX IF NOT EXISTS idx_store_items_order ON store_items(display_order)",
            "PRAGMA foreign_keys=ON",
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


def _db_file_of(conn: sqlite3.Connection) -> str:
    """The file backing a connection (empty string for in-memory databases)."""
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        return str(row[2]) if row and row[2] else ""
    except Exception:
        return ""


def backup_database(db_file: str | None = None,
                    conn: sqlite3.Connection | None = None) -> str:
    """
    Take a timestamped snapshot of the SQLite database before a schema change.

    The copy is made with the SQLite **backup API**, not a plain file copy:
    in WAL mode the committed data still lives in the ``-wal`` sidecar, so
    copying the ``.db`` file alone would produce an incomplete snapshot.

    The snapshot lands in ``Backups/`` for the production database and next
    to the database itself for any other path (tests, throw-away copies).

    Returns the path of the snapshot, or an empty string on failure.
    """
    source = db_file or _db_file_of(conn) or config.db_path()
    source_path = Path(source)
    if not source_path.exists():
        return ""

    try:
        production = Path(config.db_path()).resolve()
        target_dir = (config.BACKUPS_DIR
                      if source_path.resolve() == production
                      else source_path.parent)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = target_dir / f"pre_migration_{stamp}.db"

        src = sqlite3.connect(str(source_path))
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)          # consistent snapshot (WAL included)
            finally:
                dst.close()
        finally:
            src.close()
        return str(target)
    except Exception:
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

        backup_path = backup_database(conn=conn) if backup else ""
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
