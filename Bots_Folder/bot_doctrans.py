"""
bot_doctrans.py — DocTrans | مترجم النصوص السريع
الاسم العربي: مترجم الملفات
English Name: DocTrans
Username: @DocTransNowBot
الوصف: يترجم أي نص أو رسالة فورياً بين العربية والإنجليزية والفرنسية والتركية والألمانية والإسبانية.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_base import get_token

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[DocTrans] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("doctrans")

TOKEN = get_token("BOT_DOCTRANS_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "مترجم الملفات"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

LANGS = {
    "ar": "🇸🇦 عربي",
    "en": "🇺🇸 English",
    "fr": "🇫🇷 Français",
    "tr": "🇹🇷 Türkçe",
    "de": "🇩🇪 Deutsch",
    "es": "🇪🇸 Español",
    "ru": "🇷🇺 Русский",
    "zh": "🇨🇳 中文",
}

user_mode = {}  # uid → {"to_lang": "en", "pending_text": ""}

def lang_kb(prefix="to"):
    kb = InlineKeyboardMarkup(row_width=4)
    btns = [InlineKeyboardButton(label, callback_data=f"dt:{prefix}:{code}")
            for code, label in LANGS.items()]
    kb.add(*btns)
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def translate_text(text: str, target_lang: str) -> str:
    """استخدام MyMemory API مجاني (1000 طلب/يوم)"""
    try:
        resp = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": f"auto|{target_lang}"},
            timeout=10
        )
        data = resp.json()
        if data.get("responseStatus") == 200:
            result = data["responseData"]["translatedText"]
            if result and result.lower() != text.lower():
                return result
    except Exception as e:
        log.error(f"Translation error: {e}")

    # Fallback: LibreTranslate (if available)
    try:
        resp2 = requests.post(
            "https://libretranslate.de/translate",
            json={"q": text, "source": "auto", "target": target_lang},
            timeout=8
        )
        return resp2.json().get("translatedText", "❌ فشل الترجمة")
    except:
        return "❌ فشل الاتصال بخادم الترجمة. حاول مرة أخرى."

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    uid = msg.from_user.id
    user_mode[uid] = {"to_lang": "en"}
    bot.send_message(msg.chat.id,
        f"🌍 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "ترجمة فورية لأي نص إلى 8 لغات!\n\n"
        "👇 <b>اختر لغة الترجمة:</b>",
        reply_markup=lang_kb("to"))

@bot.callback_query_handler(func=lambda c: c.data.startswith("dt:"))
def handle_dt(call):
    uid      = call.from_user.id
    parts    = call.data.split(":")
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if parts[1] == "to":
        lang = parts[2]
        if uid not in user_mode: user_mode[uid] = {}
        user_mode[uid]["to_lang"] = lang
        label = LANGS.get(lang, lang)

        pending = user_mode[uid].get("pending_text")
        if pending:
            # Translate immediately
            wait = bot.edit_message_text(f"⏳ <i>جاري الترجمة إلى {label}...</i>", cid, mid)
            result = translate_text(pending, lang)
            user_mode[uid].pop("pending_text", None)
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(
                InlineKeyboardButton("🔄 ترجمة لغة أخرى", callback_data="dt:change"),
                InlineKeyboardButton("🏪 متجر Boda",       url=STORE_URL),
            )
            bot.edit_message_text(
                f"✅ <b>الترجمة ({label}):</b>\n\n"
                f"<code>{result}</code>\n\n"
                f"<i>النص الأصلي: {pending[:100]}</i>",
                cid, mid, reply_markup=kb)
        else:
            bot.edit_message_text(
                f"🌍 <b>لغة الهدف: {label}</b>\n\n✏️ <b>أرسل النص للترجمة:</b>",
                cid, mid, reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🔄 تغيير اللغة", callback_data="dt:change"),
                    InlineKeyboardButton("🏪 متجر Boda",   url=STORE_URL)))

    elif parts[1] == "change":
        bot.edit_message_text("🌍 <b>اختر لغة الهدف:</b>", cid, mid, reply_markup=lang_kb("to"))

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    if not text: cmd_start(msg); return

    if uid not in user_mode or not user_mode[uid].get("to_lang"):
        user_mode[uid] = {"to_lang": "", "pending_text": text}
        bot.reply_to(msg, "🌍 <b>اختر لغة الترجمة:</b>", reply_markup=lang_kb("to"))
        return

    lang  = user_mode[uid]["to_lang"]
    label = LANGS.get(lang, lang)
    wait  = bot.reply_to(msg, f"⏳ <i>جاري الترجمة إلى {label}...</i>")
    result = translate_text(text, lang)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔄 ترجمة لغة أخرى", callback_data="dt:change"),
        InlineKeyboardButton("🏪 متجر Boda",       url=STORE_URL),
    )
    bot.edit_message_text(
        f"✅ <b>الترجمة ({label}):</b>\n\n"
        f"<code>{result}</code>",
        msg.chat.id, wait.message_id, reply_markup=kb)

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "doctrans", allowed_updates=["message", "callback_query"])
