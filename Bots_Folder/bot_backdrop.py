"""
bot_backdrop.py — BackDrop | إزالة الخلفية بالذكاء الاصطناعي
@BackDropAIBot
"""
import time, os, sys, io, threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import is_subscribed, send_subscription_prompt
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    from logger_config import get_logger, configure_windows_encoding
    configure_windows_encoding()
    log = get_logger("backdrop")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="[BackDrop] %(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("backdrop")

TOKEN     = os.getenv("BOT_BACKDROP_TOKEN", "8625867307:AAGIE032doGyzruuzRW6ebT-KY3qfwC55_0")
STORE_URL = "https://t.me/BodaStoreeBot"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

_sessions: dict = {}   # uid → raw_bytes

BG_MAP = {
    "transparent": (None,                  "شفاف PNG"),
    "white":       ((255,255,255,255),     "أبيض"),
    "black":       ((0,0,0,255),           "أسود"),
    "blur":        ("blur",                "ضبابي"),
    "studio":      ((20,20,30,255),        "استوديو"),
    "nature":      ((34,139,34,255),       "أخضر طبيعة"),
}

def bg_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("⬛ شفاف", callback_data="bg:transparent"),
        InlineKeyboardButton("⬜ أبيض", callback_data="bg:white"),
        InlineKeyboardButton("🖤 أسود", callback_data="bg:black"),
        InlineKeyboardButton("🌫️ ضبابي", callback_data="bg:blur"),
        InlineKeyboardButton("📸 استوديو", callback_data="bg:studio"),
        InlineKeyboardButton("🌲 طبيعة", callback_data="bg:nature")
    )
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def remove_background(raw: bytes, bg: str) -> bytes:
    from PIL import Image
    try:
        from rembg import remove as rembg_remove
    except ImportError:
        raise ImportError("pip install rembg")
    result = rembg_remove(raw)
    fg = Image.open(io.BytesIO(result)).convert("RGBA")
    color, _ = BG_MAP.get(bg, (None, "شفاف"))
    if color is None:
        out = io.BytesIO(); fg.save(out, "PNG"); out.seek(0); return out.read()
    if color == "blur":
        from PIL import ImageFilter
        orig    = Image.open(io.BytesIO(raw)).convert("RGBA")
        blurred = orig.filter(ImageFilter.GaussianBlur(18)).resize(fg.size)
        blurred.paste(fg, (0,0), fg)
        out = io.BytesIO(); blurred.save(out, "PNG"); out.seek(0); return out.read()
    canvas = Image.new("RGBA", fg.size, color)
    canvas.paste(fg, (0,0), fg); canvas = canvas.convert("RGB")
    out = io.BytesIO(); canvas.save(out, "JPEG", quality=95); out.seek(0); return out.read()

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.send_message(message.chat.id,
        "👋 <b>أهلاً في BackDrop!</b>\n\n"
        "احذف خلفية أي صورة بدقة عالية\n"
        "باستخدام الذكاء الاصطناعي!\n\n"
        "📸 <b>أرسل أي صورة الآن للبدء:</b>", reply_markup=app_kb())

@bot.message_handler(content_types=["photo", "document"])
def handle_image(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    uid = message.from_user.id
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type.startswith("image"):
        file_id = message.document.file_id
    else:
        bot.reply_to(message, "❌ أرسل صورة PNG أو JPG.")
        return
    try:
        finfo = bot.get_file(file_id)
        raw   = bot.download_file(finfo.file_path)
        _sessions[uid] = raw
        bot.reply_to(message, "🎨 <b>اختر لون خلفية الصورة:</b>", reply_markup=bg_kb())
    except Exception as e:
        bot.reply_to(message, f"❌ فشل استلام الصورة: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("bg:"))
def handle_bg(call):
    uid = call.from_user.id
    bg = call.data.split(":")[1]
    raw = _sessions.get(uid)
    if not raw:
        bot.answer_callback_query(call.id, "⚠️ انتهت الجلسة، أرسل الصورة من جديد.", show_alert=True)
        return
    
    _, bg_name = BG_MAP.get(bg, (None, "شفاف PNG"))
    wait = bot.edit_message_text(
        f"🤖 <b>الذكاء الاصطناعي يعمل...</b>\n"
        f"خلفية: <b>{bg_name}</b>\n<i>10-30 ثانية...</i>",
        call.message.chat.id, call.message.message_id)

    def process():
        try:
            result = remove_background(raw, bg)
            buf = io.BytesIO(result)
            ext = "png" if bg == "transparent" or bg == "blur" else "jpg"
            buf.name = f"result.{ext}"
            bot.send_document(call.message.chat.id, buf,
                caption=f"✅ <b>تمت الإزالة!</b>\n🎨 الخلفية: <b>{bg_name}</b>\n📦 {len(result)/1024:.0f} KB\n\n<b>بواسطة:</b> متجر تطبيقات Boda 🏪", reply_markup=app_kb())
            bot.delete_message(call.message.chat.id, wait.message_id)
            _sessions.pop(uid, None)
        except Exception as e:
            log.error(f"Remove BG: {e}")
            bot.edit_message_text(f"❌ <b>فشل</b>\n<code>{str(e)[:200]}</code>",
                                  call.message.chat.id, wait.message_id)
    threading.Thread(target=process, daemon=True).start()

@bot.message_handler(func=lambda m: True)
def guide(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.send_message(message.chat.id, "📸 <b>أرسل أي صورة لحذف خلفيتها!</b>", reply_markup=app_kb())

if __name__ == "__main__":
    from bot_base import start_polling
    start_polling(bot, "backdrop")
