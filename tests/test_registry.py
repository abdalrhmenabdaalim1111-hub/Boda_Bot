# =============================================================================
#  tests/test_registry.py — اختبارات سجل البوتات
# =============================================================================
import json
import os
import sys
import pytest
from pathlib import Path

# إضافة المسار الجذر للمشروع
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REGISTRY_PATH = ROOT / "bots_registry.json"


def load_registry():
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestRegistry:
    """اختبارات صحة ملف bots_registry.json"""

    def test_registry_exists(self):
        """يجب أن يوجد ملف bots_registry.json"""
        assert REGISTRY_PATH.exists(), "bots_registry.json غير موجود"

    def test_registry_is_valid_json(self):
        """يجب أن يكون الملف JSON صحيح"""
        data = load_registry()
        assert isinstance(data, list), "الـ registry يجب أن يكون قائمة"

    def test_all_bots_have_required_fields(self):
        """كل بوت يجب أن يحتوي على الحقول المطلوبة"""
        required = {"id", "name", "description", "url", "tag"}
        data = load_registry()
        for bot in data:
            missing = required - set(bot.keys())
            assert not missing, (
                f"البوت '{bot.get('id', '?')}' يفتقد: {missing}")

    def test_all_ids_are_strings(self):
        """كل ID يجب أن يكون نصاً"""
        data = load_registry()
        for bot in data:
            assert isinstance(bot["id"], str), (
                f"ID البوت {bot['id']} ليس نصاً")

    def test_no_duplicate_ids(self):
        """لا يجب أن تكون هناك IDات مكررة"""
        data  = load_registry()
        ids   = [b["id"] for b in data]
        dupes = [i for i in set(ids) if ids.count(i) > 1]
        assert not dupes, f"IDات مكررة: {dupes}"

    def test_all_urls_start_with_https(self):
        """كل URL يجب أن يبدأ بـ https"""
        data = load_registry()
        for bot in data:
            url = bot.get("url", "")
            if url:  # تجاهل الروابط الفارغة
                assert url.startswith("https://"), (
                    f"البوت '{bot['id']}' لديه URL غير آمن: {url}")

    def test_hidden_field_is_boolean(self):
        """حقل hidden يجب أن يكون boolean"""
        data = load_registry()
        for bot in data:
            if "hidden" in bot:
                assert isinstance(bot["hidden"], bool), (
                    f"البوت '{bot['id']}': hidden ليس boolean")

    def test_all_descriptions_not_empty(self):
        """كل وصف يجب ألا يكون فارغاً"""
        data = load_registry()
        for bot in data:
            desc = bot.get("description", "").strip()
            assert desc, f"البوت '{bot.get('id', '?')}' لديه وصف فارغ"

    def test_minimum_bot_count(self):
        """يجب أن يكون هناك 10+ بوتات على الأقل"""
        data = load_registry()
        assert len(data) >= 10, f"عدد البوتات ({len(data)}) أقل من المتوقع"

    def test_no_placeholder_urls(self):
        """لا يجب أن تكون هناك روابط placeholder غير محددة"""
        data = load_registry()
        for bot in data:
            url = bot.get("url", "")
            assert url != "https://t.me/", (
                f"البوت '{bot['id']}' لديه رابط placeholder")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
