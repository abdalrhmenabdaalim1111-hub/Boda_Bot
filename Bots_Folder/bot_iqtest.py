"""
bot_iqtest.py — مقياس العبقرية | Genius Meter
@GeniusCheck1Bot
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
    log = get_logger("iqtest")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="[IQTest] %(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("iqtest")

TOKEN        = os.getenv("BOT_IQTEST_TOKEN", "8712494378:AAHVjhraz0--uMzO_iW8KaivcsQyeI3xj3U")
BOT_NAME     = "مقياس العبقرية | Genius Meter"
BOT_USERNAME = "@GeniusCheck1Bot"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_states = {}

def get_question():
    questions = [
        ("ما هو الرقم الذي يكمل السلسلة: 2, 4, 8, 16, ...؟", "32"),
        ("ما هو عكس كلمة 'سريع'؟", "بطيء"),
        ("إذا كان اليوم هو الإثنين، فماذا سيكون بعد 5 أيام؟", "السبت"),
        ("ما هي نتيجة: 5 * 5 + 5؟", "30"),
        ("كم شهرًا في السنة يحتوي على 28 يومًا؟", "12"),
    ]
    return random.choice(questions)

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    if not is_subscribed(bot, msg.from_user.id):
        send_subscription_prompt(bot, msg.chat.id)
        return
    bot.send_message(msg.chat.id,
        f"👋 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "اختبر ذكاءك من خلال سلسلة من الأسئلة الممتعة!\n\n"
        "💡 <b>أرسل أي كلمة للبدء بالاختبار:</b>")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
        
    from utils import app_kb
    uid = message.from_user.id
    
    if uid in user_states:
        question, answer, score, count = user_states[uid]
        text_lower = message.text.lower().strip()
        if answer in text_lower:
            score += 1
            bot.send_message(message.chat.id, "✅ <b>إجابة صحيحة!</b>", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, f"❌ <b>إجابة خاطئة!</b>\nالإجابة الصحيحة كانت: {answer}", parse_mode="HTML")
        count += 1
        
        if count >= 3:
            final_score = int((score / 3) * 60 + 80 + random.randint(0, 15))
            if final_score >= 120: emoji = "🌟"; level = "عبقري فذ"
            elif final_score >= 105: emoji = "✨"; level = "ذكي جداً"
            elif final_score >= 90: emoji = "👍"; level = "مستوى الذكاء طبيعي"
            else: emoji = "📚"; level = "يحتاج إلى تدريب الدماغ"
            
            bot.send_message(message.chat.id,
                f"🧠 <b>النتيجة النهائية لاختبار الذكاء</b>\n\n"
                f"{emoji} <b>نسبة ذكائك المعرفي (IQ): {final_score}</b>\n"
                f"📊 <b>التقييم: {level}</b>\n\n"
                f"أرسل أي رسالة للبدء باختبار جديد!",
                reply_markup=app_kb())
            del user_states[uid]
            return
    else:
        score = 0
        count = 0
        bot.send_message(message.chat.id, "🎯 <b>دعنا نبدأ التحدي! سأطرح عليك 3 أسئلة:</b>", parse_mode="HTML")
    
    q, a = get_question()
    user_states[uid] = (q, a, score, count)
    bot.send_message(message.chat.id, f"❓ <b>السؤال {count+1}:</b>\n\n{q}")

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "iqtest")
