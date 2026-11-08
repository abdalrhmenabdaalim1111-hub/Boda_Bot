"""
bot_logotext.py — LogoText | مُنشئ الشعارات النصية
الاسم العربي: مُنشئ الشعار
English Name: LogoText
Username: @LogoTextArtBot
الوصف: حوّل اسمك أو نصك لشعار نصي فني بأساليب متنوعة جاهز للنشر في البايو والمجموعات.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[LogoText] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("logotext")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "مُنشئ الشعار"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_text = {}  # uid → last text

STYLES = {
    "stars":   ("⭐ النجوم",    lambda t: f"✦ ✧ {t.upper()} ✧ ✦"),
    "fire":    ("🔥 النار",     lambda t: f"🔥 {t} 🔥\n{'━'*max(3,len(t))}"),
    "crown":   ("👑 التاج",     lambda t: f"👑 {t} 👑"),
    "waves":   ("〜 الأمواج",  lambda t: f"〜〜〜 {t} 〜〜〜"),
    "diamond": ("💎 الماسة",    lambda t: f"◆◈◆ {t} ◆◈◆"),
    "classic": ("🅰️ كلاسيك",   lambda t: f"【 {t} 】"),
    "minimal": ("➤ بسيط",     lambda t: f"➤ {t}"),
    "sparkle": ("✨ بريق",     lambda t: f"✨ {t.upper()} ✨\n{'·'*max(3,len(t))}"),
    "double":  ("🔲 مزدوج",    lambda t: f"『{t}』"),
    "box":     ("📦 صندوق",    lambda t: f"┌{'─'*(len(t)+2)}┐\n│ {t} │\n└{'─'*(len(t)+2)}┘"),
}

def styles_kb():
    kb = InlineKeyboardMarkup(row_width=3)
    btns = [InlineKeyboardButton(label, callback_data=f"logo:{k}") for k, (label, _) in STYLES.items()]
    kb.add(*btns)
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def result_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎨 أسلوب آخر",  callback_data="logo:change"),
        InlineKeyboardButton("📝 نص جديد",    callback_data="logo:new"),
        InlineKeyboardButton("🏪 متجر Boda",  url=STORE_URL),
    )
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid = msg.from_user.id
    user_text.pop(uid, None)
    bot.send_message(msg.chat.id,
        f"🎨 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "أرسل اسمك أو أي نص وسأحوّله لشعار نصي فني!\n\n"
        "✏️ <b>أرسل النص الآن:</b>",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL)))

@bot.callback_query_handler(func=lambda c: c.data.startswith("logo:"))
def handle_logo(call):
    uid      = call.from_user.id
    act      = call.data.split(":")[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if act in ("change",):
        txt = user_text.get(uid, "")
        if not txt:
            bot.edit_message_text("⚠️ أرسل النص أولاً.", cid, mid)
            return
        bot.edit_message_text(
            f"📝 <b>اختر أسلوب الشعار لـ:</b> «{txt}»",
            cid, mid, reply_markup=styles_kb())

    elif act == "new":
        user_text.pop(uid, None)
        bot.edit_message_text(
            "✏️ <b>أرسل النص الجديد:</b>", cid, mid)

    elif act in STYLES:
        txt = user_text.get(uid, "")
        if not txt:
            bot.edit_message_text("⚠️ أرسل النص أولاً.", cid, mid); return
        label, fn  = STYLES[act]
        result     = fn(txt)
        bot.edit_message_text(
            f"✅ <b>شعارك ({label}):</b>\n\n"
            f"<code>{result}</code>\n\n"
            f"<i>اضغط للنسخ</i>",
            cid, mid, reply_markup=result_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    if not text: cmd_start(msg); return
    if len(text) > 50:
        bot.reply_to(msg, "⚠️ النص طويل — أرسل 50 حرف كحد أقصى."); return
    user_text[uid] = text
    bot.reply_to(msg,
        f"📝 <b>اختر أسلوب الشعار لـ:</b> «{text}»",
        reply_markup=styles_kb())

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query"])
