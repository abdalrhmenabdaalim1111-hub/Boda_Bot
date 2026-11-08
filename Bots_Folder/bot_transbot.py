"""
bot_transbot.py — TransBot | المترجم الفوري
@TransXNowBot
"""
import time, os, sys, threading
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
    log = get_logger("transbot")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="[Trans] %(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("transbot")

TOKEN     = os.getenv("BOT_TRANSBOT_TOKEN", "8679408503:AAEGTZzQhHfr0kuZakmXjkkjzn6uavFLbrM")
STORE_URL = "https://t.me/BodaStoreBot"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

LANG_NAMES = {
    "ar":"العربية","en":"الإنجليزية","fr":"الفرنسية",
    "tr":"التركية","de":"الألمانية","es":"الإسبانية",
    "ru":"الروسية","zh-CN":"الصينية"
}

user_states = {} # chat_id -> text to translate

def translate(text: str, target: str) -> str:
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="auto", target=target).translate(text)

def lang_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(name, callback_data=f"lang:{code}") for code, name in LANG_NAMES.items()]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    if not is_subscribed(bot, msg.from_user.id):
        send_subscription_prompt(bot, msg.chat.id)
        return
    bot.send_message(msg.chat.id,
        "👋 <b>أهلاً في TransBot!</b>\n\n"
        "ترجمة فورية بين 8 لغات عالمية\n\n"
        "⬇️ <b>أرسل النص الذي تريد ترجمته:</b>",
        reply_markup=app_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    user_states[message.chat.id] = message.text
    bot.send_message(message.chat.id, "🌍 <b>اختر لغة الترجمة:</b>", reply_markup=lang_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("lang:"))
def handle_lang_selection(call):
    to_lang = call.data.split(":")[1]
    text = user_states.get(call.message.chat.id)
    if not text:
        bot.answer_callback_query(call.id, "❌ انتهت الجلسة، أرسل النص مجدداً.", show_alert=True)
        return
    
    bot.edit_message_text(f"🌍 <b>جاري الترجمة إلى {LANG_NAMES.get(to_lang, to_lang)}...</b>",
                          call.message.chat.id, call.message.message_id)
    def do():
        try:
            result = translate(text, to_lang)
            lang_name = LANG_NAMES.get(to_lang, to_lang)
            bot.edit_message_text(
                f"✅ <b>الترجمة إلى {lang_name}:</b>\n\n"
                f"{result}\n\n"
                f"<i>الأصل: {text[:60]}{'...' if len(text)>60 else ''}</i>\n\n"
                f"<b>بواسطة:</b> متجر تطبيقات Boda 🏪",
                call.message.chat.id, call.message.message_id, reply_markup=app_kb())
        except Exception as e:
            bot.edit_message_text(f"❌ خطأ في الترجمة: {e}",
                                  call.message.chat.id, call.message.message_id)
    threading.Thread(target=do, daemon=True).start()

if __name__ == "__main__":
    from bot_base import start_polling
    start_polling(bot, "transbot")
