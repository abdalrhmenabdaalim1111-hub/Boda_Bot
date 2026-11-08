"""
bot_shortlink.py — ShortLink | مختصر الروابط الذكي
الاسم العربي: مختصر الروابط
English Name: ShortLink
Username: @ShortLinkXBot
الوصف: يختصر أي رابط طويل ويُنشئ رابطاً قصيراً نظيفاً في ثانية واحدة مع إحصائيات.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import requests
from typing import Optional
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_base import get_token

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[ShortLink] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("shortlink")

TOKEN = get_token("BOT_SHORTLINK_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "مختصر الروابط"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

def store_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def shorten_url(long_url: str) -> Optional[str]:
    """استخدام TinyURL API مجاني"""
    try:
        resp = requests.get(
            f"https://tinyurl.com/api-create.php?url={long_url}",
            timeout=10
        )
        if resp.status_code == 200 and resp.text.startswith("http"):
            return resp.text.strip()
    except Exception as e:
        log.error(f"TinyURL error: {e}")
    # Fallback: is.gd
    try:
        resp = requests.get(
            f"https://is.gd/create.php?format=simple&url={long_url}",
            timeout=10
        )
        if resp.status_code == 200:
            return resp.text.strip()
    except:
        pass
    return None

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        f"🔗 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "أرسل أي رابط طويل وسأختصره لك فوراً!\n\n"
        "<b>مثال:</b>\n"
        "<code>https://www.youtube.com/watch?v=dQw4w9WgXcQ</code>\n\n"
        "⬇️ <i>أرسل الرابط الآن:</i>",
        reply_markup=store_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    text = (msg.text or "").strip()
    if not text.startswith("http"):
        if text.startswith("www."):
            text = "https://" + text
        else:
            bot.reply_to(msg,
                "⚠️ أرسل رابطاً صحيحاً يبدأ بـ <code>http://</code> أو <code>https://</code>",
                reply_markup=store_kb())
            return

    wait_msg = bot.reply_to(msg, "⏳ <i>جاري اختصار الرابط...</i>")
    short = shorten_url(text)

    if short:
        savings = max(0, len(text) - len(short))
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🔗 افتح الرابط المختصر", url=short),
            InlineKeyboardButton("🏪 متجر Boda",           url=STORE_URL),
        )
        bot.edit_message_text(
            f"✅ <b>تم الاختصار بنجاح!</b>\n\n"
            f"🔗 <b>الرابط المختصر:</b>\n<code>{short}</code>\n\n"
            f"📏 <b>الأصلي:</b> {len(text)} حرف\n"
            f"📏 <b>المختصر:</b> {len(short)} حرف\n"
            f"💾 <b>وفّرت:</b> {savings} حرف\n\n"
            f"<i>اضغط على الرابط لنسخه</i>",
            msg.chat.id, wait_msg.message_id, reply_markup=kb)
    else:
        bot.edit_message_text(
            "❌ <b>فشل الاختصار</b>\n\n"
            "تأكد من أن الرابط صحيح وقابل للوصول، ثم أعد المحاولة.",
            msg.chat.id, wait_msg.message_id, reply_markup=store_kb())

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "shortlink", allowed_updates=["message", "callback_query"])
