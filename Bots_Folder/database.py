# =============================================================================
#  Bots_Folder/database.py — نظام قاعدة البيانات SQLite الموحد
#  يوفر: تتبع المستخدمين، إحصائيات الاستخدام، جلسات البوت
# =============================================================================
import sqlite3
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger("BodaDB")


class BodaDatabase:
    """
    قاعدة بيانات SQLite مركزية لنظام Boda Bot.
    
    الجداول:
        users        — سجل المستخدمين لكل بوت
        usage_stats  — إحصائيات الاستخدام اليومية
        bot_sessions — جلسات حالة البوت
    
    مثال الاستخدام::
    
        db = BodaDatabase()
        db.track_user("currency", 123456789, "Ahmed")
        count = db.get_user_count("currency")
    """

    _instance: Optional["BodaDatabase"] = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = None):
        if db_path is None:
            base = Path(__file__).parent.parent / "Data"
            base.mkdir(exist_ok=True)
            db_path = str(base / "boda_bot.db")

        self.db_path = db_path
        self._conn_lock = threading.Lock()
        self._init_db()
        logger.info(f"✅ Database initialized: {db_path}")

    @classmethod
    def get_instance(cls) -> "BodaDatabase":
        """Singleton — نسخة واحدة مشتركة."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── تهيئة المخطط ──────────────────────────────────────────────────────────
    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                -- جدول المستخدمين
                CREATE TABLE IF NOT EXISTS users (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    bot_name    TEXT    NOT NULL,
                    username    TEXT,
                    full_name   TEXT,
                    first_seen  TEXT    NOT NULL,
                    last_seen   TEXT    NOT NULL,
                    usage_count INTEGER DEFAULT 1,
                    is_blocked  INTEGER DEFAULT 0,
                    UNIQUE(user_id, bot_name)
                );

                -- جدول إحصائيات الاستخدام اليومية
                CREATE TABLE IF NOT EXISTS usage_stats (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name    TEXT NOT NULL,
                    date        TEXT NOT NULL,
                    messages    INTEGER DEFAULT 0,
                    unique_users INTEGER DEFAULT 0,
                    errors      INTEGER DEFAULT 0,
                    UNIQUE(bot_name, date)
                );

                -- جدول جلسات البوت
                CREATE TABLE IF NOT EXISTS bot_sessions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name    TEXT NOT NULL,
                    started_at  TEXT NOT NULL,
                    stopped_at  TEXT,
                    exit_code   INTEGER,
                    restart_count INTEGER DEFAULT 0
                );

                -- جدول سجل الأخطاء
                CREATE TABLE IF NOT EXISTS error_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_name    TEXT NOT NULL,
                    error_msg   TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    user_id     INTEGER
                );

                -- جدول الإحالات والانتشار الفيروسي
                CREATE TABLE IF NOT EXISTS referrals (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referred_id INTEGER NOT NULL,
                    bot_name    TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    UNIQUE(referrer_id, referred_id, bot_name)
                );

                -- جدول تفعيل الشبكة الموحد (الـ 5 بوتات)
                CREATE TABLE IF NOT EXISTS network_activations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL UNIQUE,
                    activated_at TEXT NOT NULL,
                    is_active   INTEGER DEFAULT 1
                );

                -- Indexes للأداء
                CREATE INDEX IF NOT EXISTS idx_users_bot
                    ON users(bot_name);
                CREATE INDEX IF NOT EXISTS idx_stats_date
                    ON usage_stats(date);
                CREATE INDEX IF NOT EXISTS idx_sessions_bot
                    ON bot_sessions(bot_name);
                CREATE INDEX IF NOT EXISTS idx_referrals_ref
                    ON referrals(referrer_id);
                CREATE INDEX IF NOT EXISTS idx_activations_user
                    ON network_activations(user_id);
            """)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── Users ─────────────────────────────────────────────────────────────────
    def track_user(self, bot_name: str, user_id: int,
                   full_name: str = "", username: str = ""):
        """
        تسجيل أو تحديث معلومات مستخدم.
        
        Args:
            bot_name:  اسم البوت
            user_id:   معرف المستخدم التيليجرام
            full_name: الاسم الكامل
            username:  اسم المستخدم (@username)
        """
        now = datetime.now().isoformat()
        with self._conn_lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO users (user_id, bot_name, username, full_name,
                                       first_seen, last_seen, usage_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(user_id, bot_name) DO UPDATE SET
                        last_seen   = excluded.last_seen,
                        usage_count = usage_count + 1,
                        username    = COALESCE(excluded.username, username),
                        full_name   = COALESCE(excluded.full_name, full_name)
                """, (user_id, bot_name, username or None,
                      full_name or None, now, now))

    def get_user_count(self, bot_name: str) -> int:
        """إجمالي عدد المستخدمين لبوت معين."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM users WHERE bot_name=?",
                (bot_name,)
            ).fetchone()
            return row["cnt"] if row else 0

    def get_all_users_count(self) -> Dict[str, int]:
        """عدد المستخدمين لكل البوتات."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT bot_name, COUNT(*) as cnt
                FROM users GROUP BY bot_name
            """).fetchall()
            return {r["bot_name"]: r["cnt"] for r in rows}

    def get_top_users(self, bot_name: str, limit: int = 10) -> List[Dict]:
        """أكثر المستخدمين نشاطاً لبوت معين."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT user_id, full_name, username, usage_count, last_seen
                FROM users
                WHERE bot_name = ?
                ORDER BY usage_count DESC
                LIMIT ?
            """, (bot_name, limit)).fetchall()
            return [dict(r) for r in rows]

    # ── Usage Stats ───────────────────────────────────────────────────────────
    def record_message(self, bot_name: str, user_id: int):
        """تسجيل رسالة واحدة في الإحصائيات اليومية."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._conn_lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO usage_stats (bot_name, date, messages, unique_users)
                    VALUES (?, ?, 1, 1)
                    ON CONFLICT(bot_name, date) DO UPDATE SET
                        messages     = messages + 1,
                        unique_users = (
                            SELECT COUNT(DISTINCT user_id)
                            FROM users
                            WHERE bot_name = excluded.bot_name
                              AND date(last_seen) = excluded.date
                        )
                """, (bot_name, today))

    def record_error(self, bot_name: str, error_msg: str, user_id: int = None):
        """تسجيل خطأ."""
        now   = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        with self._conn_lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO error_log (bot_name, error_msg, occurred_at, user_id)
                    VALUES (?, ?, ?, ?)
                """, (bot_name, str(error_msg)[:500], now, user_id))
                conn.execute("""
                    INSERT INTO usage_stats (bot_name, date, errors)
                    VALUES (?, ?, 1)
                    ON CONFLICT(bot_name, date) DO UPDATE SET
                        errors = errors + 1
                """, (bot_name, today))

    def get_stats_today(self, bot_name: str) -> Dict[str, Any]:
        """إحصائيات اليوم لبوت معين."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM usage_stats
                WHERE bot_name=? AND date=?
            """, (bot_name, today)).fetchone()
            return dict(row) if row else {
                "bot_name": bot_name, "date": today,
                "messages": 0, "unique_users": 0, "errors": 0
            }

    def get_stats_summary(self, days: int = 7) -> List[Dict]:
        """ملخص الإحصائيات لآخر N أيام لكل البوتات."""
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT bot_name,
                       SUM(messages)     AS total_messages,
                       SUM(unique_users) AS total_users,
                       SUM(errors)       AS total_errors
                FROM usage_stats
                WHERE date >= ?
                GROUP BY bot_name
                ORDER BY total_messages DESC
            """, (since,)).fetchall()
            return [dict(r) for r in rows]

    # ── Bot Sessions ──────────────────────────────────────────────────────────
    def record_bot_start(self, bot_name: str) -> int:
        """تسجيل بداية تشغيل بوت، يُعيد session_id."""
        now = datetime.now().isoformat()
        with self._conn_lock:
            with self._get_conn() as conn:
                cur = conn.execute("""
                    INSERT INTO bot_sessions (bot_name, started_at)
                    VALUES (?, ?)
                """, (bot_name, now))
                return cur.lastrowid

    def record_bot_stop(self, bot_name: str, session_id: int = None,
                        exit_code: int = 0, restart_count: int = 0):
        """تسجيل إيقاف بوت."""
        now = datetime.now().isoformat()
        with self._conn_lock:
            with self._get_conn() as conn:
                if session_id:
                    conn.execute("""
                        UPDATE bot_sessions
                        SET stopped_at=?, exit_code=?, restart_count=?
                        WHERE id=?
                    """, (now, exit_code, restart_count, session_id))
                else:
                    # تحديث آخر جلسة مفتوحة
                    conn.execute("""
                        UPDATE bot_sessions
                        SET stopped_at=?, exit_code=?, restart_count=?
                        WHERE bot_name=? AND stopped_at IS NULL
                        ORDER BY id DESC LIMIT 1
                    """, (now, exit_code, restart_count, bot_name))

    def get_uptime_history(self, bot_name: str, limit: int = 10) -> List[Dict]:
        """سجل جلسات التشغيل لبوت معين."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM bot_sessions
                WHERE bot_name=?
                ORDER BY id DESC
                LIMIT ?
            """, (bot_name, limit)).fetchall()
            return [dict(r) for r in rows]

    # ── Referrals & Network Growth ───────────────────────────────────────────
    def record_referral(self, referrer_id: int, referred_id: int, bot_name: str) -> bool:
        """تسجيل إحالة جديدة لمستخدم قام بدعوة صديق."""
        if referrer_id == referred_id:
            return False  # لا يمكن للمستخدم إحالة نفسه
        now = datetime.now().isoformat()
        with self._conn_lock:
            with self._get_conn() as conn:
                try:
                    conn.execute("""
                        INSERT INTO referrals (referrer_id, referred_id, bot_name, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (referrer_id, referred_id, bot_name, now))
                    return True
                except sqlite3.IntegrityError:
                    return False  # مسجل مسبقاً

    def get_referral_count(self, user_id: int, bot_name: Optional[str] = None) -> int:
        """إرجاع عدد الأشخاص الذين قام المستخدم بدعوتهم."""
        with self._get_conn() as conn:
            if bot_name:
                row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM referrals
                    WHERE referrer_id = ? AND bot_name = ?
                """, (user_id, bot_name)).fetchone()
            else:
                row = conn.execute("""
                    SELECT COUNT(*) as cnt FROM referrals
                    WHERE referrer_id = ?
                """, (user_id,)).fetchone()
            return row["cnt"] if row else 0

    def is_network_activated(self, user_id: int) -> bool:
        """التحقق مما إذا كان المستخدم مفعلاً عبر شبكة البوتات الـ 5."""
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT is_active FROM network_activations
                WHERE user_id = ?
            """, (user_id,)).fetchone()
            return bool(row and row["is_active"])

    def set_network_activated(self, user_id: int, activated: bool = True):
        """تسجيل تفعيل المستخدم في شبكة البوتات."""
        now = datetime.now().isoformat()
        with self._conn_lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO network_activations (user_id, activated_at, is_active)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        is_active = excluded.is_active,
                        activated_at = excluded.activated_at
                """, (user_id, now, 1 if activated else 0))

    # ── Utilities ─────────────────────────────────────────────────────────────
    def get_db_size(self) -> str:
        """حجم قاعدة البيانات."""
        try:
            size = os.path.getsize(self.db_path)
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size/1024:.1f} KB"
            else:
                return f"{size/(1024*1024):.1f} MB"
        except Exception:
            return "—"

    def cleanup_old_data(self, days: int = 90):
        """حذف البيانات الأقدم من N يوم."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._conn_lock:
            with self._get_conn() as conn:
                conn.execute(
                    "DELETE FROM usage_stats WHERE date < ?", (cutoff,))
                conn.execute(
                    "DELETE FROM error_log WHERE date(occurred_at) < ?", (cutoff,))
        logger.info(f"🧹 Cleaned data older than {days} days")

    def vacuum(self):
        """ضغط قاعدة البيانات."""
        with self._get_conn() as conn:
            conn.execute("VACUUM")
        logger.info("🗜️ Database vacuumed")


# ── Convenience functions ──────────────────────────────────────────────────────

def get_db() -> BodaDatabase:
    """الحصول على النسخة المشتركة من قاعدة البيانات."""
    return BodaDatabase.get_instance()
