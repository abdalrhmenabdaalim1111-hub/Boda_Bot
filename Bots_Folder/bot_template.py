"""
bot_template.py — قالب بوت جديد (بدون WebApp)
"""
import sys, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[Template] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("template")

TOKEN = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

def app_kb():
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
    log.info("🚀 Template Bot starting")
    try:
        bot.delete_webhook(drop_pending_updates=True)
        bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20)
    except Exception as e:
        log.error(f"Fatal error: {e}")
