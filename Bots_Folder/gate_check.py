# -*- coding: utf-8 -*-
"""
Bots_Folder/gate_check.py — المصدر الوحيد لبوابة الاشتراك الإجبارية.

القناتان المطلوبتان فقط:
    1) @Stick_boda
    2) @ebdo_4

- التحقق يتم عبر بوت الفحص (BOT_GATE_CHECKER_TOKEN) أو بوت المتجر كاحتياطي.
- فشل الشبكة/الصلاحيات = فشل مفتوح (لا نحجب المستخدمين بسبب عطل البنية).
- كاش قصير (30 ثانية) حتى يُعاد الفحص بسرعة إذا ألغى المستخدم اشتراكه.
"""
import os
import time
import logging
import threading
from pathlib import Path
from typing import List, Dict

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

log = logging.getLogger("GateCheck")

# ── القناتان الإجباريتان فقط ─────────────────────────────────────────────────
CHANNELS: List[Dict[str, str]] = [
    {
        "username": "Stick_boda",
        "title": "قناة بودة",
        "url": "https://t.me/Stick_boda",
    },
    {
        "username": "ebdo_4",
        "title": "قناة عبده",
        "url": "https://t.me/ebdo_4",
    },
]

CACHE_TTL = int(os.getenv("BODA_GATE_CACHE_TTL", "30") or 30)
_cache: Dict[int, tuple] = {}
_lock = threading.Lock()


def gate_enabled() -> bool:
    """البوابة مفعّلة افتراضياً. يمكن تعطيلها مؤقتاً بـ BODA_SUB_GATE=0."""
    return os.getenv("BODA_SUB_GATE", "1").strip().lower() not in ("0", "false", "no", "off")


def _checker_token() -> str:
    token = (os.getenv("BOT_GATE_CHECKER_TOKEN") or "").strip()
    if token:
        return token
    # احتياطي: بوت المتجر أدمن في القناتين
    return (os.getenv("BOT_STORE_TOKEN") or "").strip()


def _get_status(user_id: int, username: str, token: str):
    """يرجع حالة العضوية، أو None عند أي خطأ بنيوي (فشل مفتوح)."""
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getChatMember",
            params={"chat_id": f"@{username}", "user_id": user_id},
            timeout=8,
        )
        data = resp.json()
    except Exception as exc:
        log.warning("gate network error on @%s: %s", username, exc)
        return None

    if data.get("ok"):
        return data["result"].get("status", "left")

    desc = (data.get("description") or "").lower()
    log.warning("gate API error on @%s (user %s): %s", username, user_id, desc)
    return None


def get_missing_channels(user_id: int, use_cache: bool = True) -> List[Dict[str, str]]:
    """قائمة القنوات التي لم يشترك بها المستخدم (فارغة = مسموح)."""
    if not gate_enabled():
        return []

    now = time.time()
    if use_cache:
        with _lock:
            hit = _cache.get(user_id)
        if hit and hit[0] > now:
            return hit[1]

    token = _checker_token()
    if not token:
        log.error("gate checker token missing -> fail-open")
        return []

    missing: List[Dict[str, str]] = []
    for channel in CHANNELS:
        status = _get_status(user_id, channel["username"], token)
        if status is None:
            continue  # فشل مفتوح لهذه القناة
        if status in ("left", "kicked"):
            missing.append(channel)

    with _lock:
        _cache[user_id] = (now + CACHE_TTL, missing)
    return missing


def is_subscribed(user_id: int, use_cache: bool = True) -> bool:
    """True إذا كان المستخدم مشتركاً في القناتين (أو البوابة معطّلة)."""
    return not get_missing_channels(user_id, use_cache=use_cache)


def invalidate(user_id: int) -> None:
    """مسح الكاش بعد ضغط زر التحقق لإعادة الفحص فوراً."""
    with _lock:
        _cache.pop(user_id, None)


def gate_text(missing: List[Dict[str, str]]) -> str:
    lines = [
        "🔐 <b>أنت لست مشتركاً بالقناتين المطلوبتين:</b>",
        "",
    ]
    for i, channel in enumerate(missing, start=1):
        lines.append(f"{i}️⃣ <b>{channel['title']}</b> — @{channel['username']}")
    lines += [
        "",
        "اشترك ثم اضغط <b>«تحقق من الاشتراك»</b> لفتح كل البوتات ✅",
        "⏳ سنُعيد الفحص فوراً بعد التحقق.",
    ]
    return "\n".join(lines)


def gate_markup(missing: List[Dict[str, str]]):
    """أزرار القنوات + زر التحقق (يتطلب telebot)."""
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

    markup = InlineKeyboardMarkup(row_width=1)
    for channel in missing:
        markup.add(InlineKeyboardButton(
            f"📺 {channel['title']}",
            url=channel["url"],
        ))
    markup.add(InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="gate_verify"))
    return markup
