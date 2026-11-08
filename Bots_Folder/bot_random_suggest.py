"""
bot_random_suggest.py — اقتراح عشوائي
@RandomSuggestMixBot
"""
import time, os, sys, random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import is_subscribed, send_subscription_prompt
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError: pass

try:
    from logger_config import get_logger, configure_windows_encoding
    configure_windows_encoding()
    log = get_logger("random-suggest")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    log = logging.getLogger("random_suggest")

STORE_URL = "https://t.me/BodaStoreeBot"
TOKEN     = os.getenv("BOT_RANDOM_SUGGEST_TOKEN", "8596214537:AAGAOw0f71JYaj2t9h-vTbZh_rGb8lx97nQ")
bot = telebot.TeleBot(TOKEN, threaded=True)

suggestions = [
    "شاهد فيلم Inception.",
    "جرب قراءة كتاب 'العادات الذرية'.",
    "تعلم لغة برمجة جديدة مثل بايثون.",
    "مارس الرياضة لمدة 30 دقيقة اليوم.",
    "تحدث مع صديق قديم لم تكلمه منذ فترة.",
    "الاستماع إلى بودكاست يضيف لك معلومات جديدة.",
    "تعلم مهارة التصوير الفوتوغرافي.",
    "قم بترتيب غرفتك وتنظيم أفكارك.",
    "جرب كتابة يومياتك قبل النوم بـ 5 دقائق."
]

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.reply_to(message, "مرحباً! أرسل أي رسالة للحصول على اقتراح عشوائي لليوم!")

@bot.message_handler(func=lambda message: True)
def handle_text_message(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        telebot.types.InlineKeyboardButton(text="🏪 المتجر", url=STORE_URL)
    )
    s = random.choice(suggestions)
    bot.reply_to(message, f"✨ <b>اقتراح اليوم:</b>\n\n{s}", parse_mode="HTML", reply_markup=markup)

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "random_suggest")
