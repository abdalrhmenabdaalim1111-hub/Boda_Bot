"""
bot_colorpick.py — ColorPick | محلّل ألوان الصور
الاسم العربي: محلل الألوان
English Name: ColorPick
Username: @ColorPickXBot
الوصف: أرسل أي صورة وسيستخرج البوت أبرز الألوان منها مع أكواد HEX وRGB جاهزة للاستخدام.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, io, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[ColorPick] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("colorpick")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "محلل الألوان"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

def store_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def rgb_to_name(r, g, b):
    """تقريب الألوان لأسماء عربية"""
    if r > 200 and g < 100 and b < 100:  return "أحمر ❤️"
    if r < 100 and g > 150 and b < 100:  return "أخضر 💚"
    if r < 100 and g < 100 and b > 150:  return "أزرق 💙"
    if r > 200 and g > 200 and b < 100:  return "أصفر 💛"
    if r > 200 and g < 100 and b > 150:  return "بنفسجي 💜"
    if r > 200 and g > 100 and b < 100:  return "برتقالي 🧡"
    if r < 50  and g < 50  and b < 50:   return "أسود ⬛"
    if r > 200 and g > 200 and b > 200:  return "أبيض ⬜"
    if r > 100 and g > 100 and b > 100:  return "رمادي 🩶"
    return "متنوع 🎨"

def extract_dominant_colors(raw: bytes, num_colors=6):
    from PIL import Image
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img = img.resize((150, 150))  # Reduce for speed
    pixels = list(img.getdata())

    # Simple quantization — group and count
    from collections import Counter
    def bucket(c): return tuple(x // 32 * 32 for x in c)
    counts = Counter(bucket(p) for p in pixels)
    top    = counts.most_common(num_colors * 3)

    # Deduplicate similar colors
    results = []
    for color, _ in top:
        r, g, b = color
        r += 16; g += 16; b += 16  # Midpoint of bucket
        r = min(255, r); g = min(255, g); b = min(255, b)
        # Check not too similar to existing
        too_close = any(abs(r-er)+abs(g-eg)+abs(b-eb) < 80 for er,eg,eb in results)
        if not too_close:
            results.append((r, g, b))
        if len(results) >= num_colors:
            break
    return results

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        f"🎨 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "أرسل أي صورة وسأستخرج لك أبرز الألوان منها\n"
        "مع كودها HEX وRGB!\n\n"
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

    wait = bot.reply_to(msg, "🎨 <i>جاري تحليل الألوان...</i>")
    try:
        finfo = bot.get_file(file_id)
        raw   = bot.download_file(finfo.file_path)
        colors = extract_dominant_colors(raw)

        if not colors:
            bot.edit_message_text("❌ لم أتمكن من تحليل الصورة.", msg.chat.id, wait.message_id)
            return

        lines = ["🎨 <b>الألوان الرئيسية في الصورة:</b>\n━━━━━━━━━━━━"]
        palettes = {
            "🟥": (200, 0, 0), "🟧": (255, 165, 0), "🟨": (255, 230, 0),
            "🟩": (0, 180, 0), "🟦": (0, 100, 200), "🟪": (150, 0, 200),
        }
        for i, (r, g, b) in enumerate(colors, 1):
            hex_code = f"#{r:02X}{g:02X}{b:02X}"
            name     = rgb_to_name(r, g, b)
            lines.append(f"{i}. {name}\n   <code>{hex_code}</code> | RGB({r},{g},{b})")

        lines += ["━━━━━━━━━━━━", "<i>بواسطة متجر تطبيقات Boda 🏪</i>"]

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
        bot.edit_message_text("\n".join(lines), msg.chat.id, wait.message_id, reply_markup=kb)

    except ImportError:
        bot.edit_message_text(
            "❌ مكتبة Pillow غير مثبتة.\n<code>pip install Pillow</code>",
            msg.chat.id, wait.message_id)
    except Exception as e:
        log.error(f"ColorPick error: {e}")
        bot.edit_message_text(f"❌ خطأ: {str(e)[:200]}", msg.chat.id, wait.message_id)

@bot.message_handler(func=lambda m: True)
def guide(msg):
    bot.reply_to(msg, "📸 <b>أرسل أي صورة</b> لتحليل ألوانها!", reply_markup=store_kb())

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query"])
