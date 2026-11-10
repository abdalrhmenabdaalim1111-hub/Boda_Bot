"""
tests/test_control_center_audit.py — اختبارات سجل التدقيق

تغطي:
• تسجيل عملية (من/ماذا/متى) وقراءةها
• الفلاتر (action / actor / target_id)
• العدّ والإحصاءات
• التنظيف حسب العمر
"""

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401  (path bootstrap)
from tests.cc_fixtures import cc_db  # noqa: F401  (fixture)

from control_center import audit


def test_record_and_query(cc_db):
    """تسجيل عملية ثم قراءتها"""
    row_id = audit.record("admin", "bot.start", "bot", "currency",
                          {"pid": 123}, ip="127.0.0.1")
    assert row_id > 0

    entries = audit.query(limit=10)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["actor"] == "admin"
    assert entry["action"] == "bot.start"
    assert entry["target_type"] == "bot"
    assert entry["target_id"] == "currency"
    assert entry["ip"] == "127.0.0.1"
    assert '"pid": 123' in entry["details"]


def test_query_filters(cc_db):
    """الفلاتر تعمل بشكل صحيح"""
    audit.record("admin", "bot.start", "bot", "currency")
    audit.record("operator", "ad.assign", "ad", "ad_1")
    audit.record("admin", "bot.stop", "bot", "qrgen")

    assert len(audit.query(action="bot.")) == 2
    assert len(audit.query(actor="admin")) == 2
    assert len(audit.query(target_id="qrgen")) == 1
    assert audit.count() == 3


def test_query_is_newest_first(cc_db):
    """الترتيب من الأحدث إلى الأقدم"""
    audit.record("a", "one")
    audit.record("a", "two")
    entries = audit.query(limit=10)
    assert entries[0]["action"] == "two"


def test_stats(cc_db):
    """الإحصاءات تعكس ما سُجل"""
    audit.record("admin", "bot.start")
    audit.record("admin", "bot.start")
    audit.record("viewer", "bot.list")

    stats = audit.stats()
    assert stats["total"] == 3
    assert stats["by_action"]["bot.start"] == 2
    assert stats["by_actor"]["admin"] == 2


def test_record_never_raises_without_db(monkeypatch):
    """التسجيل لا يرمي استثناءات عند تعطّل القاعدة"""
    import control_center.audit as audit_module
    monkeypatch.setattr(audit_module, "get_db", lambda: None)
    assert audit.record("admin", "bot.start") == -1
    assert audit.query() == []
    assert audit.count() == 0


def test_details_are_serialised_safely(cc_db):
    """التفاصيل غير القابلة للتسلسل لا تُسقط العملية"""
    class Weird:
        def __repr__(self):
            return "<weird>"

    row_id = audit.record("admin", "test", details={"obj": Weird()})
    assert row_id > 0
    entries = audit.query(limit=1)
    assert entries[0]["details"]
