"""
bot_cvbuilder.py — CVBuilder | مُنشئ السيرة الذاتية
الاسم العربي: بوت السيرة الذاتية
English Name: CVBuilder
Username: @CVBuilderXBot
الوصف: أنشئ سيرة ذاتية احترافية خطوة بخطوة وأرسلها لك جاهزة بتنسيق نصي أنيق للنسخ.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[CVBuilder] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("cvbuilder")

from bot_base import get_token
TOKEN = get_token("BOT_CVBUILDER_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "بوت السيرة الذاتية"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_sessions = {}  # uid → {"step":, "data": {}}

STEPS = [
    ("name",      "👤 الاسم الكامل",          "مثال: محمد عبدالله"),
    ("title",     "💼 المسمى الوظيفي",         "مثال: مطور تطبيقات | مصمم جرافيك"),
    ("phone",     "📞 رقم الهاتف",             "مثال: +966501234567"),
    ("email",     "📧 البريد الإلكتروني",       "مثال: mohammed@email.com"),
    ("summary",   "📝 نبذة شخصية (2-3 جمل)",   "مثال: مطور برمجيات بخبرة 5 سنوات..."),
    ("experience","💼 الخبرة المهنية",           "مثال: شركة XYZ — مطور ويب (2020-2024)"),
    ("education", "🎓 المؤهل التعليمي",          "مثال: بكالوريوس حاسب آلي — جامعة الملك سعود 2019"),
    ("skills",    "⚡ المهارات (افصل بفاصلة)",   "مثال: Python، التصميم، إدارة المشاريع، Excel"),
    ("languages", "🌍 اللغات",                   "مثال: العربية (أصلية) | الإنجليزية (جيدة جداً)"),
]

def build_cv(data: dict) -> str:
    name  = data.get("name", "النسخة التجريبية")
    title = data.get("title", "")
    cv = [
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 <b>{name}</b>",
        f"💼 <i>{title}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📞 {data.get('phone', '—')}   📧 {data.get('email', '—')}",
        "",
        "📝 <b>نبذة شخصية:</b>",
        f"{data.get('summary', '—')}",
        "",
        "💼 <b>الخبرة المهنية:</b>",
        f"{data.get('experience', '—')}",
        "",
        "🎓 <b>التعليم:</b>",
        f"{data.get('education', '—')}",
        "",
        "⚡ <b>المهارات:</b>",
        f"{data.get('skills', '—')}",
        "",
        "🌍 <b>اللغات:</b>",
        f"{data.get('languages', '—')}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "<i>تم إنشاؤها بواسطة CVBuilder — متجر Boda 🏪</i>",
    ]
    return "\n".join(cv)

def step_kb(allow_skip=True):
    kb = InlineKeyboardMarkup(row_width=2)
    if allow_skip:
        kb.add(InlineKeyboardButton("⏭️ تخطي", callback_data="cv:skip"))
    kb.add(InlineKeyboardButton("❌ إلغاء", callback_data="cv:cancel"))
    return kb

def done_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔄 إنشاء سيرة جديدة", callback_data="cv:restart"),
        InlineKeyboardButton("🏪 متجر Boda",         url=STORE_URL),
    )
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid = msg.from_user.id
    user_sessions.pop(uid, None)
    bot.send_message(msg.chat.id,
        f"📄 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "أنشئ سيرة ذاتية احترافية في دقائق!\n\n"
        f"سأسألك {len(STEPS)} أسئلة بسيطة ثم أُرسل لك سيرتك جاهزة.\n\n"
        "👇 <b>اضغط للبدء:</b>",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("✅ ابدأ الآن", callback_data="cv:start"),
            InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL)))

@bot.callback_query_handler(func=lambda c: c.data.startswith("cv:"))
def handle_cv(call):
    uid      = call.from_user.id
    act      = call.data.split(":")[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if act in ("start", "restart"):
        user_sessions[uid] = {"step": 0, "data": {}}
        _ask_step(uid, cid, mid, edit=True)

    elif act == "skip":
        sess = user_sessions.get(uid, {})
        if sess:
            sess["step"] += 1
            user_sessions[uid] = sess
            _ask_step(uid, cid, mid, edit=True)

    elif act == "cancel":
        user_sessions.pop(uid, None)
        bot.edit_message_text("❌ تم إلغاء إنشاء السيرة.", cid, mid,
                              reply_markup=InlineKeyboardMarkup().add(
                                  InlineKeyboardButton("🔄 ابدأ مجدداً", callback_data="cv:start")))

def _ask_step(uid, cid, mid, edit=False):
    sess = user_sessions.get(uid)
    if not sess: return
    idx = sess["step"]
    if idx >= len(STEPS):
        # Done
        cv_text = build_cv(sess["data"])
        try:
            bot.edit_message_text(
                f"🎉 <b>سيرتك الذاتية جاهزة!</b>\n\n{cv_text}",
                cid, mid, reply_markup=done_kb())
        except:
            bot.send_message(cid, f"🎉 <b>سيرتك الذاتية:</b>\n\n{cv_text}", reply_markup=done_kb())
        user_sessions.pop(uid, None)
        return

    key, label, example = STEPS[idx]
    text = (f"📋 <b>الخطوة {idx+1}/{len(STEPS)}:</b> {label}\n\n"
            f"<i>{example}</i>")
    kb = step_kb(allow_skip=(idx > 3))
    try:
        if edit: bot.edit_message_text(text, cid, mid, reply_markup=kb)
        else:    bot.send_message(cid, text, reply_markup=kb)
    except:
        bot.send_message(cid, text, reply_markup=kb)

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    sess = user_sessions.get(uid)

    if not sess:
        cmd_start(msg); return

    idx = sess["step"]
    if idx < len(STEPS):
        key, _, _ = STEPS[idx]
        sess["data"][key] = text
        sess["step"] += 1
        user_sessions[uid] = sess
        _ask_step(uid, msg.chat.id, 0, edit=False)

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "cvbuilder", allowed_updates=["message", "callback_query"])
