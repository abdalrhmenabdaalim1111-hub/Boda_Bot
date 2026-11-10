"""
tests/test_i18n.py — اختبار طبقة الترجمة الموحدة (عربي/إنجليزي)

يغطي: التطبيع (ar-SA→ar)، الترجمة المباشرة، التسلسل الاحتياطي إلى العربية،
المفاتيح الناقصة، تغيير اللغة الافتراضية، وتوازن المفاتيح بين اللغات.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BOTS_DIR = ROOT / "Bots_Folder"
for _p in (str(ROOT), str(BOTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import i18n  # noqa: E402


def setup_function(function):
    """ضمان عودة اللغة الافتراضية إلى العربية بعد كل اختبار يغيّرها."""
    i18n.set_default_lang("ar")


def test_normalize_lang_codes():
    assert i18n.normalize_lang("ar-SA") == "ar"
    assert i18n.normalize_lang("ar") == "ar"
    assert i18n.normalize_lang("en-GB") == "en"
    assert i18n.normalize_lang("EN") == "en"
    assert i18n.normalize_lang("") == i18n.current_default_lang()
    assert i18n.normalize_lang(None) == i18n.current_default_lang()
    # لغة غير مدعومة → الافتراضية
    assert i18n.normalize_lang("fr-FR") == "ar"


def test_translate_ar_en():
    assert i18n.t("welcome", "ar") == "أهلاً بك! 👋"
    assert i18n.t("welcome", "en") == "Welcome! 👋"
    assert i18n.t("store_button", "en") == "🏪 App Store"
    assert i18n.t("store_button", "ar") == "🏪 متجر التطبيقات"


def test_fallback_to_arabic_when_lang_missing_key():
    """مفتاح موجود بالعربية فقط → يُسقط للعربية حتى بلغة أخرى."""
    i18n.STRINGS["ar"]["ab_only_ar_key"] = "نص عربي فقط"
    try:
        assert i18n.t("ab_only_ar_key", "en") == "نص عربي فقط"
    finally:
        i18n.STRINGS["ar"].pop("ab_only_ar_key")


def test_missing_key_uses_passed_default_then_key():
    assert i18n.t("definitely_missing_key_xyz") == "definitely_missing_key_xyz"
    assert i18n.t("definitely_missing_key_xyz", "en") == "definitely_missing_key_xyz"
    assert i18n.t("definitely_missing_key_xyz", "en", default="بديل") == "بديل"


def test_set_default_lang():
    i18n.set_default_lang("en")
    assert i18n.current_default_lang() == "en"
    assert i18n.normalize_lang("fr") == "en"          # غير معروفة → الافتراضية الجديدة
    assert i18n.t("welcome") == "Welcome! 👋"          # بلا صراحة اللغة
    i18n.set_default_lang("ar")
    assert i18n.t("welcome") == "أهلاً بك! 👋"


def test_available_langs_and_key_parity():
    langs = i18n.available_langs()
    assert "ar" in langs and "en" in langs
    translated = i18n.to_dict()
    # توازن المفاتيح: أي مفتاح مترجم بلغة يجب أن يُترجم بكل اللغات
    assert set(translated["ar"].keys()) == set(translated["en"].keys())
    assert len(translated["ar"]) >= 10
