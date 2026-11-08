"""
bot_formatfix.py — FormatFix | محوّل الصور الاحترافي
@FormatFix1Bot
"""
import time, os, sys, io, threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import is_subscribed, send_subscription_prompt
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError: pass

try:
    from logger_config import get_logger, configure_windows_encoding
    configure_windows_encoding()
    log = get_logger("formatfix")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="[FormatFix] %(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("formatfix")

TOKEN     = os.getenv("BOT_FORMATFIX_TOKEN", "8319889739:AAH-3xpmsitsmms8KM471wMm0Vm21kURyuY")
STORE_URL = "https://t.me/BodaStoreeBot"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)
_sessions: dict = {}   # uid → {raw: bytes}

def convert_image(raw: bytes, target: str) -> tuple:
    from PIL import Image
    img = Image.open(io.BytesIO(raw))
    if target == "pdf":
        img = img.convert("RGB") if img.mode in ("RGBA","P") else img
        buf = io.BytesIO(); img.save(buf, "PDF"); return buf.getvalue(), "pdf", "application/pdf"
    elif target == "jpg":
        bg = Image.new("RGB", img.size, (255,255,255))
        if img.mode == "RGBA": bg.paste(img, mask=img.split()[3])
        elif img.mode == "P":  bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
        else: bg = img.convert("RGB")
        buf = io.BytesIO(); bg.save(buf, "JPEG", quality=95); return buf.getvalue(), "jpg", "image/jpeg"
    elif target == "webp":
        buf = io.BytesIO(); img.save(buf, "WEBP", quality=92); return buf.getvalue(), "webp", "image/webp"
    elif target == "png":
        buf = io.BytesIO(); img.convert("RGBA").save(buf, "PNG"); return buf.getvalue(), "png", "image/png"
    raise ValueError(f"Unknown format: {target}")

def format_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📄 PDF", callback_data="fmt:pdf"),
        InlineKeyboardButton("🖼️ JPG", callback_data="fmt:jpg"),
        InlineKeyboardButton("🖼️ PNG", callback_data="fmt:png"),
        InlineKeyboardButton("🌐 WEBP", callback_data="fmt:webp")
    )
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    if not is_subscribed(bot, msg.from_user.id):
        send_subscription_prompt(bot, msg.chat.id)
        return
    bot.send_message(msg.chat.id,
        "👋 <b>أهلاً في FormatFix!</b>\n\n"
        "حوّل صورك بين صيغ PDF,\n"
        "JPG, PNG, WEBP\n\n"
        "📸 <b>أرسل أي صورة الآن للبدء:</b>", reply_markup=app_kb())

@bot.message_handler(content_types=["photo", "document"])
def handle_image(msg):
    if not is_subscribed(bot, msg.from_user.id):
        send_subscription_prompt(bot, msg.chat.id)
        return
    uid = msg.from_user.id
    if msg.photo: fid = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type.startswith("image"): fid = msg.document.file_id
    else:
        bot.reply_to(msg, "❌ أرسل صورة (JPG, PNG, WEBP...)"); return
    try:
        raw = bot.download_file(bot.get_file(fid).file_path)
        _sessions[uid] = raw
        bot.reply_to(msg, "🔄 <b>الصورة وصلت! اختر الصيغة للتحويل:</b>", reply_markup=format_kb())
    except Exception as e:
        bot.reply_to(msg, f"❌ فشل الاستلام: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("fmt:"))
def handle_format(call):
    uid = call.from_user.id
    target = call.data.split(":")[1]
    raw = _sessions.get(uid)
    if not raw:
        bot.answer_callback_query(call.id, "❌ انتهت الجلسة، أرسل الصورة مرة أخرى.", show_alert=True)
        return
    bot.edit_message_text(f"⏳ <b>جاري التحويل إلى {target.upper()}...</b>", call.message.chat.id, call.message.message_id)
    def convert():
        try:
            result, ext, _ = convert_image(raw, target)
            buf = io.BytesIO(result); buf.name = f"output.{ext}"
            bot.send_document(call.message.chat.id, buf,
                caption=f"✅ <b>تم التحويل إلى {ext.upper()}!</b>\n📦 {len(result)/1024:.0f} KB\n\n<b>بواسطة:</b> متجر تطبيقات Boda 🏪", reply_markup=app_kb())
            bot.delete_message(call.message.chat.id, call.message.message_id)
            _sessions.pop(uid, None)
        except Exception as e:
            log.error(e)
            bot.edit_message_text(f"❌ خطأ: {e}", call.message.chat.id, call.message.message_id)
    threading.Thread(target=convert, daemon=True).start()

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "formatfix")
