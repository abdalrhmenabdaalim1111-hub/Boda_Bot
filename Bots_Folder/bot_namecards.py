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
import urllib.parse
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
# المسار الموحّد: /namecards/ (يعمل محلياً عبر alias في api_server وعلى GitHub Pages)
APP_URL = f"{_BASE}/namecards/"
if not APP_URL.endswith("/"):
    APP_URL += "/"

# لوحة الأدمن: مخصصة لمعرّفات محددة في BODA_ADMIN_IDS
_ADMIN_IDS = {int(x) for x in
              (os.getenv("BODA_ADMIN_IDS") or "").split(",") if x.strip().isdigit()}
_API_KEY = (os.getenv("API_SERVER_KEY") or "").strip()
_ADMIN_BASE = (os.getenv("BODA_API_BASE") or "").strip().rstrip("/") or _BASE
ADMIN_URL = f"{_ADMIN_BASE}/admin/namecards.html?key={urllib.parse.quote(_API_KEY)}"

WELCOME = (
    "🃏 <b>مرحباً بك في بوت بطاقات بالاسم</b>\n\n"
    "اختر قالباً، اكتب اسمك، وسنرسم لك بطاقة احترافية ونرسلها لك هنا مباشرة.\n"
    "يمكنك أيضاً مشاهدة إعلان قصير لإزالة العلامة المائية.\n\n"
    "اضغط الزر أدناه لفتح التطبيق 👇"
)


def _app_markup() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📱 افتح التطبيق", web_app=types.WebAppInfo(url=APP_URL)))
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
        "• /admin — لوحة الأدمن (للأدمن فقط)\n"
        "• /help — هذه الرسالة\n\n"
        "للإنشاء: افتح التطبيق، اختر قالباً، اكتب الاسم، اضغط «إنشاء».\n"
        "ستصلك الصورة هنا في المحادثة.",
    )


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if message.from_user.id not in _ADMIN_IDS:
        bot.send_message(message.chat.id, "⛔ هذا الأمر مخصص للأدمن فقط.")
        return
    kb = types.InlineKeyboardMarkup()
    label = "⚙️ افتح لوحة الأدمن"
    if ADMIN_URL.startswith("https://"):
        kb.add(types.InlineKeyboardButton(label, web_app=types.WebAppInfo(url=ADMIN_URL)))
    else:
        kb.add(types.InlineKeyboardButton(label, url=ADMIN_URL))
    bot.send_message(
        message.chat.id,
        "⚙️ <b>لوحة أدمن البطاقات</b>\n\n"
        "تعمل من نفس خادم Boda (المنفذ 8080). إن كنت على جهاز آخر، "
        "اضبط BODA_API_BASE برابط HTTPS عام قبل الإرسال.",
        reply_markup=kb)


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
