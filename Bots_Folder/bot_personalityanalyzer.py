"""
bot_personalityanalyzer.py — المحلل النفسي | Soul Scan
@PsycheAnalyzeBot
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
    log = get_logger("personality")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="[Personality] %(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("personality")

TOKEN     = os.getenv("BOT_PERSONALITYANALYZER_TOKEN", "8753720745:AAH4WUywdSaW-BYp5A60CzaIhdHEYLUhnn0")
STORE_URL = "https://t.me/BodaStoreeBot"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

_sessions = {}

# 10 Deep Personality Questions
QUESTIONS = [
    {
        "q": "1️⃣ <b>تكسّرت شاشة هاتفك فجأة، ما هو أول شيء تفعله؟</b>",
        "opts": [("أحاول إصلاحه بنفسي 🛠️", 4), ("أغضب وأنزعج جداً 😤", 1), ("أتقبل الأمر وأشتري جديداً 📱", 2), ("أبحث عن مركز صيانة فوراً 🏃", 3)]
    },
    {
        "q": "2️⃣ <b>لو خيّروك بقوة خارقة، ماذا ستختار؟</b>",
        "opts": [("قراءة الأفكار 🧠", 4), ("الطيران 🦅", 3), ("الاختفاء 👻", 2), ("العودة بالزمن ⏳", 1)]
    },
    {
        "q": "3️⃣ <b>كيف تقضي يوم إجازتك المثالي؟</b>",
        "opts": [("في السرير أتابع مسلسلات 🛏️", 2), ("استكشاف مكان جديد 🗺️", 4), ("الجلوس في مقهى هادئ ☕", 3), ("مع الأصدقاء في حفلة 🎉", 1)]
    },
    {
        "q": "4️⃣ <b>ما الوظيفة التي تظن أنها تعبر عن شخصيتك الحقيقية؟</b>",
        "opts": [("محقّق / باحث 🕵️", 4), ("فنان / مبدع 🎨", 3), ("رجل أعمال / مدير 👔", 1), ("مرشد / معلم 📚", 2)]
    },
    {
        "q": "5️⃣ <b>وجدت حقيبة مليئة بالمال في الشارع ولا أحد يراقبك، ماذا تفعل؟</b>",
        "opts": [("أسلمها للشرطة 👮", 2), ("آخذ القليل وأترك الباقي 🤔", 3), ("أتركها مكانها وأغادر 🚶", 4), ("آخذها كلها وأطير 💸", 1)]
    },
    {
        "q": "6️⃣ <b>عندما تواجه مشكلة معقدة في حياتك:</b>",
        "opts": [("أفكر بعمق وأحللها وحدي 🧠", 4), ("أستشير أصدقائي وعائلتي 🗣️", 2), ("أتوتر وأبحث عن مخرج سريع 🏃", 1), ("أكتب خطوات حلها على ورقة 📝", 3)]
    },
    {
        "q": "7️⃣ <b>ما هي أكثر كلمة يصفك بها أصدقاؤك؟</b>",
        "opts": [("غامض وكتوم 🤐", 4), ("مرح وحيوي 🤣", 1), ("عاقل وناصح 👓", 2), ("عنيد ومتمرد 😈", 3)]
    },
    {
        "q": "8️⃣ <b>في الألعاب التنافسية (فيديو جيمز أو رياضة):</b>",
        "opts": [("العب للمتعة فقط 🎮", 2), ("أغش أحياناً لأفوز 🤫", 1), ("أركز جداً ويجب أن أفوز 🏆", 4), ("أحب التخطيط ورسم الاستراتيجيات 🧮", 3)]
    },
    {
        "q": "9️⃣ <b>لو كنت في غابة مظلمة وسمعت صوتاً غريباً:</b>",
        "opts": [("أختبئ فوراً 🙈", 2), ("أذهب لاستكشاف مصدر الصوت 🔦", 4), ("أصرخ طالباً المساعدة 🗣️", 1), ("أجهز سلاحاً للاحتماء الطارئ 🔪", 3)]
    },
    {
        "q": "🔟 <b>أخيراً.. ما هو أهم شيء في الحياة بالنسبة لك؟</b>",
        "opts": [("المال والقوة 💰", 1), ("السلام الداخلي والحكمة 🧘", 4), ("المغامرة وتجربة كل شيء 🌋", 3), ("الحب والعلاقات الدافئة ❤️", 2)]
    }
]

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 <b>أهلاً بك في المحلل النفسي السري! 🧩</b>\n\n"
        "أنا هنا لأغوص في أعماق شخصيتك وأكتشف أسرارك الخفية بناءً على 10 مواقف.\n\n"
        "👇 <b>أرسل /analyze أو اضغط على الزر للبدء في الاختبار الممتع!</b>"
    )
    if not is_subscribed(bot, message.from_user.id):
        bot.send_message(message.chat.id, welcome_text)
        send_subscription_prompt(bot, message.chat.id)
        return
        
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🚀 ابدأ التحليل الآن", callback_data="start_quiz"))
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=kb)

@bot.message_handler(commands=['analyze'])
def start_analysis_cmd(message):
    start_quiz(message.from_user.id, message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data == "start_quiz")
def on_start_quiz(call):
    start_quiz(call.from_user.id, call.message.chat.id, call.message.message_id)

def start_quiz(uid, chat_id, message_id=None):
    if not is_subscribed(bot, uid):
        send_subscription_prompt(bot, chat_id)
        return
    _sessions[uid] = {"q": 0, "score": 0}
    send_question(uid, chat_id, message_id)

def send_question(uid, chat_id, message_id=None):
    session = _sessions.get(uid)
    if not session: return
    
    q_index = session["q"]
    if q_index >= len(QUESTIONS):
        finish_quiz(uid, chat_id, message_id)
        return
        
    q_data = QUESTIONS[q_index]
    kb = InlineKeyboardMarkup(row_width=1)
    
    # Shuffle options to avoid pattern guessing
    opts = [x for x in q_data["opts"]]
    random.shuffle(opts)
    
    for opt_text, opt_score in opts:
        kb.add(InlineKeyboardButton(opt_text, callback_data=f"ans:{opt_score}"))
        
    text = f"⏳ <b>السؤال {q_index + 1} من {len(QUESTIONS)}:</b>\n\n{q_data['q']}"
    
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ans:"))
def handle_answer(call):
    uid = call.from_user.id
    if uid not in _sessions:
        bot.answer_callback_query(call.id, "⚠️ الجلسة منتهية، من فضلك ابدأ من جديد.", show_alert=True)
        return
        
    score_val = int(call.data.split(":")[1])
    _sessions[uid]["score"] += score_val
    _sessions[uid]["q"] += 1
    
    send_question(uid, call.message.chat.id, call.message.message_id)

def finish_quiz(uid, chat_id, message_id):
    score = _sessions[uid]["score"]
    
    if score <= 15:
        title = "🔥 شخصية متهورة وعفوية جداً (النار الباردة)"
        desc = "أنت تعيش اللحظة! لا تحب التفكير الزائد في المستقبل وتتخذ قراراتك بناءً على مشاعرك الحالية. عفويتك تجعلك محبوباً وممتعاً لكنها قد توقعك في بعض المتاعب. تحب الحرية وتكره القيود، وتميل إلى كسر القواعد."
    elif score <= 25:
        title = "🌊 شخصية متوازنة واجتماعية (الموجة الهادئة)"
        desc = "أنت الروح الطيبة في أي مجموعة. تمزج بين المنطق والعاطفة، وتحب مساعدة الآخرين. دبلوماسي بالفطرة وتكره الصراعات، مما يجعلك الصديق الذي يلجأ إليه الجميع وقت الأزمات. لكنك أحياناً تتجاهل احتياجاتك من أجل غيرك."
    elif score <= 33:
        title = "💡 شخصية تحليلية ومخططة (المهندس الصامت)"
        desc = "أنت العقل المدبر! لا تتخذ خطوة دون أن تحسب لها ألف حساب. تفضل الجلوس في الخلفية ومراقبة وتحليل تصرفات الآخرين. تحب الاستقرار، ولا تثق بسهولة، لكن علاقاتك عميقة وحقيقية جداً مبنية على الاحترام المطلق."
    else:
        title = "🕵️ شخصية ذئب منفرد غامض (ظل القمر)"
        desc = "الغموض هو اسمك الأوسط. أنت تثق بنفسك فقط، وتجد متعتك وقوتك في الاستقلال التام عن الآخرين. لديك رؤية شديدة الثاقبة ونادراً ما يكذب إحساسك. قد يراك البعض بارداً، لكنك في الحقيقة تحمي مشاعرك جيداً وتراقب كل شيء بصمت."
        
    text = (
        f"🧠 <b>اكتمل تحليل شخصيتك بسلام!</b>\n"
        f"📊 <i>نقاطك العميقة: {score}/{len(QUESTIONS)*4}</i>\n\n"
        f"✨ <b>{title}</b>\n"
        f"📝 {desc}\n\n"
        f"🔄 <i>هل ترغب في إعادة الاختبار أو مشاركته مع أصدقائك؟</i>"
    )
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🔄 إعادة التحليل", callback_data="start_quiz"))
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    
    bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
    try: _sessions.pop(uid, None)
    except: pass

if __name__ == "__main__":
    from bot_base import start_polling
    start_polling(bot, "personality")
