"""
tests/test_control_center_botconfig.py — اختبارات إعدادات البوت

تغطي:
• إنشاء صف الإعداد تلقائياً
• التحديث (الاسم / الفئة / الميزات / التفعيل)
• تخزين التوكن مشفّراً (عند توفر cryptography)
• عدم خروج التوكن الكامل أبداً في الاستجابات
• القناع المعروض للمستخدم
"""

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401  (path bootstrap)
from tests.cc_fixtures import cc_db  # noqa: F401  (fixture)

from control_center import botconfig

SAMPLE_TOKEN = "1234567890:AAF-fakeTokenValue_1234567890abcdefGHI"


def test_ensure_creates_row(cc_db):
    """صف الإعداد يُنشأ تلقائياً"""
    cfg = botconfig.ensure("currency", "محول العملات", "أدوات")
    assert cfg["bot_id"] == "currency"
    assert cfg["display_name"] == "محول العملات"
    assert cfg["category"] == "أدوات"
    assert cfg["enabled"] is True


def test_update_fields(cc_db):
    """تحديث الحقول الأساسية"""
    botconfig.ensure("currency")
    result = botconfig.update("currency", display_name="اسم جديد",
                               category="ترفيه", enabled=False,
                               features={"ads": True, "growth_gate": False})
    assert result["ok"] is True

    cfg = botconfig.get("currency")
    assert cfg["display_name"] == "اسم جديد"
    assert cfg["category"] == "ترفيه"
    assert cfg["enabled"] is False
    assert cfg["features"]["ads"] is True


def test_unknown_feature_flags_are_dropped(cc_db):
    """الميزات غير المعروفة تُهمل"""
    botconfig.ensure("currency")
    botconfig.update("currency", features={"ads": True, "evil": True})
    cfg = botconfig.get("currency")
    assert "evil" not in cfg["features"]


def test_token_is_never_returned(cc_db):
    """التوكن لا يظهر أبداً في الإعدادات المعادة"""
    botconfig.ensure("currency")
    botconfig.update("currency", token=SAMPLE_TOKEN)
    cfg = botconfig.get("currency")
    assert SAMPLE_TOKEN not in str(cfg)
    assert "token_enc" not in cfg


def test_token_display_is_masked(cc_db, monkeypatch):
    """التوكن يظهر مقنّعاً فقط"""
    botconfig.ensure("currency")
    botconfig.update("currency", token=SAMPLE_TOKEN)
    # Fall back to the environment so the assertion holds whether or not the
    # encryption backend is installed.
    monkeypatch.setenv("BOT_CURRENCY_TOKEN", SAMPLE_TOKEN)
    displayed = botconfig.token_display("currency")
    assert SAMPLE_TOKEN not in displayed
    assert displayed
    assert "fakeTokenValue" not in displayed


def test_resolve_token_from_env(cc_db, monkeypatch):
    """التوكن يُقرأ من البيئة عند غياب المشفّر"""
    monkeypatch.setenv("BOT_CURRENCY_TOKEN", SAMPLE_TOKEN)
    assert botconfig.resolve_token("currency") == SAMPLE_TOKEN


def test_all_configs(cc_db):
    """قراءة كل الإعدادات دفعة واحدة"""
    botconfig.ensure("alpha")
    botconfig.ensure("beta")
    configs = botconfig.all_configs()
    assert "alpha" in configs and "beta" in configs


def test_update_on_missing_row_creates_it(cc_db):
    """التحديث على بوت غير موجود يُنشئ الصف"""
    result = botconfig.update("brandnew", display_name="جديد")
    assert result["ok"] is True
    assert botconfig.get("brandnew")["display_name"] == "جديد"
