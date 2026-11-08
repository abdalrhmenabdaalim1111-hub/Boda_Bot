"""
bot_mentalage.py — مرآة العقل | Mind Mirror
@MentalAgeBot
"""
import time, os, sys, random
import telebot
from utils import is_subscribed, send_subscription_prompt
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError: pass

try:
    from logger_config import get_logger, configure_windows_encoding
    configure_windows_encoding()
    log = get_logger("mentalage")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="[MentalAge] %(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("mentalage")

TOKEN = os.getenv("BOT_MENTALAGE_TOKEN", "8251149798:AAE9TrCpVBoxYtYm0LcpVU8EShIkZxwvS20")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

_sessions = {}

QUESTIONS = [
    "1️⃣ ما هو أكثر شيء يزعجك في يومك المعتاد؟\n\nأ- الاستيقاظ مبكراً\nب- الزحام والأصوات العالية\nج- الروتين والملل\nد- عدم إنجاز أهدافي",
    "2️⃣ كيف تفضل قضاء عطلة نهاية الأسبوع؟\n\nأ- اللعب ومشاهدة الكرتون/الأفلام\nب- الخروج مع الأصدقاء\nج- القراءة أو الاسترخاء بهدوء\nد- التخطيط للأسبوع القادم",
    "3️⃣ عندما تواجه مشكلة كبيرة، ما هو أول رد فعل لك؟\n\nأ- أغضب بسرعة\nب- أطلب المساعدة فوراً\nج- أفكر بهدوء بحثاً عن الحل\nد- أعتبرها درساً جديداً"
]

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 <b>أهلاً بك في اختبار العمر العقلي 🧠</b>\n\n"
        "هل أنت مستعد لمعرفة عمرك العقلي الحقيقي؟ هل عقلك عقل طفل، أم شاب، أم حكيم عجوز؟ 🤔\n\n"
        "👇 <b>أرسل /test للبدء وسأطرح عليك 3 أسئلة:</b>"
    )
    if not is_subscribed(bot, message.from_user.id):
        bot.send_message(message.chat.id, welcome_text)
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.send_message(message.chat.id, welcome_text)

@bot.message_handler(commands=['test'])
def start_test(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    _sessions[message.from_user.id] = {"q": 0, "score": 0}
    bot.send_message(message.chat.id, QUESTIONS[0])

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
        
    from utils import app_kb
    uid = message.from_user.id
    if uid not in _sessions:
        bot.send_message(message.chat.id, "❌ لم تبدأ الاختبار بعد! أرسل /test للبدء.")
        return
        
    session = _sessions[uid]
    text = message.text.strip().lower()
    
    # Calculate simple score based on answer length or choices
    if "أ" in text or "a" in text: session["score"] += 10
    elif "ب" in text or "b" in text: session["score"] += 20
    elif "ج" in text or "c" in text: session["score"] += 35
    elif "د" in text or "d" in text: session["score"] += 50
    else: session["score"] += 25 # random default
    
    session["q"] += 1
    
    if session["q"] < len(QUESTIONS):
        bot.send_message(message.chat.id, QUESTIONS[session["q"]])
    else:
        # Calculate result
        total = session["score"]
        mental_age = int(total / len(QUESTIONS))
        
        if mental_age <= 15: emoji = "👶"; desc = "عقلك لا يزال طفلاً يحب المرح والمفاجآت!"
        elif mental_age <= 25: emoji = "🧒"; desc = "أنت في مرحلة الشباب العقلي، طموح ومليء بالحيوية."
        elif mental_age <= 40: emoji = "🧑"; desc = "عقلك ناضج، تفكر بعقلانية وتتخذ قرارات متزنة."
        else: emoji = "👴"; desc = "تتمتع بحكمة الشيوخ، وخبرتك في الحياة تسبق سنك الحقيقي!"
            
        bot.send_message(message.chat.id, 
            f"🧠 <b>نتيجة اختبار العمر العقلي!</b>\n\n"
            f"{emoji} <b>عمرك العقلي المحسوب: {mental_age} سنة</b>\n\n"
            f"💭 <b>التحليل:</b>\n{desc}\n\n"
            "🔄 أرسل /test لإعادة الاختبار متى شئت!",
            reply_markup=app_kb())
        del _sessions[uid]

if __name__ == "__main__":
    from bot_base import start_polling
    start_polling(bot, "mentalage")
