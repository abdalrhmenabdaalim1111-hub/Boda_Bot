import sys, logging
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[Currency] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("currency")

TOKEN = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

# State dictionary to map user_id -> state data (amount, from_cur, to_cur)
user_states = {}

POPULAR_CURRENCIES = [
    "USD", "EUR", "GBP", "EGP", "SAR", "AED", "KWD", "QAR", "OMR", "BHD", "JOD", "TRY", "JPY"
]

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def cur_kb(action_prefix):
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(c, callback_data=f"{action_prefix}_{c}") for c in POPULAR_CURRENCIES]
    kb.add(*buttons)
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        "👋 <b>أهلاً بك في محول العملات!</b>\n\n"
        "💱 <b>تطبيق يعمل مباشرة داخل الشات!</b>\n\n"
        "يرجى إرسال <b>المبلغ</b> الذي تريد تحويله (كأرقام فقط):",
        reply_markup=app_kb())
    user_states[msg.chat.id] = {"amount": 0, "from": "", "to": ""}

@bot.message_handler(func=lambda msg: msg.text and msg.text.replace(".", "", 1).isdigit())
def handle_amount(msg):
    uid = msg.chat.id
    if uid not in user_states:
        user_states[uid] = {}
    
    amount = float(msg.text)
    user_states[uid]["amount"] = amount
    
    bot.send_message(uid,
        f"💵 المبلغ: <b>{amount}</b>\n\n"
        "🔽 من فضلك، <b>اختر العملة المراد التحويل (مِنها):</b>",
        reply_markup=cur_kb("from"))

@bot.callback_query_handler(func=lambda call: call.data.startswith("from_"))
def handle_from_currency(call):
    uid = call.message.chat.id
    cur = call.data.split("_")[1]
    
    if uid not in user_states:
        user_states[uid] = {}
    user_states[uid]["from"] = cur
    
    bot.edit_message_text(
        f"💵 العملة الأساسية: <b>{cur}</b>\n\n"
        "🔼 من فضلك، <b>اختر العملة المراد التحويل (إليها):</b>",
        chat_id=uid, message_id=call.message.message_id,
        reply_markup=cur_kb("to")
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("to_"))
def handle_to_currency(call):
    uid = call.message.chat.id
    to_cur = call.data.split("_")[1]
    
    if uid not in user_states or "amount" not in user_states[uid] or "from" not in user_states[uid]:
        bot.send_message(uid, "⚠️ حدث خطأ، يرجى إرسال المبلغ من البداية.")
        return
        
    user_states[uid]["to"] = to_cur
    amount = user_states[uid]["amount"]
    from_cur = user_states[uid]["from"]
    
    bot.edit_message_text("⏳ <i>جاري جلب أحدث أسعار الصرف...</i>", chat_id=uid, message_id=call.message.message_id)
    
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        rates = res.get("rates", {})
        
        if from_cur in rates and to_cur in rates:
            amountInUSD = amount / rates[from_cur]
            finalResult = amountInUSD * rates[to_cur]
            rate = (1 / rates[from_cur]) * rates[to_cur]
            
            result_text = (
                f"💱 <b>نتيجة التحويل:</b>\n\n"
                f"💵 المبلغ: <b>{amount:,.2f} {from_cur}</b>\n"
                f"💰 النتيجة: <b>{finalResult:,.2f} {to_cur}</b>\n\n"
                f"📊 <i>سعر الصرف: 1 {from_cur} = {rate:.4f} {to_cur}</i>\n\n"
                f"<b>بواسطة:</b> متجر تطبيقات Boda 🏪"
            )
            bot.edit_message_text(result_text, chat_id=uid, message_id=call.message.message_id, reply_markup=app_kb())
        else:
            bot.edit_message_text("❌ حدث خطأ غير معروف في قراءة السعر.", chat_id=uid, message_id=call.message.message_id)
            
    except Exception as e:
        log.error(f"Error fetching rates: {e}")
        bot.edit_message_text("❌ فشل الاتصال بخادم أسعار الصرف.", chat_id=uid, message_id=call.message.message_id)
        
    # Clear state
    user_states.pop(uid, None)

@bot.message_handler(func=lambda msg: True)
def unknown_text(msg):
    bot.reply_to(msg, "⚠️ يرجى إرسال أرقام فقط (المبلغ المُراد تحويله) لكي أبدأ.")

if __name__ == "__main__":
    log.info("🚀 محول العملات الذكي — CurrencyBot starting...")
    try:
        me = bot.get_me()
        log.info(f"Authenticated: @{me.username}")
    except Exception as e:
        log.error(f"Auth failed: {e}"); sys.exit(1)
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(
        skip_pending=True, timeout=10, long_polling_timeout=20,
        allowed_updates=["message", "callback_query"])
