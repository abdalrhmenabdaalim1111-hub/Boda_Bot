"""
tests/test_ab_analytics.py — اختبار طبقة اختبار A/B للإعلانات

يغطي:
• تعيين ثابت للمستخدم (نفس المستخدم = نفس المجموعة دائماً) عبر compute_ab_variant
• توازن تقريبي 50/50 على عيّنة مستخدمين (md5 ثابت بلا حس للترتيب)
• record_ab_event: ظهور/نقرة يومية لكل (بوت، صيغة، مجموعة) والنقرة لا تزيد الظهور
• تقرير get_ab_report: تجميع لكل مجموعة + تفصيل لكل بوت + CTR معقول
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BOTS_DIR = ROOT / "Bots_Folder"
for _p in (str(ROOT), str(BOTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ad_manager  # noqa: E402
import database    # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """قاعدة بيانات معزولة داخل tmp_path (بدون لمس بيانات الإنتاج)."""
    monkeypatch.setenv("BODA_DB_PATH", str(tmp_path / "ab.db"))
    database.BodaDatabase.reset_instance()
    db = database.get_db()
    yield db
    database.BodaDatabase.reset_instance()


@pytest.fixture()
def mgr(tmp_path):
    """مدير إعلانات معزول بملفات تهيئة مؤقتة (نمط test_ad_manager المعتمد)."""
    cfg_file = tmp_path / "ads_ab.json"
    mon_file = tmp_path / "monetag_ab.json"
    cfg_file.write_text('{"enabled": true}', encoding="utf-8")
    mon_file.write_text('{"_version": "1.0", "global_default": {}, "bots": {}}',
                        encoding="utf-8")
    return ad_manager.AdManager(config_file=cfg_file, monetag_file=mon_file)


# ── التعيين الثابت ────────────────────────────────────────────────────────────

def test_variant_is_stable_per_user():
    f = ad_manager.AdManager.compute_ab_variant
    for uid in (1, 42, 999_999, 123_456_789):
        assert f(uid) == f(uid)                 # ثابت عبر الاستدعاءات
        assert f(uid) in ("A", "B")


def test_variant_balance_approx_50_50():
    f = ad_manager.AdManager.compute_ab_variant
    counts = {"A": 0, "B": 0}
    for uid in range(1, 401):
        counts[f(uid)] += 1
    # على 400 مستخدم: كل مجموعة 30-70% (التجزئة md5 موزعة بعيدة جدًا عن الحواف)
    assert 120 <= counts["A"] <= 280
    assert 120 <= counts["B"] <= 280
    assert counts["A"] + counts["B"] == 400


def test_variant_independent_of_registry_state(db):
    """التعيين دالة في user_id فقط — لا يقرأ قاعدة البيانات ولا يعتمد على التسجيل."""
    f = ad_manager.AdManager.compute_ab_variant
    assert f(777) == f(777) == f(777)


# ── تسجيل الأحداث والتقرير ────────────────────────────────────────────────────

def test_record_view_and_click_flow(db, mgr):
    variant = ad_manager.AdManager.compute_ab_variant(101)
    other = "B" if variant == "A" else "A"

    mgr.record_ab_view("bot_currency", 101, "direct_link")
    mgr.record_ab_view("bot_currency", 101, "direct_link")   # ظهور ثانٍ
    mgr.record_ab_click("bot_currency", 101, "direct_link")  # نقرة واحدة

    report = db.get_ab_report()
    side = report["variants"][variant]
    assert side["impressions"] == 2
    assert side["clicks"] == 1
    assert side["ctr_percent"] == 50.0
    # المجموعة الأخرى لم تسجل شيئاً
    assert report["variants"][other]["impressions"] == 0
    assert report["variants"][other]["clicks"] == 0


def test_click_does_not_add_impression(db, mgr):
    """النقرة وحدها (بدون ظهور) تزيد نقرات فقط — اتساق مع عدّاد Monetag."""
    variant = ad_manager.AdManager.compute_ab_variant(55)
    mgr.record_ab_click("bot_store", 55, "direct_link")
    mgr.record_ab_click("bot_store", 55, "direct_link")
    report = db.get_ab_report()
    assert report["variants"][variant]["clicks"] == 2
    assert report["variants"][variant]["impressions"] == 0


def test_per_bot_report_sorted_and_clean(db, mgr):
    """تقرير لكل بوت: مجاميع صحيحة ورتّب تنازلي وCTR غير سالب."""
    mgr.record_ab_view("bot_currency", 7)
    mgr.record_ab_view("bot_currency", 8)
    mgr.record_ab_view("bot_videodl", 7)
    mgr.record_ab_view("bot_videodl", 7)
    mgr.record_ab_view("bot_videodl", 9)          # إجمالي 3 لتفريق الأعداد
    report = db.get_ab_report()
    rows = report["per_bot"]
    assert all(r["ctr_percent"] >= 0 for r in rows)
    assert report["days"] == 30
    # المجاميع لكل بوت مستقلة عن تقسيم المجموعات (videodl قد ينقسم بين A/B)
    totals: dict = {}
    for r in rows:
        totals[r["bot_name"]] = totals.get(r["bot_name"], 0) + r["impressions"]
    assert totals == {"videodl": 3, "currency": 2}
    # الترتيب تنازلي حسب الظهور (بلا تعادل يعد الأسماء)
    imps = [r["impressions"] for r in rows]
    assert imps == sorted(imps, reverse=True)


def test_report_groups_both_variants(db, mgr):
    """مستخدمان بمجموعتين مختلفتين يظهران في تدقيق المجموعات."""
    seen = set()
    for uid in range(1, 60):
        mgr.record_ab_view("bot_currency", uid)
        seen.add(ad_manager.AdManager.compute_ab_variant(uid))
    assert seen == {"A", "B"}          # العينة تكفي لظهور المجموعتين
    report = db.get_ab_report()
    a, b = report["variants"]["A"], report["variants"]["B"]
    assert a["impressions"] + b["impressions"] == 59   # 59 مستخدم فريد
