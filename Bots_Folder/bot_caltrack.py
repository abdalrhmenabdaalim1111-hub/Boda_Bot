"""
bot_caltrack.py — CalTrack | عداد السعرات الحرارية
الاسم العربي: عداد السعرات
English Name: CalTrack
Username: @CalTrackXBot
الوصف: تعرّف على السعرات الحرارية في وجباتك وأطعمتك اليومية وتابع هدفك الغذائي بسهولة.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[CalTrack] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("caltrack")

from bot_base import get_token
TOKEN = get_token("BOT_CALTRACK_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "عداد السعرات"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

# قاعدة بيانات بسيطة للأغذية الشائعة (سعرات per 100g)
FOODS = {
    "أرز مطبوخ": 130, "أرز": 130,
    "دجاج مشوي": 165, "دجاج": 165,
    "لحم بقري": 250, "لحم": 250,
    "بيض": 155, "بيضة": 77,
    "خبز": 265, "خبز أبيض": 265,
    "خبز أسمر": 247,
    "موز": 89, "تفاحة": 52, "برتقال": 47,
    "عدس مطبوخ": 116, "عدس": 116,
    "جبنة": 402, "جبن": 402, "جبنة قريش": 98,
    "حليب": 42, "لبن": 63,
    "شوكولاتة": 546,
    "بطاطس مقلية": 312, "بطاطس مشوية": 93,
    "تونة": 116, "سمك": 136,
    "زبادي": 59,
    "برجر": 295,
    "بيتزا": 266,
    "فول مدمس": 110, "فول": 110,
    "شاورما دجاج": 230, "شاورما": 280,
    "شاي بدون سكر": 2, "قهوة": 2,
    "عصير برتقال": 45, "كوكا كولا": 42,
    "مكرونة مطبوخة": 131, "مكرونة": 131,
}

user_daily = {}  # uid → {"items": [], "goal": 2000}

def home_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔍 بحث عن طعام",   callback_data="cal:search"),
        InlineKeyboardButton("📋 وجباتي اليوم",   callback_data="cal:today"),
        InlineKeyboardButton("🎯 تغيير هدفي",     callback_data="cal:goal"),
        InlineKeyboardButton("🗑 تصفير اليوم",    callback_data="cal:reset"),
        InlineKeyboardButton("🏪 متجر Boda",      url=STORE_URL),
    )
    return kb

def get_session(uid):
    if uid not in user_daily:
        user_daily[uid] = {"items": [], "goal": 2000, "mode": ""}
    return user_daily[uid]

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid  = msg.from_user.id
    sess = get_session(uid)
    sess["mode"] = ""
    total = sum(c for _, c in sess["items"])
    goal  = sess["goal"]
    bot.send_message(msg.chat.id,
        f"🥗 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        f"🎯 هدفك اليومي: <b>{goal}</b> سعرة\n"
        f"✅ استهلكت اليوم: <b>{total}</b> سعرة\n"
        f"📊 الباقي: <b>{max(0, goal-total)}</b> سعرة\n\n"
        "👇 <b>اختر ما تريد:</b>",
        reply_markup=home_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("cal:"))
def handle_cal(call):
    uid      = call.from_user.id
    act      = call.data.split(":")[1]
    cid, mid = call.message.chat.id, call.message.message_id
    sess     = get_session(uid)
    bot.answer_callback_query(call.id)

    if act == "search":
        sess["mode"] = "search"
        cats = list(FOODS.keys())[:5]
        example = " / ".join(cats)
        bot.edit_message_text(
            f"🔍 <b>ابحث عن طعام</b>\n\n"
            f"أرسل اسم الطعام:\n<i>مثال: {example}</i>\n\n"
            f"📝 أو أرسل: <code>الطعام الوزن_بالجرام</code>\n"
            f"<i>مثال: دجاج 200</i>",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 رجوع", callback_data="cal:back")))

    elif act == "today":
        items = sess["items"]
        total = sum(c for _, c in items)
        goal  = sess["goal"]
        if not items:
            bot.edit_message_text("📭 لم تُضف وجبات بعد!\n\nاضغط 🔍 للبحث وإضافة وجبة.",
                                  cid, mid, reply_markup=home_kb()); return
        lines = [f"📋 <b>وجباتك اليوم:</b>\n━━━━━━━━━━━"]
        for item, cal in items:
            lines.append(f"• {item}: <b>{cal}</b> سعرة")
        pct = min(100, int(total/goal*100))
        bar = "█" * (pct//10) + "░" * (10 - pct//10)
        lines += [f"━━━━━━━━━━━",
                  f"🔥 <b>الإجمالي: {total}</b> / {goal} سعرة",
                  f"[{bar}] {pct}%"]
        bot.edit_message_text("\n".join(lines), cid, mid, reply_markup=home_kb())

    elif act == "goal":
        sess["mode"] = "setgoal"
        bot.edit_message_text(
            "🎯 <b>حدد هدفك اليومي من السعرات:</b>\n\n"
            "<i>أرسل رقماً مثل: 1800 أو 2500</i>",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 رجوع", callback_data="cal:back")))

    elif act == "reset":
        sess["items"] = []
        bot.edit_message_text("✅ تم تصفير وجبات اليوم!", cid, mid, reply_markup=home_kb())

    elif act == "back":
        sess["mode"] = ""
        total = sum(c for _, c in sess["items"])
        goal  = sess["goal"]
        bot.edit_message_text(
            f"🥗 <b>{BOT_NAME}</b>\n\n🎯 هدفك: {goal} | ✅ استهلكت: {total}\n\n👇 اختر:",
            cid, mid, reply_markup=home_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    sess = get_session(uid)
    mode = sess.get("mode", "")

    if mode == "setgoal":
        try:
            goal = int(text)
            if not (500 <= goal <= 6000): raise ValueError
            sess["goal"] = goal
            sess["mode"] = ""
            bot.reply_to(msg, f"✅ <b>تم تحديد هدفك:</b> {goal} سعرة يومياً!", reply_markup=home_kb())
        except:
            bot.reply_to(msg, "⚠️ أدخل رقماً صحيحاً بين 500 و 6000")

    elif mode == "search":
        parts   = text.split()
        name    = parts[0] if parts else text
        weight  = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100

        # Find food
        found = None
        for k, v in FOODS.items():
            if name in k or k in name:
                found = (k, v); break

        if found:
            food_name, per100 = found
            calories = int(per100 * weight / 100)
            sess["items"].append((f"{food_name} ({weight}g)", calories))
            total = sum(c for _, c in sess["items"])
            goal  = sess["goal"]
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton("🔍 إضافة أخرى",  callback_data="cal:search"),
                InlineKeyboardButton("📋 وجباتي",       callback_data="cal:today"),
                InlineKeyboardButton("🏪 متجر Boda",    url=STORE_URL),
            )
            bot.reply_to(msg,
                f"✅ <b>تمت الإضافة!</b>\n\n"
                f"🍽️ {food_name} ({weight}g): <b>{calories}</b> سعرة\n\n"
                f"🔥 <b>اليوم: {total}</b> / {goal} سعرة",
                reply_markup=kb)
        else:
            bot.reply_to(msg,
                f"❌ لم أجد «{name}» في القاعدة.\n\n"
                f"<b>أمثلة متاحة:</b> دجاج / أرز / بيض / برجر / شاورما",
                reply_markup=home_kb())
    else:
        cmd_start(msg)

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "caltrack", allowed_updates=["message", "callback_query"])
