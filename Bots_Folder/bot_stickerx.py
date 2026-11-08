"""
bot_stickerx.py — StickerX Bot | تحويل الصور إلى ملصقات تيليجرام
@StickerXMakerBot
"""

import time
import os, sys, io, threading, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import is_subscribed, send_subscription_prompt
from bot_base import get_token

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO,
                    format="[StickerX] %(asctime)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("stickerx")

TOKEN = get_token("BOT_STICKERX_TOKEN")
STORE_URL = "https://t.me/BodaStoreBot"
SIZE      = (512, 512)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

_sessions: dict = {}

def bg_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("⬛ شفاف", callback_data="bg:transparent"),
        InlineKeyboardButton("⬜ أبيض", callback_data="bg:white"),
        InlineKeyboardButton("🖤 أسود", callback_data="bg:black")
    )
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def make_sticker(img_bytes: bytes, remove_bg: bool = False) -> bytes:
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    img.thumbnail(SIZE, Image.LANCZOS)
    
    if remove_bg:
        try:
            from rembg import remove as rembg_remove
            img = rembg_remove(img)
        except ImportError:
            log.warning("rembg not installed, skipping BG removal")
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    offset = ((SIZE[0] - img.width) // 2, (SIZE[1] - img.height) // 2)
    canvas.paste(img, offset)

    buf = io.BytesIO()
    canvas.save(buf, format="WEBP", quality=95)
    buf.seek(0)
    return buf.read()

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    text = (
        "🎨 <b>StickerX Bot</b>\n"
        "<i>حوّل أي صورة إلى ملصق تيليجرام احترافي!</i>\n"
        "───────────────────────\n\n"
        "⬇️ <b>أرسل أي صورة الآن للبدء في تحويلها إلى ملصق:</b>"
    )
    bot.send_message(message.chat.id, text, reply_markup=app_kb())

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
        bot.reply_to(message, "❌ أرسل صورة فقط (JPG, PNG, WEBP...)")
        return

    try:
        file_info = bot.get_file(file_id)
        raw = bot.download_file(file_info.file_path)
        _sessions[uid] = raw
        bot.reply_to(message, "🎨 <b>اختر لون خلفية الملصق:</b>", reply_markup=bg_kb())
    except Exception as e:
        bot.reply_to(message, f"❌ فشل الاستلام: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("bg:"))
def handle_bg(call):
    uid = call.from_user.id
    bg = call.data.split(":")[1]
    raw = _sessions.get(uid)

    if not raw:
        bot.answer_callback_query(call.id, "⚠️ انتهت الجلسة، أرسل الصورة من جديد.", show_alert=True)
        return

    wait = bot.edit_message_text("⏳ <b>جاري إنشاء الملصق...</b>\n<i>قد يستغرق بضع ثوانٍ</i>",
                                 call.message.chat.id, call.message.message_id)

    def convert():
        try:
            sticker_bytes = make_sticker(raw, remove_bg=(bg == "transparent"))
            buf = io.BytesIO(sticker_bytes)
            buf.name = "sticker.webp"

            bot.send_sticker(call.message.chat.id, buf)

            buf.seek(0)
            buf.name = "sticker.webp"
            bot.send_document(
                call.message.chat.id, buf,
                caption="✅ <b>ملصقك جاهز!</b>\nيمكنك إضافته لحزمة ملصقاتك.\n\n<b>بواسطة:</b> متجر تطبيقات Boda 🏪",
                reply_markup=app_kb()
            )
            bot.delete_message(call.message.chat.id, wait.message_id)
            del _sessions[uid]

        except Exception as e:
            log.error(f"Convert error: {e}")
            bot.edit_message_text(f"❌ <b>خطأ في التحويل</b>\n<code>{str(e)[:150]}</code>",
                call.message.chat.id, wait.message_id)

    threading.Thread(target=convert, daemon=True).start()

@bot.message_handler(func=lambda m: True)
def handle_other(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    bot.send_message(message.chat.id, "📸 <b>أرسل صورة فقط للبدء في إنشاء الملصق!</b>", reply_markup=app_kb())

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "stickerx")
