"""
bot_braintwist.py — BrainTwist | بوت الألغاز والمعلومات
الاسم العربي: بوت الألغاز
English Name: BrainTwist
Username: @BrainTwistXBot
الوصف: تحدّ عقلك يومياً بألغاز ممتعة ومسابقات معلومات عامة مع أصدقائك!

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging, random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[BrainTwist] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("braintwist")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "بوت الألغاز"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

RIDDLES = [
    {"q": "ما الذي له أسنان لكنه لا يعض؟", "a": "المشط"},
    {"q": "ما الذي يكبر كلّما أخذت منه؟", "a": "الحفرة"},
    {"q": "أنا لا أتكلم لكنني أجيب، من أنا؟", "a": "الصدى"},
    {"q": "ما الذي يمشي على أربع في الصباح وعلى اثنتين في الظهيرة وعلى ثلاث في المساء؟", "a": "الإنسان (طفل، بالغ، عجوز)"},
    {"q": "كيف تضع فيلاً في الثلاجة في 3 خطوات؟", "a": "افتح الثلاجة، ضع الفيل، أغلق الثلاجة!"},
    {"q": "ما الشيء الذي كلّما زاد نقص؟", "a": "العمر"},
    {"q": "ما الذي له عيون لكنه لا يرى؟", "a": "الإبرة"},
    {"q": "ما الذي يأتي مرة في الدقيقة، مرتين في اللحظة، ولا يأتي في ألف عام؟", "a": "حرف الميم"},
    {"q": "ما الذي يمكنك كسره بمجرد ذكره؟", "a": "الصمت"},
    {"q": "من الذي يولد في الماء ويموت إذا بقي في الماء؟", "a": "الملح"},
]

QUIZ = [
    {"q": "كم عدد دول العالم؟",                   "opts": ["193", "195", "200", "185"],  "ans": 0},
    {"q": "ما هي أكبر دولة في العالم مساحةً؟",    "opts": ["كندا", "الصين", "روسيا", "أمريكا"], "ans": 2},
    {"q": "كم يبلغ ضرب 7 × 8؟",                   "opts": ["54", "56", "58", "64"],      "ans": 1},
    {"q": "ما هي عاصمة اليابان؟",                 "opts": ["كيوتو", "أوساكا", "طوكيو", "هيروشيما"], "ans": 2},
    {"q": "من اخترع الهاتف؟",                     "opts": ["توماس إديسون", "نيكولا تيسلا", "ألكسندر غراهام بيل", "برنارد ليز"], "ans": 2},
    {"q": "ما هو أطول نهر في العالم؟",             "opts": ["الأمازون", "النيل", "المسيسيبي", "الكونغو"], "ans": 1},
    {"q": "كم يبلغ مجموع زوايا المثلث؟",           "opts": ["90 درجة", "180 درجة", "270 درجة", "360 درجة"], "ans": 1},
    {"q": "ما هي أسرع طائر في العالم؟",            "opts": ["النسر", "الشاهين", "الحدأة", "طائر الجنة"], "ans": 1},
]

EMOJIS = ["🧠", "💡", "🤔", "🎯", "⚡", "🔥", "🌟"]

active_quiz = {}  # uid → {"idx": int, "score": int, "questions": list}

def home_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎯 لغز جديد",   callback_data="riddle:new"),
        InlineKeyboardButton("🧠 مسابقة",      callback_data="quiz:start"),
        InlineKeyboardButton("🏪 متجر Boda",  url=STORE_URL),
    )
    return kb

def reveal_kb(riddle_index):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💡 الإجابة",     callback_data=f"riddle:reveal:{riddle_index}"),
        InlineKeyboardButton("🎯 لغز آخر",     callback_data="riddle:new"),
        InlineKeyboardButton("🏪 متجر Boda",   url=STORE_URL),
    )
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        f"{random.choice(EMOJIS)} <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "تحدّ عقلك يومياً بألغاز ممتعة ومسابقات!\n\n"
        "👇 <b>اختر ما تريد:</b>",
        reply_markup=home_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("riddle:"))
def handle_riddle(call):
    parts    = call.data.split(":")
    act      = parts[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if act == "new":
        idx    = random.randint(0, len(RIDDLES)-1)
        riddle = RIDDLES[idx]
        bot.edit_message_text(
            f"🤔 <b>اللغز:</b>\n\n<i>{riddle['q']}</i>\n\n"
            f"💭 <i>فكّر في الإجابة ثم اضغط لكشفها!</i>",
            cid, mid, reply_markup=reveal_kb(idx))

    elif act == "reveal" and len(parts) > 2:
        idx    = int(parts[2])
        riddle = RIDDLES[idx]
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🎯 لغز جديد",  callback_data="riddle:new"),
            InlineKeyboardButton("🧠 مسابقة",     callback_data="quiz:start"),
            InlineKeyboardButton("🏪 متجر Boda",  url=STORE_URL),
        )
        bot.edit_message_text(
            f"🤔 <b>اللغز:</b>\n<i>{riddle['q']}</i>\n\n"
            f"✅ <b>الإجابة:</b> <b>{riddle['a']}</b>\n\n"
            f"🎯 هل أجبت صح؟",
            cid, mid, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("quiz:"))
def handle_quiz(call):
    uid      = call.from_user.id
    parts    = call.data.split(":")
    act      = parts[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if act == "start":
        questions = random.sample(QUIZ, min(5, len(QUIZ)))
        active_quiz[uid] = {"idx": 0, "score": 0, "questions": questions}
        _send_quiz_question(uid, cid, mid, edit=True)

    elif act == "ans" and len(parts) > 2:
        chosen = int(parts[2])
        if uid not in active_quiz: return
        sess = active_quiz[uid]
        q    = sess["questions"][sess["idx"]]
        correct = (chosen == q["ans"])
        if correct: sess["score"] += 1
        sess["idx"] += 1

        if sess["idx"] >= len(sess["questions"]):
            # End
            score = sess["score"]
            total = len(sess["questions"])
            emoji = "🏆" if score == total else ("🌟" if score >= total*0.7 else "💪")
            kb    = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton("🔄 مسابقة جديدة", callback_data="quiz:start"),
                InlineKeyboardButton("🎯 لغز",           callback_data="riddle:new"),
                InlineKeyboardButton("🏪 متجر Boda",     url=STORE_URL),
            )
            del active_quiz[uid]
            status = "صح ✅" if correct else f"خطأ ❌ (الصح: {q['opts'][q['ans']]})"
            bot.edit_message_text(
                f"السؤال الأخير — {status}\n\n"
                f"{emoji} <b>انتهت المسابقة!</b>\n\n"
                f"✅ نتيجتك: <b>{score}/{total}</b>\n"
                f"{'أداء ممتاز! 🏆' if score==total else ''}",
                cid, mid, reply_markup=kb)
        else:
            status = "✅ صح!" if correct else f"❌ خطأ! الصح: <b>{q['opts'][q['ans']]}</b>"
            bot.edit_message_text(f"{status}", cid, mid)
            import time; time.sleep(0.8)
            _send_quiz_question(uid, cid, mid, edit=True)

def _send_quiz_question(uid, cid, mid, edit=False):
    if uid not in active_quiz: return
    sess  = active_quiz[uid]
    q     = sess["questions"][sess["idx"]]
    idx   = sess["idx"]
    total = len(sess["questions"])
    score = sess["score"]

    kb = InlineKeyboardMarkup(row_width=1)
    for i, opt in enumerate(q["opts"]):
        kb.add(InlineKeyboardButton(opt, callback_data=f"quiz:ans:{i}"))
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))

    text = (
        f"🧠 <b>سؤال {idx+1}/{total}</b> | النقاط: {score}\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>{q['q']}</b>"
    )
    if edit:
        try: bot.edit_message_text(text, cid, mid, reply_markup=kb)
        except: bot.send_message(cid, text, reply_markup=kb)
    else:
        bot.send_message(cid, text, reply_markup=kb)

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    cmd_start(msg)

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query"])
