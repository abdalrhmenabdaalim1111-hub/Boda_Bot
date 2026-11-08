"""
bot_cryptorate.py — CryptoRate | أسعار العملات الرقمية
الاسم العربي: محوّل العملة الرقمية
English Name: CryptoRate
Username: @CryptoRateXBot
الوصف: تابع أسعار البيتكوين والإيثيريوم وأشهر العملات الرقمية لحظياً بالدولار والريال.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[CryptoRate] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("crypto")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "محوّل العملة الرقمية"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

COINS = {
    "bitcoin":   ("₿ Bitcoin",    "BTC", "🟡"),
    "ethereum":  ("Ξ Ethereum",   "ETH", "🔵"),
    "binancecoin": ("BNB",        "BNB", "🟠"),
    "ripple":    ("✦ XRP",        "XRP", "🩵"),
    "dogecoin":  ("Ð Dogecoin",   "DOGE","🐕"),
    "solana":    ("◎ Solana",     "SOL", "🟣"),
    "cardano":   ("₳ Cardano",    "ADA", "🔮"),
    "tether":    ("₮ Tether",     "USDT","🟢"),
}

def coins_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    btns = [InlineKeyboardButton(f"{e} {s}", callback_data=f"coin:{k}")
            for k, (n, s, e) in COINS.items()]
    kb.add(*btns)
    kb.add(InlineKeyboardButton("📊 جميع الأسعار", callback_data="coin:all"))
    kb.add(InlineKeyboardButton("🏪 متجر Boda",   url=STORE_URL))
    return kb

def get_prices(coins: list) -> dict:
    try:
        ids = ",".join(coins)
        r   = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd,sar", "include_24hr_change": "true"},
            timeout=10
        ).json()
        return r
    except Exception as e:
        log.error(f"Crypto API: {e}")
        return {}

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        f"💰 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "تابع أسعار العملات الرقمية لحظياً!\n\n"
        "👇 <b>اختر عملة:</b>",
        reply_markup=coins_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("coin:"))
def handle_coin(call):
    coin_id  = call.data.split(":", 1)[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)
    bot.edit_message_text("⏳ <i>جاري جلب الأسعار...</i>", cid, mid)

    kb = InlineKeyboardMarkup(row_width=1)

    if coin_id == "all":
        prices = get_prices(list(COINS.keys()))
        lines  = ["📊 <b>جميع الأسعار الآن:</b>\n━━━━━━━━━━━━━━"]
        for cid_k, (name, sym, emoji) in COINS.items():
            d = prices.get(cid_k, {})
            usd = d.get("usd", "?")
            change = d.get("usd_24h_change", 0)
            chg_txt = f"+{change:.2f}%" if change and change > 0 else f"{change:.2f}%" if change else ""
            arrow   = "📈" if change and change > 0 else ("📉" if change and change < 0 else "")
            lines.append(f"{emoji} <b>{sym}</b>: ${usd:,.4f} {arrow} <i>{chg_txt}</i>")
        kb.add(
            InlineKeyboardButton("🔄 تحديث",     callback_data="coin:all"),
            InlineKeyboardButton("🏠 رجوع",      callback_data="coin:back"),
            InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL),
        )
        bot.edit_message_text("\n".join(lines), cid, mid, reply_markup=kb)

    elif coin_id == "back":
        bot.edit_message_text(
            f"💰 <b>{BOT_NAME}</b>\n\n👇 اختر عملة:", cid, mid, reply_markup=coins_kb())

    elif coin_id in COINS:
        prices = get_prices([coin_id])
        d      = prices.get(coin_id, {})
        name, sym, emoji = COINS[coin_id]
        usd    = d.get("usd", "?")
        sar    = d.get("sar", "?")
        change = d.get("usd_24h_change", 0)
        arrow  = "📈" if change and change > 0 else ("📉" if change and change < 0 else "➡️")
        chg_cl = "🟢" if change and change > 0 else ("🔴" if change and change < 0 else "⚪")

        kb.add(
            InlineKeyboardButton("🔄 تحديث",      callback_data=f"coin:{coin_id}"),
            InlineKeyboardButton("📊 جميع الأسعار", callback_data="coin:all"),
            InlineKeyboardButton("🔙 رجوع",        callback_data="coin:back"),
            InlineKeyboardButton("🏪 متجر Boda",   url=STORE_URL),
        )
        bot.edit_message_text(
            f"{emoji} <b>{name} ({sym})</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"💵 <b>السعر بالدولار:</b> ${usd:,.4f}\n"
            f"🇸🇦 <b>السعر بالريال:</b> ﷼{sar:,.2f}\n"
            f"{chg_cl} <b>التغيير 24س:</b> {change:.2f}% {arrow}\n"
            f"━━━━━━━━━━━━━━\n"
            f"<i>بواسطة متجر تطبيقات Boda 🏪</i>",
            cid, mid, reply_markup=kb)

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    cmd_start(msg)

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query"])
