# -*- coding: utf-8 -*-
"""
Bots_Folder/bot_store.py — متجر تطبيقات بودة (الدليل الرسمي للبوتات).

البوابة الإجبارية: @Stick_boda + @ebdo_4 فقط.
"""
import json
from pathlib import Path

import telebot
from telebot import types

from Bots_Folder.bot_base import get_token, start_bot
from Bots_Folder.gate_middleware import GateMiddleware

TOKEN = get_token("BOT_STORE_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
gate = GateMiddleware(bot, "store")

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "bots_registry.json"
with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
    BOTS = json.load(f)


def get_categories():
    return sorted({b.get("category", "").strip() for b in BOTS if b.get("category")})


def send_store_menu(chat_id: int):
    welcome_text = (
        "🏪 <b>أهلاً بك في متجر تطبيقات بودة (Boda Store)</b>\n\n"
        "أكثر من 34 بوت وتطبيق مصغر في مكان واحد!\n"
        "اختر الفئة التي تهمك واستكشف الأدوات الذكية."
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    for cat in get_categories():
        markup.add(types.InlineKeyboardButton(f"📂 {cat}", callback_data=f"cat_{cat}"))
    bot.send_message(chat_id, welcome_text, reply_markup=markup)


def _blocked(call) -> bool:
    """فحص البوابة داخل أزرار الكولباك (يمنع التحايل بالأزرار القديمة)."""
    user = getattr(call, "from_user", None)
    if not user:
        return True
    lang = (getattr(user, "language_code", "") or "ar").lower()
    return gate.check_user(user.id, call.message.chat.id, lang)


@bot.message_handler(commands=["start"])
def send_welcome(message):
    if gate.check_and_show_gate(message):
        return
    send_store_menu(message.chat.id)


@bot.callback_query_handler(func=lambda call: (call.data or "").startswith("cat_"))
def show_category(call):
    if _blocked(call):
        return

    cat = (call.data or "").split("_", 1)[1]
    filtered = [b for b in BOTS if b.get("category") == cat]

    text = f"📂 فئة: <b>{cat}</b>\n\nاختر البوت لبدء الاستخدام:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in filtered:
        emoji = b.get("emoji") or "🤖"
        markup.add(types.InlineKeyboardButton(
            f"{emoji} {b.get('name', b.get('id', ''))}", url=b.get("url", "")))
    markup.add(types.InlineKeyboardButton("🔙 العودة للمتجر", callback_data="back_main"))

    try:
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, text, reply_markup=markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "back_main")
def back_main(call):
    if _blocked(call):
        return
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    send_store_menu(call.message.chat.id)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: (call.data or "").startswith("gate_verify"))
def verify_sub(call):
    gate.handle_verify_callback(call)


def register_handlers(bot_instance):
    pass


if __name__ == "__main__":
    start_bot(bot, "store")
