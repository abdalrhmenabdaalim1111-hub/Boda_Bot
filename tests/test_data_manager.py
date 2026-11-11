# =============================================================================
#  tests/test_data_manager.py — اختبارات مدير البيانات الموحد
# =============================================================================
import sys
import json
import time
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

from data_manager import DataManager, DataEntry


@pytest.fixture
def dm(tmp_path):
    """مدير بيانات بملف تخزين مؤقت (مسار مطلق يتجاوز مجلد الوحدة)"""
    return DataManager(storage_path=str(tmp_path / "bot_data.json"))


class TestDataEntry:
    def test_defaults(self):
        e = DataEntry(key="k", value="v")
        assert e.timestamp is not None
        assert e.expires_at is None
        assert e.metadata == {}


class TestSetGet:
    def test_set_and_get(self, dm):
        dm.set("name", "أحمد")
        assert dm.get("name") == "أحمد"

    def test_get_missing_returns_default(self, dm):
        assert dm.get("nope") is None
        assert dm.get("nope", "افتراضي") == "افتراضي"

    def test_set_with_metadata(self, dm):
        dm.set("k", 1, metadata={"source": "test"})
        assert dm.get_metadata("k") == {"source": "test"}

    def test_values_persist_to_disk(self, tmp_path):
        """الحفظ على القرص ثم إعادة التحميل من ملف جديد"""
        path = str(tmp_path / "persist.json")
        d1 = DataManager(storage_path=path)
        d1.set("x", {"nested": True})
        d2 = DataManager(storage_path=path)  # نسخة جديدة تقرأ نفس الملف
        assert d2.get("x") == {"nested": True}

    def test_expiry_not_persisted_if_still_valid(self, tmp_path):
        """قيمة بصلاحية كافية تُحفظ وتُعاد قراءتها"""
        path = str(tmp_path / "exp.json")
        d1 = DataManager(storage_path=path)
        d1.set("k", "v", expires_in=600)
        d2 = DataManager(storage_path=path)
        assert d2.get("k") == "v"

    def test_expired_entry_dropped_on_load(self, tmp_path):
        """إدخال منتهي الصلاحية في الملف يُتخطى عند التحميل"""
        path = tmp_path / "stale.json"
        past = (datetime.now() - timedelta(seconds=10)).isoformat()
        path.write_text(json.dumps({
            "old": {"value": 1, "timestamp": past,
                    "expires_at": past, "metadata": {}},
            "fresh": {"value": 2, "timestamp": past, "expires_at": None, "metadata": {}},
        }, ensure_ascii=False), encoding="utf-8")
        d = DataManager(storage_path=str(path))
        assert d.get("old") is None
        assert d.get("fresh") == 2

    def test_corrupt_file_is_ignored(self, tmp_path):
        """ملف تالف → لا ينهار التحميل ويبدأ فارغاً"""
        path = tmp_path / "bad.json"
        path.write_text("{{{not json", encoding="utf-8")
        d = DataManager(storage_path=str(path))
        assert d.get_all() == {}

    def test_expired_on_get_deletes_and_saves(self, tmp_path):
        """القراءة بعد انتهاء الصلاحية تحذف الإدخال وتحفظ"""
        path = str(tmp_path / "g.json")
        d = DataManager(storage_path=path)
        d.set("k", "v", expires_in=0.05)
        time.sleep(0.1)
        assert d.get("k") is None
        # محفوظ على القرص بلا الإدخال المنتهي
        assert "k" not in json.loads(Path(path).read_text(encoding="utf-8"))

    def test_save_failure_is_swallowed(self, dm):
        """فشل الكتابة لا يمنع التعديل في الذاكرة"""
        with patch("data_manager.json.dump", side_effect=OSError("disk full")):
            dm.set("k", "v")  # لا يرفع
        assert dm.get("k") == "v"


class TestDeleteExists:
    def test_delete_existing(self, dm):
        dm.set("k", 1)
        assert dm.delete("k") is True
        assert dm.get("k") is None

    def test_delete_missing(self, dm):
        assert dm.delete("nope") is False

    def test_exists_true_and_false(self, dm):
        assert dm.exists("k") is False
        dm.set("k", 1)
        assert dm.exists("k") is True

    def test_exists_expired_cleans_up(self, dm):
        """exists على مفتاح منتهٍ يحذفه ويعيد False"""
        dm.set("k", 1, expires_in=0.05)
        time.sleep(0.1)
        assert dm.exists("k") is False
        assert "k" not in dm.data


class TestCollections:
    def test_get_all(self, dm):
        dm.set("a", 1)
        dm.set("b", 2)
        assert dm.get_all() == {"a": 1, "b": 2}

    def test_get_all_purges_expired(self, dm):
        """get_all ينظف المنتهي ويعيد الساري فقط"""
        dm.set("live", 1)
        dm.set("dead", 2, expires_in=0.05)
        time.sleep(0.1)
        assert dm.get_all() == {"live": 1}

    def test_clear(self, dm):
        dm.set("a", 1)
        dm.clear()
        assert dm.get_all() == {}

    def test_get_keys_by_pattern(self, dm):
        """البحث بنمط fnmatch"""
        dm.set("user:1:name", "أ")
        dm.set("user:2:name", "ب")
        dm.set("order:1", "x")
        assert sorted(dm.get_keys_by_pattern("user:*")) == ["user:1:name", "user:2:name"]
        assert dm.get_keys_by_pattern("user:?*") == sorted(dm.get_keys_by_pattern("user:*"))
        assert dm.get_keys_by_pattern("nomatch") == []

    def test_metadata_roundtrip(self, dm):
        dm.set("k", 1, metadata={"a": 1})
        dm.update_metadata("k", {"b": 2})
        assert dm.get_metadata("k") == {"a": 1, "b": 2}

    def test_metadata_missing_key(self, dm):
        assert dm.get_metadata("nope") is None

    def test_update_metadata_missing_key_safe(self, dm):
        dm.update_metadata("nope", {"x": 1})  # لا يرفع

    def test_get_summary(self, dm):
        dm.set("a", "x" * 100)
        dm.set("b", 1, expires_in=0.05)
        time.sleep(0.1)
        s = dm.get_summary()
        assert s["total_entries"] == 2
        assert s["expired_entries"] == 1
        assert s["active_entries"] == 1
        assert s["size_bytes"] > 0
        assert s["size_mb"] == s["size_bytes"] / (1024 * 1024)

    def test_get_summary_empty(self, dm):
        s = dm.get_summary()
        assert s["total_entries"] == 0
        # json.dumps({}) == "{}" → الحجم الأساسي 2 بايت
        assert s["size_bytes"] == 2


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
