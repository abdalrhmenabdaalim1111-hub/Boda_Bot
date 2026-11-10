"""
bot_template.py — قالب بوت جديد (النظام الموحّد v5)

طريقة الإنشاء:
    1. انسخ هذا الملف إلى bot_mybot.py
    2. غيّر BOT_NAME إلى اسم البوت (بدون bot_ أو .py)
    3. أضف التوكن في .env :  BOT_MYBOT_TOKEN=...
    4. سجّل البوت في bots_registry.json  (أو: python dev_tools.py new-bot mybot "MyBot")

ملاحظة مهمة:
    start_bot() يربط تلقائياً: تتبع المستخدمين + الإعلانات الموحدة +
    محرك النمو (شبكة الخمسة) + زر WebApp — لا تكتب أي كود إضافي.
"""
import sys, logging
import telebot

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[Template] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("template")

from bot_base import get_token

# ── الإعداد: غيّر هذين السطرين فقط ──
BOT_NAME = "template"
TOKEN = get_token(f"BOT_{BOT_NAME.upper()}_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)


def app_kb():
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪 متجر تطبيقات Boda", url=STORE_URL))
    return kb


@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    welcome_text = (
        "👋 <b>أهلاً في Template Bot!</b>\n\n"
        "هذا قالب لإنشاء بوتات جديدة تعمل بنظام المحادثة الطبيعي.\n\n"
        "أرسل لي أي شيء!"
    )
    bot.send_message(msg.chat.id, welcome_text, reply_markup=app_kb())


@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    bot.send_message(msg.chat.id, f"✅ استلمت رسالتك:\n{msg.text}")


if __name__ == "__main__":
    from bot_base import start_bot
    log.info("🚀 Template Bot starting")
    start_bot(bot, BOT_NAME, allowed_updates=["message", "callback_query"])
