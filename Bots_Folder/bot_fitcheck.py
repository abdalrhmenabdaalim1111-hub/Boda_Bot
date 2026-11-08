"""
bot_fitcheck.py — FitCheck | حاسبة BMI وصحة الجسم
الاسم العربي: حاسبة BMI
English Name: FitCheck
Username: @FitCheckXBot
الوصف: يحسب مؤشر كتلة جسمك ويعطيك توصيات صحية متخصصة لوزن مثالي وحياة أفضل.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[FitCheck] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("fitcheck")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "حاسبة BMI"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_sessions = {}  # uid → {"step": "", "weight": 0, "height": 0, "age": 0, "gender": ""}

def store_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def gender_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("👨 ذكر", callback_data="gender:m"),
        InlineKeyboardButton("👩 أنثى", callback_data="gender:f"),
    )
    return kb

def bmi_category(bmi):
    if bmi < 18.5:  return ("نحيف جداً 🔵", "ابدأ بتناول وجبات متوازنة غنية بالبروتين والكربوهيدرات.")
    elif bmi < 25:  return ("وزن طبيعي ✅", "أنت في وزن ممتاز! حافظ على نشاطك الرياضي وتغذيتك الجيدة.")
    elif bmi < 30:  return ("زيادة وزن 🟡", "حاول تقليل السكريات والدهون وممارسة الرياضة 3-4 مرات أسبوعياً.")
    elif bmi < 35:  return ("سمنة من الدرجة الأولى 🟠", "استشر طبيباً أو أخصائي تغذية لخطة علاج مناسبة.")
    else:           return ("سمنة مفرطة 🔴", "ضروري مراجعة طبيب متخصص في السمنة فوراً.")

def calc_ideal_weight(height_cm, gender):
    h = height_cm / 100
    if gender == "m": return round(22.5 * h * h, 1)
    return round(21.5 * h * h, 1)

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid = msg.from_user.id
    user_sessions[uid] = {"step": "gender"}
    bot.send_message(msg.chat.id,
        f"💪 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "احسب مؤشر كتلة جسمك (BMI) وتعرّف على وضعك الصحي.\n\n"
        "👇 <b>أولاً، حدد جنسك:</b>",
        reply_markup=gender_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("gender:"))
def handle_gender(call):
    uid       = call.from_user.id
    gender    = call.data.split(":")[1]
    cid, mid  = call.message.chat.id, call.message.message_id
    if uid not in user_sessions: user_sessions[uid] = {}
    user_sessions[uid]["gender"] = gender
    user_sessions[uid]["step"]   = "age"
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "🎂 <b>كم عمرك بالسنوات؟</b>\n\n<i>أرسل رقماً مثل: 25</i>",
        cid, mid)

@bot.callback_query_handler(func=lambda c: c.data == "restart")
def handle_restart(call):
    user_sessions[call.from_user.id] = {"step": "gender"}
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "👇 <b>حدد جنسك للبدء من جديد:</b>",
        call.message.chat.id, call.message.message_id, reply_markup=gender_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    if uid not in user_sessions:
        user_sessions[uid] = {"step": "gender"}
        cmd_start(msg); return

    step = user_sessions[uid].get("step", "")

    try:
        val = float(text)
        if step == "age":
            if not (5 <= val <= 120): raise ValueError("invalid age")
            user_sessions[uid]["age"]  = int(val)
            user_sessions[uid]["step"] = "weight"
            bot.reply_to(msg, "⚖️ <b>كم وزنك بالكيلوجرام؟</b>\n\n<i>مثال: 75</i>")

        elif step == "weight":
            if not (20 <= val <= 300): raise ValueError("invalid weight")
            user_sessions[uid]["weight"] = val
            user_sessions[uid]["step"]   = "height"
            bot.reply_to(msg, "📏 <b>كم طولك بالسنتيمتر؟</b>\n\n<i>مثال: 175</i>")

        elif step == "height":
            if not (100 <= val <= 250): raise ValueError("invalid height")
            user_sessions[uid]["height"] = val
            # Calculate
            w, h   = user_sessions[uid]["weight"], val / 100
            bmi    = round(w / (h * h), 1)
            cat, tip = bmi_category(bmi)
            gender   = user_sessions[uid].get("gender", "m")
            ideal    = calc_ideal_weight(val, gender)
            diff     = round(w - ideal, 1)
            diff_txt = f"زيادة {abs(diff)} كجم" if diff > 0 else (f"نقص {abs(diff)} كجم" if diff < 0 else "مثالي ✅")

            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(
                InlineKeyboardButton("🔄 حساب مجدداً", callback_data="restart"),
                InlineKeyboardButton("🏪 متجر Boda",   url=STORE_URL),
            )
            bot.reply_to(msg,
                f"📊 <b>نتيجة مؤشر كتلة الجسم (BMI):</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"📌 <b>BMI:</b> {bmi}\n"
                f"🏷️ <b>التصنيف:</b> {cat}\n"
                f"⚖️ <b>وزنك الحالي:</b> {w} كجم\n"
                f"🎯 <b>وزنك المثالي:</b> {ideal} كجم\n"
                f"📉 <b>الفرق:</b> {diff_txt}\n"
                f"━━━━━━━━━━━━━━\n"
                f"💡 <b>نصيحة:</b> {tip}",
                reply_markup=kb)
            user_sessions[uid] = {"step": "gender"}
        else:
            cmd_start(msg)
    except ValueError as e:
        if str(e).startswith("invalid"):
            bot.reply_to(msg, "⚠️ أدخل رقماً صحيحاً في النطاق المطلوب.")
        else:
            bot.reply_to(msg, "⚠️ أدخل رقماً صحيحاً فقط مثل: <code>75</code>")
    except Exception as e:
        bot.reply_to(msg, f"❌ خطأ: {e}")

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query"])
