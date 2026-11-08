"""
bot_pollmaster.py — PollMaster | صانع الاستطلاعات الذكي
الاسم العربي: بوت التصويت
English Name: PollMaster
Username: @PollMasterXBot
الوصف: أنشئ استطلاعات رأي واسئلة تصويت احترافية للمجموعات في ثواني، مع إحصائيات فورية.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[PollMaster] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("pollmaster")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "بوت التصويت"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_mode   = {}   # uid → {"step": "", "question": "", "options": [], "anonymous": True}
active_polls = {}  # poll_id → {"question": "", "options": [], "votes": {}, "voters": set()}

TEMPLATES = [
    ("⭐ تقييم",    "كيف تقيّم هذه الخدمة؟", ["⭐ ممتاز", "👍 جيد", "😐 عادي", "👎 سيء"]),
    ("✅ نعم/لا",   "هل توافق على هذا؟",      ["✅ نعم", "❌ لا", "🤔 ربما"]),
    ("🗳️ اختيار",  "ما هو خيارك المفضل؟",   ["الخيار الأول", "الخيار الثاني", "الخيار الثالث"]),
    ("📅 موعد",    "متى يناسبك الاجتماع؟",   ["الصباح", "الظهير", "المساء"]),
]

def home_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ استطلاع جديد", callback_data="pm:new"),
        InlineKeyboardButton("📋 قوالب جاهزة",  callback_data="pm:templates"),
        InlineKeyboardButton("📊 استطلاع سريع", callback_data="pm:quick"),
        InlineKeyboardButton("🏪 متجر Boda",    url=STORE_URL),
    )
    return kb

def template_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for i, (name, q, _) in enumerate(TEMPLATES):
        kb.add(InlineKeyboardButton(f"{name}: {q}", callback_data=f"pm:tmpl:{i}"))
    kb.add(InlineKeyboardButton("🔙 رجوع", callback_data="pm:home"))
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid = msg.from_user.id
    user_mode.pop(uid, None)
    bot.send_message(msg.chat.id,
        f"🗳️ <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "أنشئ استطلاعات رأي احترافية للمجموعات!\n\n"
        "✅ استطلاعات متعددة الخيارات\n"
        "📋 قوالب جاهزة للاستخدام\n"
        "📊 إحصائيات فورية\n\n"
        "👇 <b>اختر:</b>",
        reply_markup=home_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("pm:"))
def handle_pm(call):
    uid      = call.from_user.id
    parts    = call.data.split(":")
    act      = parts[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if act == "home":
        user_mode.pop(uid, None)
        bot.edit_message_text(
            f"🗳️ <b>{BOT_NAME}</b>\n\n👇 اختر:", cid, mid, reply_markup=home_kb())

    elif act == "new":
        user_mode[uid] = {"step": "question", "question": "", "options": [], "anonymous": True}
        bot.edit_message_text(
            "➕ <b>استطلاع جديد</b>\n\n"
            "الخطوة 1/2: أرسل <b>سؤال الاستطلاع</b>:\n\n"
            "<i>مثال: ما هو لون الفريق المفضل لديك؟</i>",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("❌ إلغاء", callback_data="pm:home")))

    elif act == "templates":
        bot.edit_message_text(
            "📋 <b>القوالب الجاهزة:</b>\n\nاختر قالب لإرساله مباشرة:",
            cid, mid, reply_markup=template_kb())

    elif act == "quick":
        # Send a quick yes/no poll using Telegram native poll
        try:
            bot.send_poll(
                cid,
                question="هل أنت موافق؟",
                options=["✅ نعم", "❌ لا", "🤔 ربما"],
                is_anonymous=False,
            )
            bot.delete_message(cid, mid)
        except Exception as e:
            bot.edit_message_text(f"❌ خطأ: {e}", cid, mid, reply_markup=home_kb())

    elif act == "tmpl" and len(parts) > 2:
        idx  = int(parts[2])
        name, question, options = TEMPLATES[idx]
        try:
            bot.send_poll(cid, question=question, options=options, is_anonymous=True)
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(
                InlineKeyboardButton("📋 قوالب أخرى", callback_data="pm:templates"),
                InlineKeyboardButton("🏪 متجر Boda",  url=STORE_URL),
            )
            bot.edit_message_text(f"✅ تم إرسال استطلاع: {name}!", cid, mid, reply_markup=kb)
        except Exception as e:
            bot.edit_message_text(f"❌ خطأ: {e}", cid, mid, reply_markup=home_kb())

    elif act == "anon" and len(parts) > 2:
        is_anon = (parts[2] == "yes")
        sess    = user_mode.get(uid, {})
        if sess.get("step") == "sending":
            q    = sess["question"]
            opts = sess["options"]
            try:
                bot.send_poll(cid, question=q, options=opts, is_anonymous=is_anon)
                user_mode.pop(uid, None)
                kb = InlineKeyboardMarkup(row_width=1)
                kb.add(
                    InlineKeyboardButton("➕ استطلاع آخر", callback_data="pm:new"),
                    InlineKeyboardButton("🏪 متجر Boda",   url=STORE_URL),
                )
                bot.edit_message_text("✅ <b>تم إرسال الاستطلاع بنجاح!</b>", cid, mid, reply_markup=kb)
            except Exception as e:
                bot.edit_message_text(f"❌ خطأ في الإرسال: {e}", cid, mid, reply_markup=home_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    sess = user_mode.get(uid, {})
    step = sess.get("step", "")

    if step == "question":
        if len(text) < 3:
            bot.reply_to(msg, "⚠️ السؤال قصير جداً! أكتب سؤالاً واضحاً."); return
        sess["question"] = text
        sess["step"]     = "options"
        user_mode[uid]   = sess
        bot.reply_to(msg,
            "✅ <b>سؤال محفوظ!</b>\n\n"
            "الخطوة 2/2: أرسل <b>خيارات الاستطلاع</b>\n"
            "كل خيار في سطر منفصل (2-10 خيارات)\n\n"
            "<b>مثال:</b>\n<code>أحمر\nأزرق\nأخضر\nأصفر</code>")

    elif step == "options":
        options = [o.strip() for o in text.split("\n") if o.strip()]
        if len(options) < 2:
            bot.reply_to(msg, "⚠️ أرسل خيارين على الأقل — كل خيار في سطر منفصل."); return
        if len(options) > 10:
            options = options[:10]
            bot.reply_to(msg, "⚠️ تم الاكتفاء بأول 10 خيارات.")

        sess["options"] = options
        sess["step"]    = "sending"
        user_mode[uid]  = sess

        preview = "\n".join(f"• {o}" for o in options)
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("👤 مجهول", callback_data="pm:anon:yes"),
            InlineKeyboardButton("📛 باسم",  callback_data="pm:anon:no"),
            InlineKeyboardButton("❌ إلغاء", callback_data="pm:home"),
        )
        bot.reply_to(msg,
            f"📋 <b>معاينة الاستطلاع:</b>\n\n"
            f"❓ <b>{sess['question']}</b>\n\n{preview}\n\n"
            f"هل الاستطلاع مجهول الهوية أم بالأسماء؟",
            reply_markup=kb)
    else:
        cmd_start(msg)

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query", "poll"])
