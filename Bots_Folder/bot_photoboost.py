"""
bot_photoboost.py — PhotoBoost | محسّن الصور الذكي
الاسم العربي: محسّن الصور
English Name: PhotoBoost
Username: @PhotoBoostXBot
الوصف: حسّن صورك تلقائياً — زيادة الحدة والإضاءة والتباين وتحويل الصيغ في ثواني.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, io, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[PhotoBoost] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("photoboost")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "محسّن الصور"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_images = {}  # uid → raw bytes

ENHANCEMENTS = {
    "sharpen":    ("🔍 تحسين الحدة",    "sharpen"),
    "brightness": ("☀️ زيادة إضاءة",   "brightness"),
    "contrast":   ("🎯 تحسين التباين",  "contrast"),
    "grayscale":  ("⬛ أبيض وأسود",    "grayscale"),
    "blur":       ("🌫️ ضبابي فني",     "blur"),
    "flip_h":     ("↔️ عكس أفقي",      "flip_h"),
    "flip_v":     ("↕️ عكس رأسي",      "flip_v"),
    "auto":       ("✨ تحسين تلقائي",   "auto"),
}

def effects_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    btns = [InlineKeyboardButton(label, callback_data=f"ph:{k}") for k, (label, _) in ENHANCEMENTS.items()]
    kb.add(*btns)
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def store_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def process_image(raw: bytes, effect: str) -> bytes:
    from PIL import Image, ImageEnhance, ImageFilter
    img = Image.open(io.BytesIO(raw)).convert("RGB")

    if effect == "sharpen":
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=3))
    elif effect == "brightness":
        img = ImageEnhance.Brightness(img).enhance(1.4)
    elif effect == "contrast":
        img = ImageEnhance.Contrast(img).enhance(1.5)
    elif effect == "grayscale":
        img = img.convert("L").convert("RGB")
    elif effect == "blur":
        img = img.filter(ImageFilter.GaussianBlur(radius=3))
    elif effect == "flip_h":
        from PIL import Image as PilImage
        img = img.transpose(PilImage.FLIP_LEFT_RIGHT)
    elif effect == "flip_v":
        from PIL import Image as PilImage
        img = img.transpose(PilImage.FLIP_TOP_BOTTOM)
    elif effect == "auto":
        img = ImageEnhance.Brightness(img).enhance(1.15)
        img = ImageEnhance.Contrast(img).enhance(1.25)
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        img = ImageEnhance.Color(img).enhance(1.2)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    buf.seek(0)
    return buf.read()

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        f"🖼️ <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "أرسل أي صورة وحسّنها بلمسة واحدة!\n\n"
        "📸 <b>أرسل الصورة الآن:</b>",
        reply_markup=store_kb())

@bot.message_handler(content_types=["photo", "document"])
def handle_image(msg):
    uid = msg.from_user.id
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image"):
        file_id = msg.document.file_id
    else:
        bot.reply_to(msg, "❌ أرسل صورة PNG أو JPG."); return
    try:
        finfo = bot.get_file(file_id)
        raw   = bot.download_file(finfo.file_path)
        user_images[uid] = raw
        bot.reply_to(msg,
            "✅ <b>صورتك جاهزة!</b>\n\n🎨 <b>اختر التأثير:</b>",
            reply_markup=effects_kb())
    except Exception as e:
        bot.reply_to(msg, f"❌ فشل تحميل الصورة: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ph:"))
def handle_effect(call):
    uid      = call.from_user.id
    effect   = call.data.split(":")[1]
    cid, mid = call.message.chat.id, call.message.message_id
    raw      = user_images.get(uid)
    bot.answer_callback_query(call.id)

    if not raw:
        bot.edit_message_text("⚠️ انتهت الجلسة، أرسل الصورة مجدداً.", cid, mid); return

    label = ENHANCEMENTS.get(effect, (effect, effect))[0]
    bot.edit_message_text(f"⏳ <i>جاري تطبيق {label}...</i>", cid, mid)

    try:
        result = process_image(raw, effect)
        buf    = io.BytesIO(result); buf.name = "enhanced.jpg"
        kb     = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🎨 تأثير آخر", callback_data="ph:back"),
            InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL),
        )
        bot.send_photo(cid, buf,
            caption=f"✅ <b>تم تطبيق: {label}</b>\n\n<i>بواسطة متجر تطبيقات Boda 🏪</i>",
            reply_markup=kb)
        bot.delete_message(cid, mid)
    except ImportError:
        bot.edit_message_text(
            "❌ مكتبة Pillow غير مثبتة.\n<code>pip install Pillow</code>",
            cid, mid)
    except Exception as e:
        log.error(f"PhotoBoost: {e}")
        bot.edit_message_text(f"❌ خطأ: {str(e)[:200]}", cid, mid, reply_markup=effects_kb())

@bot.callback_query_handler(func=lambda c: c.data == "ph:back")
def handle_back(call):
    uid      = call.from_user.id
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)
    if user_images.get(uid):
        bot.edit_message_text("🎨 <b>اختر التأثير:</b>", cid, mid, reply_markup=effects_kb())
    else:
        bot.edit_message_text("📸 أرسل الصورة أولاً.", cid, mid)

@bot.message_handler(func=lambda m: True)
def guide(msg):
    bot.reply_to(msg, "📸 <b>أرسل أي صورة</b> لتحسينها!", reply_markup=store_kb())

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "photoboost", allowed_updates=["message", "callback_query"])
