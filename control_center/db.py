"""
control_center/db.py — database access for the Control Center.

The Control Center deliberately uses **the same SQLite file** as the bots
(``Data/boda_bot.db``), so statistics, ad data and bot configuration can be
joined without any cross-database synchronisation.

Two access styles are provided:

``get_db()``
    Returns the shared :class:`database.BodaDatabase` instance — the very same
    object the bots use. Honours ``BODA_DB_PATH`` so tests stay isolated.

``connect()``
    A raw connection, used by the migration runner which must not depend on
    the application-level schema bootstrap.
"""

import os
import sqlite3
import threading
from pathlib import Path

from . import config

_migrate_lock = threading.Lock()


def get_db():
    """Return the shared BodaDatabase instance (or ``None`` when unavailable)."""
    try:
        from database import BodaDatabase
    except ImportError:
        return None
    try:
        return BodaDatabase.get_instance()
    except Exception:
        return None


def reset_db() -> None:
    """Drop the cached singleton — test helper only."""
    try:
        from database import BodaDatabase
        BodaDatabase.reset_instance()
    except Exception:
        pass


def connect(db_file: str | None = None) -> sqlite3.Connection:
    """Open a raw connection with the project's standard pragmas."""
    target = db_file or config.db_path()
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def column_names(conn: sqlite3.Connection, table: str) -> list:
    """Return the column names of a table (empty list when it does not exist)."""
    if not table_exists(conn, table):
        return []
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def ensure_column(conn: sqlite3.Connection, table: str, column: str,
                  ddl: str) -> bool:
    """
    Add a column when it is missing.

    Used by migrations that must work on databases created before the
    Control Center existed. Returns ``True`` when the column was added.
    """
    if not table_exists(conn, table):
        return False
    if column in column_names(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    return True


def db_file_size(path: str | None = None) -> int:
    try:
        return os.path.getsize(path or config.db_path())
    except OSError:
        return 0
