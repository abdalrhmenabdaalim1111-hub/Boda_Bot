"""
Bots_Folder/i18n.py — طبقة ترجمة موحدة لكل البوتات (عربي وإنجليزي كبداية)

الفكرة:
    نص المفتاح مرة واحدة في قاموس STRINGS لكل لغة، ثم في أي بوت:
        from i18n import t
        t("welcome", lang="en")
    • اللغة الافتراضية "ar" (متغيرة عبر set_default_lang أو البيئة BODA_DEFAULT_LANG)
    • مفتاح ناقص في لغة ما → يُسقط تلقائياً إلى العربية → ثم إلى الافتراض
    • إضافة لغة جديدة = إضافة قسم في STRINGS فقط (الوظائف ثابتة)

لكل بوت اختيار لغة المستخدم الواردة من update.from_user.language_code:
    lang = (language_code or "ar")[:2]
"""
import os
from typing import Optional, Dict, Any, Tuple

LANGUAGES: Tuple[str, ...] = ("ar", "en")
_default_lang = os.getenv("BODA_DEFAULT_LANG", "ar").strip().lower() or "ar"
if _default_lang not in LANGUAGES:
    _default_lang = "ar"

STRINGS: Dict[str, Dict[str, str]] = {
    "ar": {
        "welcome": "أهلاً بك! 👋",
        "menu": "القائمة",
        "back": "رجوع",
        "choose_language": "اختر لغتك:",
        "language_changed": "تم تغيير اللغة ✅",
        "network_gate": "فعّل شبكة البوتات (5 خطوات) لفتح كامل الميزات:",
        "network_done": "شبكة البوتات مفعّلة 🎉",
        "sponsor_button": "📢 زوّر راعينا",  # noqa: E501 button label
        "store_button": "🏪 متجر التطبيقات",
        "app_card": "افتح التطبيق",
        "referral_link": "رابط الدعوة الخاص بك",
        "vip_reward": "🌟 عضوية VIP",
        "error_generic": "حدث خطأ ما، حاول مرة أخرى.",
    },
    "en": {
        "welcome": "Welcome! 👋",
        "menu": "Menu",
        "back": "Back",
        "choose_language": "Choose your language:",
        "language_changed": "Language changed ✅",
        "network_gate": "Activate the bot network (5 steps) to unlock features:",
        "network_done": "Bot network activated 🎉",
        "sponsor_button": "📢 Visit our sponsor",
        "store_button": "🏪 App Store",
        "app_card": "Open App",
        "referral_link": "Your referral link",
        "vip_reward": "🌟 VIP membership",
        "error_generic": "Something went wrong, please try again.",
    },
}


def normalize_lang(lang: Optional[str]) -> str:
    """تطبيع رمز لغة المستخدم (مثل ar-SA → ar) مع تجاهل غير المعروفة"""
    candidate = (lang or "").strip().lower()
    if not candidate:
        return _default_lang
    code = candidate.split("-")[0][:2]
    return code if code in LANGUAGES else _default_lang


def t(key: str, lang: Optional[str] = None, default: Optional[str] = None) -> str:
    """
    ترجمة مفتاح مع تسلسل احتياطي: اللغة المطلوبة → العربية → نص التمرير → المفتاح.
    """
    code = normalize_lang(lang)
    return (STRINGS.get(code, {}).get(key)
            or STRINGS.get("ar", {}).get(key)
            or (default if default is not None else key))


def set_default_lang(lang: str) -> None:
    """ضبط اللغة الافتراضية للنظام (كومي للبوتات التي تبدأ بالإنجليزية مثلاً)."""
    global _default_lang
    code = normalize_lang(lang)
    if code in LANGUAGES:
        _default_lang = code


def current_default_lang() -> str:
    return _default_lang


def available_langs() -> Tuple[str, ...]:
    return LANGUAGES


def to_dict() -> Dict[str, Any]:
    """نسخة من كل الترجمات (لحقنها في صفحات الويب أو الاختبارات)."""
    return {lang: dict(strings) for lang, strings in STRINGS.items()}
