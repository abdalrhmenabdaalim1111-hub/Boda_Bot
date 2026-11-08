# =============================================================================
#  tests/test_database.py — اختبارات قاعدة البيانات SQLite
# =============================================================================
import sys
import os
import pytest
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))


class TestBodaDatabase:
    """اختبارات قاعدة البيانات BodaDatabase"""

    @pytest.fixture
    def db(self, tmp_path):
        """قاعدة بيانات مؤقتة لكل اختبار"""
        from database import BodaDatabase
        db = BodaDatabase(db_path=str(tmp_path / "test.db"))
        yield db

    def test_db_creates_successfully(self, db):
        """قاعدة البيانات تُنشأ بدون أخطاء"""
        assert os.path.exists(db.db_path)

    def test_track_new_user(self, db):
        """تتبع مستخدم جديد"""
        db.track_user("currency", 123456, "أحمد", "ahmed")
        count = db.get_user_count("currency")
        assert count == 1

    def test_track_same_user_twice(self, db):
        """تتبع نفس المستخدم مرتين — يُحدّث ولا يُضيف"""
        db.track_user("currency", 123456, "أحمد")
        db.track_user("currency", 123456, "أحمد")
        count = db.get_user_count("currency")
        assert count == 1

    def test_track_multiple_bots(self, db):
        """نفس المستخدم في بوتين مختلفين"""
        db.track_user("currency", 123456)
        db.track_user("transbot", 123456)
        assert db.get_user_count("currency") == 1
        assert db.get_user_count("transbot") == 1

    def test_record_message(self, db):
        """تسجيل رسالة في الإحصائيات اليومية"""
        db.record_message("currency", 123456)
        stats = db.get_stats_today("currency")
        assert stats["messages"] >= 1

    def test_record_error(self, db):
        """تسجيل خطأ"""
        db.record_error("currency", Exception("Test error"), 123456)
        stats = db.get_stats_today("currency")
        assert stats["errors"] >= 1

    def test_bot_session_start_stop(self, db):
        """تسجيل جلسة بوت"""
        session_id = db.record_bot_start("currency")
        assert session_id is not None and session_id > 0
        db.record_bot_stop("currency", session_id, exit_code=0)
        history = db.get_uptime_history("currency")
        assert len(history) == 1
        assert history[0]["exit_code"] == 0

    def test_get_all_users_count(self, db):
        """إحصائيات المستخدمين لكل البوتات"""
        db.track_user("currency", 1)
        db.track_user("currency", 2)
        db.track_user("transbot", 3)
        counts = db.get_all_users_count()
        assert counts.get("currency") == 2
        assert counts.get("transbot") == 1

    def test_db_size_string(self, db):
        """حجم قاعدة البيانات يُعاد كنص"""
        size = db.get_db_size()
        assert isinstance(size, str)
        assert len(size) > 0

    def test_cleanup_old_data(self, db):
        """حذف البيانات القديمة لا يرفع استثناء"""
        db.cleanup_old_data(days=0)  # حذف كل شيء

    def test_stats_summary(self, db):
        """ملخص الإحصائيات"""
        db.record_message("currency", 1)
        db.record_message("currency", 2)
        summary = db.get_stats_summary(days=1)
        assert isinstance(summary, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
