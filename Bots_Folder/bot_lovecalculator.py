"""
bot_lovecalculator.py — رادار القلوب | Heart Radar
@LoveMatchRBot
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
    log = get_logger("lovecalculator")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="[LoveCalc] %(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("lovecalculator")

from bot_base import get_token
TOKEN = get_token("BOT_LOVECALCULATOR_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_states = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "💕 <b>أهلاً بك في رادار القلوب!</b> 💘\n\n"
        "هل تريد معرفة نسبة التوافق العاطفي بينك وبين من تحب؟ نحن هنا لنقيس لك نبض القلوب ونخبرك بالحقيقة (الترفيهية)! 😄\n\n"
        "👇 <b>أرسل اسمك الآن للبدء:</b>"
    )
    if not is_subscribed(bot, message.from_user.id):
        bot.send_message(message.chat.id, welcome_text)
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.send_message(message.chat.id, welcome_text)

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    
    from utils import app_kb
    uid = message.from_user.id
    text = message.text.strip()
    
    if uid not in user_states:
        user_states[uid] = text
        bot.send_message(message.chat.id, f"🥰 جميل يا <b>{text}</b>! الآن أرسل اسم الشخص الآخر:", parse_mode="HTML")
    else:
        name1 = user_states[uid]
        name2 = text
        
        # Calculate percentage using deterministic hash
        m1, m2 = name1.lower(), name2.lower()
        percentage = int((hash(m1 + m2 + "cupid") % 100)) + 1
        
        if percentage >= 85: 
            emoji = "💖💖💖"
            msg = "قصة حب خرافية! أنتما توأم روح حقيقي 👩‍❤️‍👨"
        elif percentage >= 65: 
            emoji = "💕💕"
            msg = "علاقة قوية ومتناغمة، فيها الكثير من السعادة ✨"
        elif percentage >= 40: 
            emoji = "❤️"
            msg = "هناك مشاعر طيبة، لكن تحتاجان إلى بعض التفاهم 🤔"
        else: 
            emoji = "💔"
            msg = "التوافق ليس مثالياً، لكن الحب يصنع المعجزات! 🤷‍♂️"
        
        bot.send_message(message.chat.id, 
            f"💘 <b>نتيجة رادار القلوب:</b>\n\n"
            f"👤 <b>{name1}</b>\n"
            f"          ➕\n"
            f"👤 <b>{name2}</b>\n\n"
            f"🧬 <b>نسبة التوافق: {percentage}%</b> {emoji}\n"
            f"💌 <b>التحليل:</b> {msg}\n\n"
            "🔄 أرسل اسماً جديداً لبدء حساب آخر!",
            parse_mode="HTML",
            reply_markup=app_kb())
        
        del user_states[uid]

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "lovecalculator")
