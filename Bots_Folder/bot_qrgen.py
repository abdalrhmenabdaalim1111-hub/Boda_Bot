"""
bot_qrgen.py — QRGen | صانع QR Code الاحترافي
@QRGenProBot
"""
import time
import sys, io, logging
import telebot
from utils import is_subscribed, send_subscription_prompt
from bot_base import get_token

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[QRGen] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("qrgen")

TOKEN = get_token("BOT_QRGEN_TOKEN")
STORE_URL = "https://t.me/BodaStoreBot"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_states = {} # chat_id -> text to encode

COLORS = {
    "black": ("أسود ⬛", "#000000"),
    "blue": ("أزرق 🟦", "#0000FF"),
    "red": ("أحمر 🟥", "#FF0000"),
    "green": ("أخضر 🟩", "#008000"),
    "purple": ("بنفسجي 🟪", "#800080")
}

def app_kb():
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def color_kb():
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(name, callback_data=f"qrcolor:{code}") for code, (name, hex_val) in COLORS.items()]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def make_qr(text: str, color: str = "#000000") -> bytes:
    import qrcode
    try:
        r = int(color[1:3], 16); g = int(color[3:5], 16); b = int(color[5:7], 16)
    except: r = g = b = 0
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=12, border=4)
    qr.add_data(text); qr.make(fit=True)
    img = qr.make_image(fill_color=(r, g, b), back_color="white")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    return buf.read()

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    if not is_subscribed(bot, msg.from_user.id):
        send_subscription_prompt(bot, msg.chat.id)
        return
    bot.send_message(msg.chat.id,
        "👋 <b>أهلاً في QRGen!</b>\n\n"
        "حوّل أي نص أو رابط أو معلومة\n"
        "إلى QR Code احترافي!\n\n"
        "⬇️ <b>أرسل أي نص أو رابط الآن:</b>",
        reply_markup=app_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    if not is_subscribed(bot, message.from_user.id):
        send_subscription_prompt(bot, message.chat.id)
        return
    content = message.text
    if not content: return
    user_states[message.chat.id] = content
    bot.send_message(message.chat.id, "🎨 <b>اختر لون الـ QR Code:</b>", reply_markup=color_kb())

@bot.callback_query_handler(func=lambda call: call.data.startswith("qrcolor:"))
def handle_color_selection(call):
    color_code = call.data.split(":")[1]
    content = user_states.get(call.message.chat.id)
    if not content:
        bot.answer_callback_query(call.id, "❌ انتهت الجلسة، أرسل الرابط مجدداً.", show_alert=True)
        return
    
    hex_color = COLORS.get(color_code, ("أسود", "#000000"))[1]
    color_name = COLORS.get(color_code, ("أسود", "#000000"))[0]
    
    bot.edit_message_text(f"⏳ <b>جاري إنشاء QR Code بلون {color_name}...</b>",
                          call.message.chat.id, call.message.message_id)
    try:
        img_bytes = make_qr(content, hex_color)
        buf = io.BytesIO(img_bytes); buf.name = "qrcode.png"
        caption = (
            f"✅ <b>QR Code جاهز!</b> ({color_name})\n"
            f"<code>{content[:80]}{'...' if len(content)>80 else ''}</code>\n\n"
            f"<b>بواسطة:</b> متجر تطبيقات Boda 🏪"
        )
        bot.send_photo(call.message.chat.id, buf, caption=caption, reply_markup=app_kb())
        bot.delete_message(call.message.chat.id, call.message.message_id)
        user_states.pop(call.message.chat.id, None)
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {e}", call.message.chat.id, call.message.message_id)

if __name__ == "__main__":
    log.info("🚀 QRGen starting (@QRGenProBot)")
    bot.delete_webhook(drop_pending_updates=True)
    time.sleep(2)  # Wait for Telegram to release previous session
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20)
