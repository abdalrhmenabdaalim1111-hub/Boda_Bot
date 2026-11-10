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


class TestSmartNetwork:
    """اختبارات شبكة الـ 5 بوتات الذكية: التعيين، التحقق الحقيقي، الحظر"""

    @pytest.fixture
    def db(self, tmp_path):
        from database import BodaDatabase
        return BodaDatabase(db_path=str(tmp_path / "net.db"))

    def test_set_get_assignments_roundtrip(self, db):
        db.set_network_assignments(1, ["store", "qrgen", "vidload", "safepass", "iqtest"])
        assert db.get_network_assignments(1) == ["store", "qrgen", "vidload", "safepass", "iqtest"]

    def test_set_assignments_replaces_completely(self, db):
        db.set_network_assignments(2, ["a", "b", "c", "d", "e"])
        db.set_network_assignments(2, ["x", "y", "z", "w", "v"])
        assert db.get_network_assignments(2) == ["x", "y", "z", "w", "v"]

    def test_assignments_are_per_user(self, db):
        db.set_network_assignments(3, ["a", "b", "c", "d", "e"])
        db.set_network_assignments(4, ["f", "g", "h", "i", "j"])
        assert "a" in db.get_network_assignments(3)
        assert "a" not in db.get_network_assignments(4)

    def test_has_user_started(self, db):
        db.track_user("qrgen", 777, "أحمد")
        assert db.has_user_started("qrgen", 777) is True
        assert db.has_user_started("vidload", 777) is False
        assert db.has_user_started("qrgen", 888) is False

    def test_bot_user_counts(self, db):
        db.track_user("qrgen", 1, "u1")
        db.track_user("qrgen", 2, "u2")
        db.track_user("vidload", 3, "u3")
        counts = db.get_bot_user_counts()
        assert counts.get("qrgen") == 2
        assert counts.get("vidload") == 1

    def test_activation_time_for_ttl(self, db):
        assert db.get_network_activation_time(5) is None
        db.set_network_activated(5, True)
        t = db.get_network_activation_time(5)
        assert t is not None
        from datetime import datetime
        assert abs((datetime.now() - datetime.fromisoformat(t)).total_seconds()) < 60

    def test_mark_user_blocked_and_list(self, db):
        # مستخدم له سجل مسبق
        db.track_user("qrgen", 9, "u9")
        db.mark_user_blocked("qrgen", 9)
        assert "qrgen" in db.get_blocked_bot_ids(9)

        # مستخدم بلا سجل مسبق — يُسجل الحظر على أي حال
        db.mark_user_blocked("vidload", 10)
        assert "vidload" in db.get_blocked_bot_ids(10)

        # غير المحظور لا يظهر
        db.track_user("iqtest", 9, "u9b")
        assert "iqtest" not in db.get_blocked_bot_ids(9)



if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
