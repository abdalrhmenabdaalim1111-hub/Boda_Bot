"""
bot_textspeak.py — TextSpeak | محوّل النص لصوت
الاسم العربي: محوّل النص لصوت
English Name: TextSpeak
Username: @TextSpeakXBot
الوصف: حوّل أي نص عربي أو إنجليزي لملف صوتي مجاناً باستخدام تقنية القراءة الذكية.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, io, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[TextSpeak] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("textspeak")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "محوّل النص لصوت"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_mode = {}  # uid → lang

LANGS = {
    "ar": ("🇸🇦 عربي",      "ar"),
    "en": ("🇺🇸 English",    "en"),
    "tr": ("🇹🇷 Türkçe",     "tr"),
    "fr": ("🇫🇷 Français",   "fr"),
}

def lang_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    btns = [InlineKeyboardButton(label, callback_data=f"ts:lang:{code}") for code, (label, _) in LANGS.items()]
    kb.add(*btns)
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def store_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def text_to_speech(text: str, lang: str) -> bytes:
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except ImportError:
        raise ImportError("gtts not installed — run: pip install gtts")

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid = msg.from_user.id
    user_mode.pop(uid, None)
    bot.send_message(msg.chat.id,
        f"🔊 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "حوّل أي نص لصوت في ثواني!\n\n"
        "👇 <b>اختر اللغة أولاً:</b>",
        reply_markup=lang_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("ts:"))
def handle_ts(call):
    parts    = call.data.split(":")
    uid      = call.from_user.id
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if parts[1] == "lang":
        lang = parts[2]
        user_mode[uid] = lang
        label = LANGS.get(lang, ("عربي", "ar"))[0]
        bot.edit_message_text(
            f"✅ <b>اللغة: {label}</b>\n\n"
            "✏️ <b>أرسل النص الآن:</b>\n"
            "<i>حد أقصى: 500 حرف</i>",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔄 تغيير اللغة", callback_data="ts:back"),
                InlineKeyboardButton("🏪 متجر Boda",   url=STORE_URL)))

    elif parts[1] == "back":
        user_mode.pop(uid, None)
        bot.edit_message_text(
            f"🔊 <b>{BOT_NAME}</b>\n\n👇 اختر اللغة:",
            cid, mid, reply_markup=lang_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    lang = user_mode.get(uid)

    if not lang:
        cmd_start(msg); return

    if not text:
        bot.reply_to(msg, "⚠️ أرسل نصاً للتحويل."); return

    if len(text) > 500:
        text = text[:500]
        bot.reply_to(msg, "⚠️ تم اقتصار النص على 500 حرف.")

    wait = bot.reply_to(msg, f"🔊 <i>جاري تحويل النص إلى صوت...</i>")
    try:
        audio = text_to_speech(text, lang)
        buf   = io.BytesIO(audio); buf.name = "speech.mp3"
        kb    = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🔄 تحويل آخر",    callback_data="ts:back"),
            InlineKeyboardButton("🏪 متجر Boda",    url=STORE_URL),
        )
        bot.send_audio(msg.chat.id, buf,
            caption=f"🔊 <b>تم التحويل!</b>\n<i>{text[:60]}...</i>\n\n<b>بواسطة:</b> متجر Boda 🏪",
            reply_markup=kb)
        bot.delete_message(msg.chat.id, wait.message_id)

    except ImportError:
        bot.edit_message_text(
            "❌ <b>مكتبة gTTS غير مثبتة</b>\n<code>pip install gtts</code>",
            msg.chat.id, wait.message_id, reply_markup=store_kb())
    except Exception as e:
        log.error(f"TTS error: {e}")
        bot.edit_message_text(
            f"❌ حدث خطأ: <code>{str(e)[:200]}</code>",
            msg.chat.id, wait.message_id, reply_markup=lang_kb())

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "textspeak", allowed_updates=["message", "callback_query"])
