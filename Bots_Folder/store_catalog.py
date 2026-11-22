# -*- coding: utf-8 -*-
"""
Bots_Folder/store_catalog.py — الكتالوج المشترك لمتجر بودة.

مصدر واحد لـ:
  • ترتيب الفئات وأسماؤها وأيقوناتها.
  • استبعاد بوت المتجر نفسه من قوائم المتجر (مع بقاء المتجر يعمل).
  • ترتيب البوتات بشكل ثابت (order) بدل الاعتماد على ترتيب الملف.

يُستخدم من:
  • Bots_Folder/bot_store.py      (بوت تيليجرام)
  • tools/build_mini_apps.py      (متجر الويب + catalog.json)
"""
from __future__ import annotations

from typing import Iterable, List, Dict

STORE_BOT_ID = "store"

# ترتيب الفئات في الواجهتين — ثابت ومقصود.
CATEGORY_ORDER = ["daily", "design", "media", "learn", "fun", "health", "business"]

CATEGORY_META: Dict[str, Dict[str, str]] = {
    "daily": {
        "name": "أدوات يومية",
        "icon": "🛠️",
        "desc": "أدوات عملية تنجز مهامك اليومية بسرعة: تحويل العملات، رموز QR، الصيغ، الطقس، والتذكيرات.",
    },
    "design": {
        "name": "صور وتصميم",
        "icon": "🎨",
        "desc": "أدوات الذكاء الاصطناعي لتحسين الصور، إزالة الخلفيات، صناعة الملصقات، واستخراج الألوان.",
    },
    "media": {
        "name": "فيديو وصوت",
        "icon": "🎬",
        "desc": "تحميل ومعالجة الفيديو والصوت: تيك توك نظيف، إزالة الصمت، وتحويل النص إلى صوت.",
    },
    "learn": {
        "name": "تعلّم واختبارات",
        "icon": "🧠",
        "desc": "ترجمة، تحليل شخصية، اختبارات ذكاء وألغاز توسّع معرفتك وتختبر قدراتك.",
    },
    "fun": {
        "name": "ترفيه وتسلية",
        "icon": "🎪",
        "desc": "أسماء موازية، قرارات عشوائية، توافق عاطفي، وعمر عقلي — جرعة ترفيه يومية.",
    },
    "health": {
        "name": "صحة ورشاقة",
        "icon": "💪",
        "desc": "حاسبات ومتابعة صحية بسيطة تساعدك على فهم وزنك وسعراتك واتخاذ خطوات أفضل.",
    },
    "business": {
        "name": "أمان وأعمال",
        "icon": "🔐",
        "desc": "حماية حساباتك، تنظيم ملاحظاتك، بناء سيرتك الذاتية، ومتابعة العملات الرقمية.",
    },
}

_DEFAULT_CATEGORY = "daily"


def bot_category_key(bot: dict) -> str:
    """مفتاح الفئة لبوت، مع fallback آمن."""
    key = (bot.get("category_key") or "").strip()
    return key if key in CATEGORY_META else _DEFAULT_CATEGORY


def is_store_bot(bot: dict) -> bool:
    """هل هذا هو بوت المتجر نفسه؟"""
    return (bot.get("id") or "").strip() == STORE_BOT_ID


def is_store_visible(bot: dict) -> bool:
    """هل يظهر البوت داخل قوائم المتجر؟"""
    if not bot.get("id") or is_store_bot(bot):
        return False
    if bot.get("hidden_from_store"):
        return False
    return True


def visible_bots(bots: Iterable[dict]) -> List[dict]:
    """كل البوتات الظاهرة في المتجر، مرتبة ترتيباً ثابتاً."""
    items = [b for b in bots if is_store_visible(b)]
    return sorted(items, key=lambda b: (int(b.get("order", 9999) or 9999),
                                        str(b.get("name", ""))))


def featured_bots(bots: Iterable[dict], limit: int = 8) -> List[dict]:
    """البوتات المميزة (ثم استكمالها بالأوائل عند الحاجة)."""
    visible = visible_bots(bots)
    picks = [b for b in visible if b.get("featured")]
    if len(picks) < limit:
        seen = {b.get("id") for b in picks}
        picks += [b for b in visible if b.get("id") not in seen]
    return picks[:limit]


def category_list(bots: Iterable[dict]) -> List[dict]:
    """الفئات التي تحتوي بوتات ظاهرة فقط، بترتيب CATEGORY_ORDER."""
    visible = visible_bots(bots)
    counts: Dict[str, int] = {}
    for bot in visible:
        key = bot_category_key(bot)
        counts[key] = counts.get(key, 0) + 1

    out: List[dict] = []
    for key in CATEGORY_ORDER:
        if not counts.get(key):
            continue
        meta = CATEGORY_META[key]
        out.append({
            "key": key,
            "name": meta["name"],
            "icon": meta["icon"],
            "desc": meta["desc"],
            "count": counts[key],
        })
    return out


def category_meta(key: str) -> dict:
    """بيانات فئة واحدة مع مفتاحها."""
    meta = CATEGORY_META.get(key, CATEGORY_META[_DEFAULT_CATEGORY])
    return {"key": key if key in CATEGORY_META else _DEFAULT_CATEGORY, **meta}


def bots_in_category(bots: Iterable[dict], key: str) -> List[dict]:
    """بوتات فئة واحدة مرتبة."""
    return [b for b in visible_bots(bots) if bot_category_key(b) == key]


def get_bot(bots: Iterable[dict], bot_id: str) -> dict | None:
    """البحث عن بوت ظاهر بالمعرّف."""
    for bot in visible_bots(bots):
        if bot.get("id") == bot_id:
            return bot
    return None


def search_bots(bots: Iterable[dict], query: str, limit: int = 12) -> List[dict]:
    """بحث بسيط في الاسم والوصف والمميزات والمعرّف."""
    q = (query or "").strip().lower()
    if not q:
        return []
    results: List[dict] = []
    for bot in visible_bots(bots):
        haystack = " ".join([
            str(bot.get("name", "")),
            str(bot.get("short_desc", "")),
            str(bot.get("description", "")),
            str(bot.get("username", "")),
            str(bot.get("category", "")),
            " ".join(str(x) for x in (bot.get("features") or [])),
        ]).lower()
        if q in haystack:
            results.append(bot)
        if len(results) >= limit:
            break
    return results
