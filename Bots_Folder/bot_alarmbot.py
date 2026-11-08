"""
bot_alarmbot.py — AlarmBot | بوت التذكيرات الذكي
الاسم العربي: بوت المنبّه
English Name: AlarmBot
Username: @AlarmBotXPro
الوصف: اضبط تذكيرات ومنبهات بأوقات محددة وسيُرسل البوت لك رسالة تنبيه في وقتها بالضبط.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging, threading, time
from datetime import datetime, timedelta
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[AlarmBot] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("alarmbot")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "بوت المنبّه"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

alarms    = {}   # uid → [{"text": str, "fire_at": datetime, "id": int}]
alarm_id  = [0]
user_mode = {}   # uid → "setting"

lock = threading.Lock()

def get_alarms(uid):
    return alarms.get(str(uid), [])

def add_alarm(uid, text, when: datetime):
    with lock:
        alarm_id[0] += 1
        aid = alarm_id[0]
        key = str(uid)
        if key not in alarms: alarms[key] = []
        alarms[key].append({"text": text, "fire_at": when, "id": aid})
    return aid

def home_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("⏰ تذكير جديد", callback_data="ab:new"),
        InlineKeyboardButton("📋 تذكيراتي",   callback_data="ab:list"),
        InlineKeyboardButton("🗑 حذف الكل",   callback_data="ab:clear"),
        InlineKeyboardButton("🏪 متجر Boda",  url=STORE_URL),
    )
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid = msg.from_user.id
    user_mode.pop(uid, None)
    count = len(get_alarms(uid))
    bot.send_message(msg.chat.id,
        f"⏰ <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "اضبط تذكيرات ذكية وسأُنبّهك في وقتها!\n\n"
        f"⏳ لديك <b>{count}</b> تذكير نشط.\n\n"
        "👇 <b>اختر:</b>",
        reply_markup=home_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("ab:"))
def handle_ab(call):
    uid      = call.from_user.id
    act      = call.data.split(":")[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if act == "new":
        user_mode[uid] = "setting"
        bot.edit_message_text(
            "⏰ <b>تذكير جديد</b>\n\n"
            "أرسل التذكير بهذا الشكل:\n"
            "<code>الوقت | الرسالة</code>\n\n"
            "<b>أمثلة:</b>\n"
            "<code>10:30 | اجتماع مع المدير</code>\n"
            "<code>+30 | مراجعة البريد</code> (بعد 30 دقيقة)\n"
            "<code>+2h | وجبة الغداء</code> (بعد ساعتين)",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("❌ إلغاء", callback_data="ab:home")))

    elif act == "list":
        alarms_list = get_alarms(uid)
        if not alarms_list:
            bot.edit_message_text("📭 لا توجد تذكيرات نشطة.\n\nأضف تذكيراً جديداً:",
                                  cid, mid, reply_markup=home_kb()); return
        lines = ["📋 <b>تذكيراتك النشطة:</b>\n"]
        now   = datetime.now()
        for a in alarms_list:
            diff = a["fire_at"] - now
            mins = int(diff.total_seconds() / 60)
            time_str = a["fire_at"].strftime("%H:%M")
            remaining = f"{mins} دقيقة" if mins < 60 else f"{mins//60} ساعة"
            lines.append(f"⏰ <b>{time_str}</b> — {a['text']}\n   <i>بعد {remaining}</i>")
        bot.edit_message_text("\n".join(lines), cid, mid, reply_markup=home_kb())

    elif act == "clear":
        alarms.pop(str(uid), None)
        bot.edit_message_text("✅ تم حذف جميع التذكيرات!", cid, mid, reply_markup=home_kb())

    elif act == "home":
        user_mode.pop(uid, None)
        bot.edit_message_text(f"⏰ <b>{BOT_NAME}</b>\n\n👇 اختر:", cid, mid, reply_markup=home_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    mode = user_mode.get(uid, "")

    if mode == "setting":
        try:
            when   = None
            note   = text
            if "|" in text:
                time_part, note = [x.strip() for x in text.split("|", 1)]
            else:
                time_part = text.split()[0]
                note      = " ".join(text.split()[1:]) or "⏰ تذكير!"

            now = datetime.now()
            if time_part.startswith("+"):
                # Relative
                t = time_part[1:]
                if t.endswith("h"):
                    when = now + timedelta(hours=int(t[:-1]))
                elif t.endswith("m") or t.isdigit():
                    mins = int(t.replace("m", ""))
                    when = now + timedelta(minutes=mins)
            else:
                h, m = map(int, time_part.split(":"))
                when = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if when <= now:
                    when += timedelta(days=1)

            if not when: raise ValueError("لم أفهم الوقت")

            aid = add_alarm(uid, note, when)
            diff = int((when - datetime.now()).total_seconds())
            remaining = f"{diff//60} دقيقة" if diff < 3600 else f"{diff//3600} ساعة و{(diff%3600)//60} دقيقة"

            user_mode.pop(uid, None)
            bot.reply_to(msg,
                f"✅ <b>تم ضبط التذكير!</b>\n\n"
                f"⏰ الوقت: <b>{when.strftime('%H:%M')}</b>\n"
                f"📝 الرسالة: <i>{note}</i>\n"
                f"⏳ بعد: {remaining}",
                reply_markup=home_kb())

            # Schedule alarm
            def fire():
                wait = (when - datetime.now()).total_seconds()
                if wait > 0: time.sleep(wait)
                try:
                    bot.send_message(msg.chat.id,
                        f"🔔 <b>تنبيه!</b>\n\n⏰ {note}\n\n<i>– AlarmBot</i>",
                        reply_markup=home_kb())
                except: pass
                with lock:
                    key = str(uid)
                    if key in alarms:
                        alarms[key] = [a for a in alarms[key] if a["id"] != aid]
            threading.Thread(target=fire, daemon=True).start()

        except Exception as e:
            bot.reply_to(msg,
                f"⚠️ لم أفهم الوقت. <i>({e})</i>\n\n"
                "جرب:\n<code>10:30 | اجتماع</code>\n"
                "أو: <code>+30 | راجع البريد</code>")
    else:
        cmd_start(msg)

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "alarmbot", allowed_updates=["message", "callback_query"])
