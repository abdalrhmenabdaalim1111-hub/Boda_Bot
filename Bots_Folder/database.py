# -*- coding: utf-8 -*-
"""
Bots_Folder/database.py — قاعدة البيانات المركزية (Unified SQLite Database)
تستخدم وضع WAL للسماح بالقراءة والكتابة المتزامنة من عدة عمليات.
"""
import sqlite3
import os
import threading
from pathlib import Path

# المسار إلى ملف قاعدة البيانات
DB_PATH = Path(__file__).parent.parent / "Data" / "boda_bot.db"

class BodaDatabase:
    def __init__(self):
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """إنشاء الجداول الأساسية إذا لم تكن موجودة."""
        with self._lock:
            with self._get_conn() as conn:
                # جدول المستخدمين الموحد
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        full_name TEXT,
                        xp_points INTEGER DEFAULT 0,
                        level TEXT DEFAULT 'مبتدئ 🐣',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen TIMESTAMP
                    )
                """)
                # جدول إحصائيات النشاط
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS usage_stats (
                        user_id INTEGER,
                        bot_id TEXT,
                        usage_count INTEGER DEFAULT 1,
                        last_used TIMESTAMP,
                        PRIMARY KEY (user_id, bot_id)
                    )
                """)
                conn.commit()

    def track_user(self, bot_id: str, user_id: int, full_name: str, username: str):
        """تحديث بيانات المستخدم وتتبع نشاطه في بوت معين."""
        with self._lock:
            with self._get_conn() as conn:
                # تحديث بيانات المستخدم وإعطائه 5 نقاط XP عند كل استخدام
                conn.execute("""
                    INSERT INTO users (user_id, username, full_name, xp_points, last_seen)
                    VALUES (?, ?, ?, 5, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET 
                        username=excluded.username,
                        full_name=excluded.full_name,
                        xp_points=xp_points + 5,
                        last_seen=CURRENT_TIMESTAMP
                """, (user_id, username, full_name))
                
                # تحديث مستوى المستخدم بناءً على نقاطه
                conn.execute("""
                    UPDATE users SET level = CASE 
                        WHEN xp_points >= 1000 THEN 'أسطورة 👑'
                        WHEN xp_points >= 500 THEN 'محترف 🌟'
                        WHEN xp_points >= 100 THEN 'مستكشف 🚀'
                        ELSE 'مبتدئ 🐣'
                    END WHERE user_id = ?
                """, (user_id,))

                # تحديث إحصائيات الاستخدام
                conn.execute("""
                    INSERT INTO usage_stats (user_id, bot_id, usage_count, last_used)
                    VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, bot_id) DO UPDATE SET 
                        usage_count = usage_count + 1,
                        last_used = CURRENT_TIMESTAMP
                """, (user_id, bot_id))
                conn.commit()

    def get_user_profile(self, user_id: int):
        """استرجاع بيانات الملف الشخصي الموحد للمستخدم."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                return dict(row)
            return None

# دالة مساعدة للحصول على نسخة قاعدة البيانات
def get_db():
    return BodaDatabase()
