"""
bot_cashier.py — CashierCalc | حاسبة الكاشير الذكية
الاسم العربي: حاسبة الكاشير
English Name: CashierCalc
Username: @CashierCalcBot
الوصف: آلة حاسبة ذكية متكاملة للحسابات اليومية — جمع، طرح، ضرب، قسمة، فاتورة، خصم، ونسبة مئوية.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot_base import get_token

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[CashierCalc] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("cashier")

TOKEN = get_token("BOT_CASHIER_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "حاسبة الكاشير"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

user_sessions = {}  # uid → {"items": [], "mode": ""}

def store_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪 متجر تطبيقات Boda", url=STORE_URL))
    return kb

def main_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🧮 حاسبة بسيطة",   callback_data="calc:simple"),
        InlineKeyboardButton("🧾 فاتورة",         callback_data="calc:bill"),
        InlineKeyboardButton("💸 خصم %",          callback_data="calc:discount"),
        InlineKeyboardButton("📊 نسبة مئوية",     callback_data="calc:percent"),
        InlineKeyboardButton("🏪 متجر Boda",      url=STORE_URL),
    )
    return kb

def bill_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ احسب الإجمالي",  callback_data="bill:total"),
        InlineKeyboardButton("🗑 مسح الفاتورة",   callback_data="bill:clear"),
        InlineKeyboardButton("🔙 رجوع",            callback_data="calc:back"),
    )
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    user_sessions[msg.from_user.id] = {"items": [], "mode": ""}
    bot.send_message(msg.chat.id,
        f"👋 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "🧮 <b>كل حسابات الكاشير في بوت واحد:</b>\n"
        "• حاسبة بسيطة بعمليات متعددة\n"
        "• فاتورة تراكمية لعدة أصناف\n"
        "• حساب الخصم والسعر النهائي\n"
        "• حساب النسب المئوية\n\n"
        "👇 <b>اختر ما تريده:</b>",
        reply_markup=main_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("calc:"))
def handle_calc(call):
    uid  = call.from_user.id
    act  = call.data.split(":")[1]
    cid  = call.message.chat.id
    mid  = call.message.message_id
    if uid not in user_sessions:
        user_sessions[uid] = {"items": [], "mode": ""}

    if act == "simple":
        user_sessions[uid]["mode"] = "simple"
        bot.edit_message_text(
            "🧮 <b>الحاسبة البسيطة</b>\n\n"
            "أرسل العملية الحسابية مباشرة:\n"
            "<code>مثال: 500 + 250 * 2 - 100</code>\n"
            "<code>أو: 1500 / 3</code>\n\n"
            "✏️ <i>أرسل العملية الآن:</i>",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 رجوع", callback_data="calc:back")))

    elif act == "bill":
        user_sessions[uid]["mode"] = "bill"
        items = user_sessions[uid].get("items", [])
        text = _bill_text(items)
        bot.edit_message_text(text, cid, mid, reply_markup=bill_kb())

    elif act == "discount":
        user_sessions[uid]["mode"] = "discount"
        bot.edit_message_text(
            "💸 <b>حساب الخصم</b>\n\n"
            "أرسل: <code>السعر الخصم%</code>\n"
            "<b>مثال:</b> <code>500 20</code>\n"
            "يعني: سعر 500 بخصم 20%",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 رجوع", callback_data="calc:back")))

    elif act == "percent":
        user_sessions[uid]["mode"] = "percent"
        bot.edit_message_text(
            "📊 <b>حساب النسبة المئوية</b>\n\n"
            "أرسل: <code>الرقم النسبة%</code>\n"
            "<b>مثال:</b> <code>1200 15</code>\n"
            "يعني: ما هو 15% من 1200؟",
            cid, mid, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 رجوع", callback_data="calc:back")))

    elif act == "back":
        user_sessions[uid]["mode"] = ""
        bot.edit_message_text(
            f"🏠 <b>القائمة الرئيسية — {BOT_NAME}</b>\n\n👇 اختر ما تريده:",
            cid, mid, reply_markup=main_kb())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bill:"))
def handle_bill(call):
    uid  = call.from_user.id
    act  = call.data.split(":")[1]
    cid  = call.message.chat.id
    mid  = call.message.message_id
    if uid not in user_sessions:
        user_sessions[uid] = {"items": [], "mode": "bill"}

    if act == "total":
        items = user_sessions[uid].get("items", [])
        if not items:
            bot.answer_callback_query(call.id, "⚠️ الفاتورة فارغة! أضف أصناف أولاً.", show_alert=True)
            return
        total = sum(p for _, p in items)
        text = _bill_text(items) + f"\n\n━━━━━━━━━━━━━━\n💰 <b>الإجمالي: {total:,.2f}</b>"
        bot.edit_message_text(text, cid, mid, reply_markup=bill_kb())

    elif act == "clear":
        user_sessions[uid]["items"] = []
        bot.edit_message_text(_bill_text([]), cid, mid, reply_markup=bill_kb())
    bot.answer_callback_query(call.id)

def _bill_text(items):
    header = "🧾 <b>الفاتورة الحالية:</b>\n━━━━━━━━━━━━━━\n"
    if not items:
        return header + "<i>لا توجد أصناف — أرسل: الاسم السعر\nمثال: كوكا كولا 5</i>"
    rows = "".join(f"{i+1}. {n}  →  {p:,.2f}\n" for i, (n, p) in enumerate(items))
    return header + rows

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    uid  = msg.from_user.id
    text = (msg.text or "").strip()
    if uid not in user_sessions:
        user_sessions[uid] = {"items": [], "mode": ""}
        cmd_start(msg); return

    mode = user_sessions[uid].get("mode", "")

    try:
        if mode == "simple":
            # safe eval — numbers and operators only
            clean = "".join(c for c in text if c in "0123456789+-*/(). ")
            result = eval(clean)
            bot.reply_to(msg, f"🧮 <b>النتيجة:</b>\n<code>{text}</code>\n= <b>{result:,.4f}</b>", reply_markup=main_kb())

        elif mode == "bill":
            parts = text.rsplit(" ", 1)
            if len(parts) == 2:
                name  = parts[0].strip()
                price = float(parts[1].replace(",", ""))
                user_sessions[uid]["items"].append((name, price))
                items = user_sessions[uid]["items"]
                bot.reply_to(msg, _bill_text(items), reply_markup=bill_kb())
            else:
                bot.reply_to(msg, "⚠️ الصيغة: <code>اسم الصنف السعر</code>\n<b>مثال:</b> <code>برجر 25</code>")

        elif mode == "discount":
            parts = text.split()
            price, disc = float(parts[0]), float(parts[1])
            saved  = price * disc / 100
            final  = price - saved
            bot.reply_to(msg,
                f"💸 <b>نتيجة الخصم:</b>\n"
                f"السعر الأصلي: {price:,.2f}\n"
                f"الخصم {disc}%: -{saved:,.2f}\n"
                f"━━━━━━━━\n💰 <b>السعر النهائي: {final:,.2f}</b>",
                reply_markup=main_kb())

        elif mode == "percent":
            parts = text.split()
            num, pct = float(parts[0]), float(parts[1])
            result = num * pct / 100
            bot.reply_to(msg,
                f"📊 <b>نتيجة النسبة:</b>\n"
                f"{pct}% من {num:,.2f}\n"
                f"= <b>{result:,.4f}</b>",
                reply_markup=main_kb())

        else:
            # Try generic math
            try:
                clean = "".join(c for c in text if c in "0123456789+-*/(). ")
                result = eval(clean)
                bot.reply_to(msg, f"🧮 <b>النتيجة:</b> <b>{result:,.4f}</b>", reply_markup=main_kb())
            except:
                cmd_start(msg)
    except Exception as e:
        bot.reply_to(msg, f"❌ خطأ في الإدخال.\n<i>{e}</i>\n\nجرب مثلاً: <code>500 + 250</code>")

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "cashier", allowed_updates=["message", "callback_query"])
