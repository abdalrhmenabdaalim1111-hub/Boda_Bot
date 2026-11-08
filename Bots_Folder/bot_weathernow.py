"""
bot_weathernow.py — WeatherNow | بوت الطقس الفوري
الاسم العربي: بوت الطقس
English Name: WeatherNow
Username: @WeatherNowXBot
الوصف: احصل على حالة الطقس الآن لأي مدينة في العالم مع درجة الحرارة والرطوبة وسرعة الريح.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[WeatherNow] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("weather")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "بوت الطقس"
# Open-Meteo + Geocoding API — مجاني 100% بدون key
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

POPULAR_CITIES = [
    ("🇸🇦 الرياض",    "Riyadh"),
    ("🇦🇪 دبي",        "Dubai"),
    ("🇪🇬 القاهرة",    "Cairo"),
    ("🇸🇦 جدة",        "Jeddah"),
    ("🇶🇦 الدوحة",     "Doha"),
    ("🇰🇼 الكويت",     "Kuwait City"),
]

def store_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def cities_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    btns = [InlineKeyboardButton(n, callback_data=f"city:{e}") for n, e in POPULAR_CITIES]
    kb.add(*btns)
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

def get_weather(city: str) -> dict | None:
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "ar"},
            timeout=8
        ).json()
        results = geo.get("results", [])
        if not results: return None
        r   = results[0]
        lat, lon = r["latitude"], r["longitude"]
        name     = r.get("name", city)
        country  = r.get("country", "")

        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,apparent_temperature",
                "wind_speed_unit": "kmh",
            },
            timeout=8
        ).json()
        cur = weather.get("current", {})
        return {
            "name": name, "country": country,
            "temp":      cur.get("temperature_2m", "?"),
            "feels":     cur.get("apparent_temperature", "?"),
            "humidity":  cur.get("relative_humidity_2m", "?"),
            "wind":      cur.get("wind_speed_10m", "?"),
            "code":      cur.get("weather_code", 0),
        }
    except Exception as e:
        log.error(f"Weather error: {e}")
        return None

def weather_code_emoji(code: int) -> str:
    if code == 0:       return "☀️ صافٍ تماماً"
    elif code <= 3:     return "⛅ غائم جزئياً"
    elif code <= 49:    return "🌫️ ضبابي"
    elif code <= 67:    return "🌧️ ممطر"
    elif code <= 77:    return "❄️ ثلج"
    elif code <= 82:    return "🌦️ أمطار متفرقة"
    elif code <= 99:    return "⛈️ عواصف رعدية"
    return "🌤️ متقلب"

def _format_weather(d: dict) -> str:
    cond = weather_code_emoji(d["code"])
    return (
        f"🌍 <b>{d['name']}</b> — {d['country']}\n"
        f"━━━━━━━━━━━━━━\n"
        f"{cond}\n"
        f"🌡️ <b>درجة الحرارة:</b> {d['temp']}°C\n"
        f"🤔 <b>تشعر كأنها:</b> {d['feels']}°C\n"
        f"💧 <b>الرطوبة:</b> {d['humidity']}%\n"
        f"💨 <b>سرعة الريح:</b> {d['wind']} كم/س\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>بواسطة متجر تطبيقات Boda 🏪</i>"
    )

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        f"☀️ <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "اعرف حالة الطقس لأي مدينة في العالم الآن!\n\n"
        "📍 <b>أرسل اسم المدينة</b> بالعربي أو الإنجليزي\n"
        "أو اختر من المدن الشهيرة:",
        reply_markup=cities_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("city:"))
def handle_city(call):
    city     = call.data.split(":", 1)[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)
    bot.edit_message_text(f"⏳ <i>جاري جلب طقس {city}...</i>", cid, mid)
    data = get_weather(city)
    kb   = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔄 تحديث", callback_data=f"city:{city}"),
        InlineKeyboardButton("🏠 رجوع",  callback_data="city:back"),
        InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL),
    )
    if data:
        bot.edit_message_text(_format_weather(data), cid, mid, reply_markup=kb)
    else:
        bot.edit_message_text("❌ لم أجد المدينة. تأكد من الاسم وأعد المحاولة.", cid, mid,
                              reply_markup=cities_kb())

@bot.callback_query_handler(func=lambda c: c.data == "city:back")
def handle_back(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"☀️ <b>{BOT_NAME}</b>\n\n📍 أرسل اسم مدينة أو اختر:",
        call.message.chat.id, call.message.message_id, reply_markup=cities_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    city = (msg.text or "").strip()
    if not city: cmd_start(msg); return
    wait = bot.reply_to(msg, f"⏳ <i>جاري جلب طقس {city}...</i>")
    data = get_weather(city)
    kb   = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔄 تحديث",     callback_data=f"city:{city}"),
        InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL),
    )
    if data:
        bot.edit_message_text(_format_weather(data), msg.chat.id, wait.message_id, reply_markup=kb)
    else:
        bot.edit_message_text(
            f"❌ <b>لم أجد مدينة باسم '{city}'</b>\n\n"
            "جرب كتابة الاسم بالإنجليزي أو تحقق من الهجاء.",
            msg.chat.id, wait.message_id, reply_markup=cities_kb())

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query"])
