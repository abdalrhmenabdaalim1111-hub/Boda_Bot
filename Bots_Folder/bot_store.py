# -*- coding: utf-8 -*-
"""
Bots_Folder/bot_store.py — متجر تطبيقات بودة (الدليل الرسمي للبوتات).

البوابة الإجبارية: @Stick_boda + @ebdo_4 فقط.
بوت المتجر نفسه لا يظهر داخل قائمة المتجر (hidden_from_store).
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from urllib.parse import quote

import telebot
from telebot import types

from Bots_Folder.bot_base import get_token, start_bot
from Bots_Folder.gate_middleware import GateMiddleware
from Bots_Folder.store_catalog import (
    category_list,
    category_meta,
    bots_in_category,
    featured_bots,
    get_bot,
    search_bots,
    visible_bots,
)

try:
    from Bots_Folder import gate_check
except ImportError:  # تشغيل مباشر من داخل Bots_Folder
    import gate_check

TOKEN = get_token("BOT_STORE_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
gate = GateMiddleware(bot, "store")

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "bots_registry.json"
with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
    BOTS = json.load(f)

VISIBLE = visible_bots(BOTS)
CATEGORIES = category_list(BOTS)
FEATURED = featured_bots(BOTS, 8)

# رابط متجر الويب — من .env أو GitHub Pages كاحتياطي آمن.
_WEB_BASE = os.getenv("MINIAPPS_BASE_URL", "").strip().rstrip("/")
if not _WEB_BASE:
    _WEB_BASE = "https://abdalrhmenabdaalim1111-hub.github.io/Boda_Bot"
WEB_STORE_URL = f"{_WEB_BASE}/store/"

CHANNEL_STICK = "https://t.me/Stick_boda"
CHANNEL_EBDU = "https://t.me/ebdo_4"

WELCOME = (
    "🏪 <b>متجر تطبيقات بودة</b>\n"
    "────────────────────\n"
    "منصة واحدة تجمع <b>{count} بوتاً وتطبيقاً</b> في <b>{cats} فئات</b>.\n"
    "أدوات ذكية، صور، فيديو، ترجمة، صحة، ترفيه… وكلها <b>بدون إعلانات</b>.\n\n"
    "اختر فئة، أو استخدم البحث للوصول السريع لما تحتاجه."
)


def esc(value) -> str:
    """تهريب آمن لنصوص HTML داخل رسائل تيليجرام."""
    return html.escape(str(value or ""), quote=False)


def bot_url(bot_data: dict) -> str:
    url = (bot_data.get("url") or "").strip()
    if url:
        return url
    username = (bot_data.get("username") or "").lstrip("@")
    return f"https://t.me/{username}" if username else "https://t.me/BodaStoreeBot"


def web_app_url(bot_data: dict) -> str:
    return f"{_WEB_BASE}/{bot_data.get('id', '')}/"


def share_url(bot_data: dict) -> str:
    name = bot_data.get("name", "بوت بودة")
    short = bot_data.get("short_desc", "")
    text = f"جرّب {name} — {short}".strip(" —")
    return f"https://t.me/share/url?url={quote(bot_url(bot_data), safe='')}&text={quote(text, safe='')}"


def _stats() -> tuple[dict, int, list]:
    """إحصاءات المستخدمين من قاعدة البيانات (best-effort)."""
    try:
        from Bots_Folder.database import BodaDatabase
        db = BodaDatabase.get_instance()
        counts = db.get_bot_user_counts()
        total = sum(int(v or 0) for v in counts.values())
        usage: dict = {}
        try:
            with db._get_conn() as conn:
                rows = conn.execute(
                    "SELECT bot_name, SUM(usage_count) AS s FROM users GROUP BY bot_name"
                ).fetchall()
                for r in rows:
                    usage[r["bot_name"]] = int(r["s"] or 0)
        except Exception:
            pass
        top = sorted(
            counts.items(),
            key=lambda x: int(usage.get(x[0], int(x[1] or 0)) or 0), reverse=True
        )[:5]
        return counts, total, top, usage
    except Exception:
        return {}, 0, [], {}


def _main_markup() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⭐ البوتات المميزة", callback_data="featured"),
        types.InlineKeyboardButton("🔥 الأكثر استخداماً", callback_data="top"),
    )
    markup.add(
        types.InlineKeyboardButton("🔍 بحث عن بوت", callback_data="search"),
        types.InlineKeyboardButton("📊 إحصائيات", callback_data="stats"),
    )
    for cat in CATEGORIES:
        markup.add(types.InlineKeyboardButton(
            f"{cat['icon']} {cat['name']} ({cat['count']})",
            callback_data=f"cat:{cat['key']}",
        ))
    markup.add(
        types.InlineKeyboardButton("🔐 حالة الاشتراك", callback_data="check_sub"),
        types.InlineKeyboardButton("💬 الدعم", url="https://t.me/BodaStoreeBot"),
    )
    markup.add(types.InlineKeyboardButton("🌐 المتجر على الويب", url=WEB_STORE_URL))
    markup.add(
        types.InlineKeyboardButton("📣 قناة بودة", url=CHANNEL_STICK),
        types.InlineKeyboardButton("📣 قناة عبده", url=CHANNEL_EBDU),
    )
    return markup


def send_store_menu(chat_id: int, edit_message_id: int | None = None):
    text = WELCOME.format(count=len(VISIBLE), cats=len(CATEGORIES))
    markup = _main_markup()
    if edit_message_id:
        try:
            bot.edit_message_text(text, chat_id, edit_message_id, reply_markup=markup)
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, reply_markup=markup)


def _blocked(call) -> bool:
    """فحص البوابة داخل أزرار الكولباك (فحص فوري بدون كاش)."""
    user = getattr(call, "from_user", None)
    if not user:
        return True
    chat_id = getattr(getattr(call, "message", None), "chat", None)
    chat_id = getattr(chat_id, "id", None) or user.id
    lang = (getattr(user, "language_code", "") or "ar").lower()
    blocked = gate.check_user(user.id, chat_id, lang, use_cache=False)
    if blocked:
        try:
            bot.answer_callback_query(
                call.id,
                "🔐 اشترك في القناتين ثم اضغط «تحقق من الاشتراك».",
                show_alert=True,
            )
        except Exception:
            pass
    return blocked


def _safe_edit(call, text: str, markup) -> None:
    chat_id = call.message.chat.id
    try:
        bot.edit_message_text(
            text, chat_id, call.message.message_id, reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception:
        bot.send_message(chat_id, text, reply_markup=markup,
                         disable_web_page_preview=True)


@bot.message_handler(commands=["featured"])
def cmd_featured(message):
    if gate.check_and_show_gate(message):
        return
    # reuse show_featured logic by creating a fake call? Instead, send featured list directly.
    text = "⭐ <b>اختيارات فريق بودة</b>\n\nبوتات مميزة تجمع بين الفائدة وسهولة الاستخدام:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in FEATURED:
        markup.add(types.InlineKeyboardButton(
            f"{b.get('emoji', '🤖')} {b.get('name', b.get('id', ''))}",
            callback_data=f"bot:{b['id']}",
        ))
    markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))
    bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.message_handler(commands=["top"])
def cmd_top(message):
    if gate.check_and_show_gate(message):
        return
    counts, total, top = _stats()
    text = "🔥 <b>الأكثر استخداماً</b>\n\n"
    if top:
        for i, (bot_id, users) in enumerate(top, start=1):
            b = next((x for x in VISIBLE if x.get("id") == bot_id), None)
            name = b.get("name") if b else bot_id
            emoji = b.get("emoji", "🤖") if b else "🤖"
            text += f"{i}. {emoji} {esc(name)} — {int(users or 0):,} مستخدم\n"
    else:
        text = "لا توجد بيانات كافية بعد."
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["stats"])
def cmd_stats(message):
    if gate.check_and_show_gate(message):
        return
    counts, total, top = _stats()
    text = (
        "📊 <b>إحصائيات منصة بودة</b>\n"
        "────────────────────\n"
        f"🤖 البوتات: {len(VISIBLE)}\n"
        f"📂 الفئات: {len(CATEGORIES)}\n"
        f"👥 المستخدمون: {total:,}\n"
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=["start", "menu", "help", "about"])
def send_welcome(message) -> None:
    if gate.check_and_show_gate(message, use_cache=False):
        return
    cmd = (message.text or "").split()[0].lower()
    if cmd in ("/help", "/about"):
        text = (
            "🏪 <b>متجر تطبيقات بودة — المساعدة</b>\n"
            "────────────────────\n"
            "• /start أو /menu — القائمة الرئيسية\n"
            "• /featured — البوتات المميزة\n"
            "• /top — الأكثر استخداماً\n"
            "• /stats — إحصائيات المنصة\n"
            "• /search <كلمة> — بحث (أو استخدم زر البحث)\n\n"
            "🔐 <b>الاشتراك الإجباري:</b> للوصول إلى أي بوت، اشترك في "
            "@Stick_boda و @ebdo_4، ثم اضغط «تحقق من الاشتراك».\n\n"
            "💬 الدعم: @BodaStoreeBot"
        )
        bot.send_message(message.chat.id, text, disable_web_page_preview=True)
        return
    send_store_menu(message.chat.id)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def unknown_text(message):
    if gate.check_and_show_gate(message):
        return
    text = (message.text or "").strip()
    if text.startswith("/search "):
        handle_search(message)
        return
    if text.startswith("/"):
        bot.send_message(
            message.chat.id,
            "❓ أمر غير معروف. استخدم /help لعرض الأوامر المتاحة.",
        )
        return
    # treat any non-command text as search
    handle_search(message)


@bot.callback_query_handler(func=lambda call: call.data == "back_main")
def back_main(call) -> None:
    if _blocked(call):
        return
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    send_store_menu(call.message.chat.id)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "featured")
def show_featured(call) -> None:
    if _blocked(call):
        return
    text = "⭐ <b>اختيارات فريق بودة</b>\n\nبوتات مميزة تجمع بين الفائدة وسهولة الاستخدام:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in FEATURED:
        markup.add(types.InlineKeyboardButton(
            f"{b.get('emoji', '🤖')} {b.get('name', b.get('id', ''))}",
            callback_data=f"bot:{b['id']}",
        ))
    markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))
    _safe_edit(call, text, markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "top")
def show_top(call):
    if _blocked(call):
        return
    counts, total, top, usage = _stats()
    text = "🔥 <b>الأكثر استخداماً في منصة بودة</b>\n\n"
    if top:
        for i, (bot_id, users) in enumerate(top, start=1):
            b = next((x for x in VISIBLE if x.get("id") == bot_id), None)
            name = b.get("name") if b else bot_id
            emoji = b.get("emoji", "🤖") if b else "🤖"
            cat = b.get("category", "") if b else ""
            uses = int(usage.get(bot_id, 0) or 0)
            text += (f"{i}. {emoji} <b>{esc(name)}</b> — {int(users or 0):,} مستخدم  ·  "
                     f"{esc(cat)}  ·  {uses:,} استخدام\n")
    else:
        text += "لا توجد بيانات كافية بعد — كن أول المستخدمين!"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for bot_id, _ in (top or []):
        b = next((x for x in VISIBLE if x.get("id") == bot_id), None)
        if b:
            markup.add(types.InlineKeyboardButton(
                f"{b.get('emoji', '🤖')} {b.get('name', bot_id)}",
                callback_data=f"bot:{bot_id}",
            ))
    markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))
    _safe_edit(call, text, markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: (call.data or "").startswith("cat:"))
def show_category(call) -> None:
    if _blocked(call):
        return
    key = (call.data or "").split(":", 1)[1]
    meta = category_meta(key)
    items = bots_in_category(BOTS, meta["key"])
    text = (
        f"{meta['icon']} <b>{esc(meta['name'])}</b>  ·  {len(items)} بوت\n"
        f"{esc(meta['desc'])}\n\n"
        "اختر البوت لعرض التفاصيل:"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in items:
        markup.add(types.InlineKeyboardButton(
            f"{b.get('emoji', '🤖')} {b.get('name', b.get('id', ''))}",
            callback_data=f"bot:{b['id']}",
        ))
    markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))
    _safe_edit(call, text, markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: (call.data or "").startswith("bot:"))
def show_bot(call) -> None:
    if _blocked(call):
        return
    bot_id = (call.data or "").split(":", 1)[1]
    b = get_bot(BOTS, bot_id)
    if not b:
        bot.answer_callback_query(call.id, "⚠️ هذا البوت غير متاح حالياً.", show_alert=True)
        return

    cat_key = b.get("category_key", "daily")
    cat_name = b.get("category") or category_meta(cat_key)["name"]
    cat_icon = b.get("category_icon") or category_meta(cat_key)["icon"]
    counts, _, _, usage = _stats()
    users = int(counts.get(b.get("id"), 0) or 0)
    uses = int(usage.get(b.get("id"), 0) or 0)

    lines = [
        f"{b.get('emoji', '🤖')} <b>{esc(b.get('name', b.get('id', '')))}</b>",
        f"{cat_icon} {esc(cat_name)}",
        "",
        esc(b.get("description", "")),
        "",
    ]
    features = b.get("features") or []
    if features:
        lines.append("<b>أبرز المميزات:</b>")
        lines.extend(f"• {esc(item)}" for item in features)
        lines.append("")
    if b.get("username"):
        lines.append(f"👤 <code>@{esc(str(b['username']).lstrip('@'))}</code>")
    lines.append(f"👥 {users:,} مستخدم" if users else "✨ جديد على المنصة")
    if uses:
        lines.append(f"🖱️ {uses:,} استخدام")
    lines.append(f"🧩 التطبيق المصغّر: <a href=\"{esc(web_app_url(b))}\">افتح في المتصفح</a>")

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🚀 افتح البوت في تيليجرام", url=bot_url(b)))
    markup.add(types.InlineKeyboardButton("📱 جرّب التطبيق المصغّر", url=web_app_url(b)))
    markup.add(types.InlineKeyboardButton("📤 شارك البوت", url=share_url(b)))
    markup.add(types.InlineKeyboardButton(
        f"🔙 رجوع إلى {cat_icon} {cat_name}", callback_data=f"cat:{cat_key}"))
    markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))

    _safe_edit(call, "\n".join(lines), markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "stats")
def show_stats(call) -> None:
    if _blocked(call):
        return
    counts, total, top, _usage = _stats()
    lines = [
        "📊 <b>إحصائيات منصة بودة</b>",
        "────────────────────",
        f"🤖 البوتات المتاحة: <b>{len(VISIBLE)}</b>",
        f"📂 الفئات: <b>{len(CATEGORIES)}</b>",
        f"👥 إجمالي المستخدمين المسجلين: <b>{total:,}</b>",
        "",
    ]
    if top:
        lines.append("<b>🏆 الأكثر استخداماً:</b>")
        for i, (bot_id, users) in enumerate(top, start=1):
            b = next((x for x in VISIBLE if x.get("id") == bot_id), None)
            name = b.get("name") if b else bot_id
            lines.append(f"{i}. {esc(name)} — {int(users or 0):,} مستخدم")
    else:
        lines.append("لا توجد إحصاءات كافية بعد — كن أول المستخدمين!")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))
    _safe_edit(call, "\n".join(lines), markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_subscription(call) -> None:
    user = call.from_user
    lang = (getattr(user, "language_code", "") or "ar").lower()
    missing = gate_check.get_missing_channels(user.id, use_cache=False)
    if not missing:
        text = "✅ <b>اشتراكك مفعّل</b>\n\nأنت مشترك في القناتين، ويمكنك استخدام كل بوتات المتجر بحرية."
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))
        _safe_edit(call, text, markup)
        bot.answer_callback_query(call.id, "✅ الاشتراك مفعّل")
        return

    try:
        gate.show_gate(call.message.chat.id, missing, lang)
    except Exception:
        pass
    bot.answer_callback_query(
        call.id,
        f"🔐 ما زلت غير مشترك في {len(missing)} قناة. اشترك ثم اضغط تحقق.",
        show_alert=True,
    )


@bot.callback_query_handler(func=lambda call: call.data == "search")
def ask_search(call) -> None:
    if _blocked(call):
        return
    bot.send_message(
        call.message.chat.id,
        "🔍 <b>ابحث في المتجر</b>\n\n"
        "أرسل اسم البوت أو كلمة من وصفه (مثال: صور، ترجمة، تيك توك، سيرة).\n"
        "أو أرسل /start للعودة للقائمة.",
        reply_markup=types.ForceReply(selective=True),
    )
    bot.answer_callback_query(call.id)


def handle_search(message) -> None:
    if gate.check_and_show_gate(message):
        return
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        send_store_menu(message.chat.id)
        return

    results = search_bots(BOTS, text, limit=12)
    if not results:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))
        bot.send_message(
            message.chat.id,
            f"🔍 لا توجد نتائج مطابقة لـ «{esc(text)}».\n"
            "جرّب كلمة أقصر أو تصفح الفئات من القائمة الرئيسية.",
            reply_markup=markup,
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in results:
        markup.add(types.InlineKeyboardButton(
            f"{b.get('emoji', '🤖')} {b.get('name', b.get('id', ''))}",
            callback_data=f"bot:{b['id']}",
        ))
    markup.add(types.InlineKeyboardButton("🏪 القائمة الرئيسية", callback_data="back_main"))
    bot.send_message(
        message.chat.id,
        f"🔍 <b>نتائج البحث عن «{esc(text)}»</b>\n\nاختر البوت:",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: (call.data or "").startswith("gate_verify"))
def verify_sub(call) -> None:
    gate.handle_verify_callback(call)


def register_handlers(bot_instance) -> None:
    pass


if __name__ == "__main__":
    start_bot(bot, "store")
