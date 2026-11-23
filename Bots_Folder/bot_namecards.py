# -*- coding: utf-8 -*-
"""
Bots_Folder/bot_namecards.py — بوت «بطاقات بالاسم».

الأوامر:
  /start       ترحيب + زر فتح التطبيق (+ تسجيل الإحالة من ref_)
  /help        شرح الأوامر
  /mycards     آخر 5 بطاقات أنشأها المستخدم
"""
from __future__ import annotations

import os
from pathlib import Path

import telebot
from telebot import types

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from Bots_Folder.bot_base import get_token, start_bot
from Bots_Folder import gate_check
from Bots_Folder.namecards import security, store

# التوكين يُحفظ مشفراً عبر لوحة التحكم (زر «تحديث توكن البوت»)،
# مع دعم الاحتياطي من .env والاسم الذي يحقنه Supervisor.
TOKEN = ""
try:
    from control_center.botconfig import resolve_token as _resolve_token
    TOKEN = _resolve_token("namecards") or ""
except Exception:
    pass
TOKEN = TOKEN or get_token("NAMECARDS_BOT_TOKEN") or get_token("BOT_NAMECARDS_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

_BASE = os.getenv("MINIAPPS_BASE_URL", "").strip().rstrip("/")
if not _BASE:
    _BASE = "https://abdalrhmenabdaalim1111-hub.github.io/Boda_Bot"
APP_URL = f"{_BASE}/apps/namecards/" if "/apps" not in _BASE else f"{_BASE}/namecards/"
if not APP_URL.endswith("/"):
    APP_URL += "/"

WELCOME = (
    "🃏 <b>مرحباً بك في بوت بطاقات بالاسم</b>\n\n"
    "اختر قالباً، اكتب اسمك، وسنرسم لك بطاقة احترافية ونرسلها لك هنا مباشرة.\n"
    "يمكنك أيضاً مشاهدة إعلان قصير لإزالة العلامة المائية.\n\n"
    "اضغط الزر أدناه لفتح التطبيق 👇"
)


def _app_markup() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📱 افتح التطبيق", web_app=types.WebAppInfo(url=APP_URL)))
    kb.add(types.InlineKeyboardButton("🌐 فتح في المتصفح", url=APP_URL))
    kb.add(types.InlineKeyboardButton("🏪 متجر بودة", url="https://t.me/BodaStoreeBot"))
    return kb


@bot.message_handler(commands=["start"])
def cmd_start(message):
    # بوابة الاشتراك موحّدة (عبر unified_middleware) — نتعامل مع الإحالة هنا فقط
    payload = (message.text or "").split(" ", 1)
    if len(payload) > 1 and payload[1].startswith("ref_"):
        ref_hash = payload[1][4:].strip()[:12]
        if ref_hash and ref_hash != security.user_hash(message.from_user.id):
            store.record_referral(ref_hash, message.from_user.id)
    bot.send_message(message.chat.id, WELCOME, reply_markup=_app_markup())


@bot.message_handler(commands=["help"])
def cmd_help(message):
    bot.send_message(
        message.chat.id,
        "🃏 <b>مساعدة البوت</b>\n\n"
        "• /start — فتح التطبيق وإنشاء بطاقة\n"
        "• /mycards — آخر 5 بطاقات أنشأتها\n"
        "• /help — هذه الرسالة\n\n"
        "للإنشاء: افتح التطبيق، اختر قالباً، اكتب الاسم، اضغط «إنشاء».\n"
        "ستصلك الصورة هنا في المحادثة.",
    )


@bot.message_handler(commands=["mycards"])
def cmd_mycards(message):
    uh = security.user_hash(message.from_user.id)
    cards = store.recent_cards(uh, 5)
    if not cards:
        bot.send_message(message.chat.id, "📭 لم تنشئ أي بطاقة بعد. ابدأ بـ /start")
        return
    lines = ["🃏 <b>آخر بطاقاتك:</b>", ""]
    for i, c in enumerate(cards, 1):
        tpl = store.get_template(c["template_id"])
        title = tpl.get("name") or c["template_id"]
        status = "✅" if c["ok"] else "⚠️"
        lines.append(f"{i}. {status} {title} — <code>{c['ts']}</code>")
    bot.send_message(message.chat.id, "\n".join(lines))


if __name__ == "__main__":
    start_bot(bot, "namecards")
