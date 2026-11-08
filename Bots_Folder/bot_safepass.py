"""
bot_safepass.py — SafePass | مولّد كلمات المرور الآمنة
الاسم العربي: مولّد الباسورد
English Name: SafePass
Username: @SafePassXBot
الوصف: ينشئ كلمات مرور قوية وآمنة بطول وتعقيد تختاره أنت، مع نصائح لحمايتها.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging, secrets, string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_base import get_token

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[SafePass] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("safepass")

TOKEN = get_token("BOT_SAFEPASS_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "مولّد الباسورد"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

def store_kb(): 
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def main_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔒 قوية جداً (20)",     callback_data="pass:20:all"),
        InlineKeyboardButton("🔑 قوية (16)",           callback_data="pass:16:all"),
        InlineKeyboardButton("🔐 متوسطة (12)",         callback_data="pass:12:alnum"),
        InlineKeyboardButton("🗝️ بسيطة (8)",           callback_data="pass:8:alnum"),
        InlineKeyboardButton("🔢 أرقام فقط (6)",       callback_data="pass:6:digits"),
        InlineKeyboardButton("🔄 توليد مخصص",         callback_data="pass:custom"),
        InlineKeyboardButton("🏪 متجر Boda",           url=STORE_URL),
    )
    return kb

def _strength_bar(password):
    score = 0
    if any(c.isupper() for c in password): score += 1
    if any(c.islower() for c in password): score += 1
    if any(c.isdigit() for c in password): score += 1
    if any(c in string.punctuation for c in password): score += 1
    if len(password) >= 16: score += 1
    bars  = ["🔴 ضعيفة جداً", "🟠 ضعيفة", "🟡 متوسطة", "🟢 قوية", "💪 قوية جداً"]
    return bars[min(score, 4)]

def gen_password(length: int, charset: str) -> str:
    chars = {
        "all":    string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}",
        "alnum":  string.ascii_letters + string.digits,
        "digits": string.digits,
    }.get(charset, string.ascii_letters + string.digits)
    return "".join(secrets.choice(chars) for _ in range(length))

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        f"🔐 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "أنشئ كلمات مرور قوية وآمنة في ثواني!\n\n"
        "👇 <b>اختر نوع الكلمة:</b>",
        reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("pass:"))
def handle_pass(call):
    parts = call.data.split(":")
    cid   = call.message.chat.id
    mid   = call.message.message_id
    bot.answer_callback_query(call.id)

    if parts[1] == "custom":
        bot.edit_message_text(
            "✏️ <b>توليد مخصص</b>\n\n"
            "أرسل: <code>الطول النوع</code>\n"
            "الأنواع: <code>all</code> / <code>alnum</code> / <code>digits</code>\n"
            "<b>مثال:</b> <code>24 all</code>",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 رجوع", callback_data="pass:back")))
        return

    if parts[1] == "back":
        bot.edit_message_text(
            f"🔐 <b>{BOT_NAME}</b>\n\n👇 اختر نوع الكلمة:", 
            cid, mid, reply_markup=main_kb())
        return

    length  = int(parts[1])
    charset = parts[2]
    pwd = gen_password(length, charset)
    strength = _strength_bar(pwd)

    regen_data = f"pass:{length}:{charset}"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔄 توليد أخرى", callback_data=regen_data),
        InlineKeyboardButton("🏠 رجوع",        callback_data="pass:back"),
        InlineKeyboardButton("🏪 متجر Boda",   url=STORE_URL),
    )
    bot.edit_message_text(
        f"✅ <b>كلمة مرورك الجديدة:</b>\n\n"
        f"<code>{pwd}</code>\n\n"
        f"📊 القوة: {strength}\n"
        f"📏 الطول: {length} حرف\n\n"
        f"⚠️ <i>اضغط على الكلمة لنسخها</i>\n"
        f"🔒 <i>احفظها في مكان آمن ولا تشاركها</i>",
        cid, mid, reply_markup=kb)

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    text = (msg.text or "").strip().split()
    try:
        length  = int(text[0])
        charset = text[1] if len(text) > 1 else "all"
        if not (4 <= length <= 64):
            raise ValueError("length out of range")
        pwd      = gen_password(length, charset)
        strength = _strength_bar(pwd)
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
        bot.reply_to(msg,
            f"✅ <b>كلمة مرورك:</b>\n<code>{pwd}</code>\n\n"
            f"📊 القوة: {strength}\n📏 الطول: {length} حرف",
            reply_markup=kb)
    except:
        cmd_start(msg)

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "safepass", allowed_updates=["message", "callback_query"])
