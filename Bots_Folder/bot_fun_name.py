"""
bot_fun_name.py — FunNameGen
@FunNameGenBot
"""
import time, os, sys, random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import is_subscribed, send_subscription_prompt
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    from logger_config import get_logger, configure_windows_encoding
    configure_windows_encoding()
    log = get_logger("fun-name")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    log = logging.getLogger("fun_name")

STORE_URL = "https://t.me/BodaStoreeBot"
TOKEN     = os.getenv("BOT_FUN_NAME_TOKEN", "8596390483:AAGN-JvyqZ7yEhMJHPp9cKpkUvyyjZhR1y0")
bot = telebot.TeleBot(TOKEN, threaded=True)

def generate_fun_name(real_name):
    prefixes = ["الكابتن", "الأسطورة", "الشبح", "الأمير", "البرنس", "الملك", "الزعيم", "البطل"]
    suffixes = ["الخطير", "المدمر", "السريع", "المشاغب", "الذكي", "المحبوب", "الغريب", "العجيب"]
    return f"{random.choice(prefixes)} {real_name} {random.choice(suffixes)}"

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.reply_to(message, "مرحباً! أرسل اسمك وسأقوم بتوليد اسم مضحك لك!")

@bot.message_handler(func=lambda message: True)
def handle_text_message(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    name = message.text.strip()
    fun_name = generate_fun_name(name)
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="🏪 القائمة الرئيسية / المتجر", url=STORE_URL)
    )
    bot.reply_to(message, f"✨ اسمك الجديد هو:\n\n<b>{fun_name}</b>", parse_mode="HTML", reply_markup=markup)

if __name__ == "__main__":
    from bot_base import start_polling
    start_polling(bot, "fun-name")
