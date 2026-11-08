"""
bot_luckybox.py — LuckyBox | صندوق الحظ اليومي
الاسم العربي: مربّع الحظ
English Name: LuckyBox
Username: @LuckyBoxXBot
الوصف: افتح صندوق مفاجآتك اليومي! اقتباسات ملهمة، نصائح يومية، وأرقام الحظ كل يوم.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging, random
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[LuckyBox] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("luckybox")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "مربّع الحظ"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

QUOTES = [
    "النجاح ليس نهائياً، والفشل ليس قاتلاً — ما يهم هو الشجاعة على الاستمرار. ● وينستون تشرشل",
    "الطريق الوحيد للقيام بعمل رائع هو أن تحب ما تفعله. ● ستيف جوبز",
    "لا تنتظر الفرصة المثالية، بل اصنع فرصتك. ● جورج برنارد شو",
    "كل يوم هو فرصة لتكون أفضل مما كنت عليه أمس.",
    "الشخص الذي يتحرك بثقة نحو أحلامه سيلتقي بنجاح لم يتوقعه. ● هنري ثورو",
    "السعادة لا تُشترى بالمال، لكن المال يمنحك وقتاً لتبحث عنها.",
    "العظمة ليست في من تكون، بل في ما تفعل من أجل الآخرين.",
    "ابدأ أينما أنت، استخدم ما لديك، افعل ما تستطيع. ● آرثر آش",
    "الحياة ٪10 مما يحدث لك و٪90 كيف تتعامل مع ما يحدث. ● تشارلز سويندول",
    "لا تقارن رحلتك برحلة غيرك — أنت لا تعرف قصتهم الكاملة.",
]

TIPS = [
    "💧 اشرب 8 أكواب ماء يومياً لتحسين تركيزك وصحتك.",
    "🧘 خصص 10 دقائق يومياً للتأمل أو التنفس العميق.",
    "📵 ابتعد عن الموبايل ساعة قبل النوم لنوم أعمق.",
    "🏃 30 دقيقة مشي يومياً تعادل ساعة في الجيم.",
    "📚 اقرأ 20 صفحة يومياً = كتاب كامل كل شهر!",
    "🙏 اشكر 3 أشياء كل يوم لتحسين صحتك النفسية.",
    "🌅 استيقظ مبكراً — الساعة الذهبية بعد الفجر هي وقت الإبداع.",
    "🥗 أضف خضراوات لكل وجبة رئيسية لتعزيز المناعة.",
    "💤 8 ساعات نوم يومياً تزيد كفاءةً وإنتاجيةً.",
    "😊 الابتسامة تُفرز هرمون السعادة — ابتسم حتى لنفسك!",
]

BOXES = ["🎁", "🎀", "📦", "🎊", "🎉", "✨", "💫", "🌟"]

def home_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎁 افتح الصندوق",   callback_data="lb:open"),
        InlineKeyboardButton("💡 نصيحة اليوم",    callback_data="lb:tip"),
        InlineKeyboardButton("💬 اقتباس ملهم",    callback_data="lb:quote"),
        InlineKeyboardButton("🍀 أرقام الحظ",      callback_data="lb:lucky"),
        InlineKeyboardButton("🏪 متجر Boda",       url=STORE_URL),
    )
    return kb

def again_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔄 مرة أخرى",       callback_data="lb:open"),
        InlineKeyboardButton("🏠 القائمة",         callback_data="lb:home"),
        InlineKeyboardButton("🏪 متجر Boda",       url=STORE_URL),
    )
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    box = random.choice(BOXES)
    bot.send_message(msg.chat.id,
        f"{box} <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "افتح صندوق مفاجآتك اليومي!\n"
        "اقتباسات ملهمة، نصائح ذهبية، وأرقام الحظ.\n\n"
        "👇 <b>ماذا تريد اليوم؟</b>",
        reply_markup=home_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("lb:"))
def handle_lb(call):
    act      = call.data.split(":")[1]
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if act == "home":
        box = random.choice(BOXES)
        bot.edit_message_text(
            f"{box} <b>{BOT_NAME}</b>\n\n👇 ماذا تريد اليوم؟",
            cid, mid, reply_markup=home_kb())

    elif act == "open":
        # Random box content
        choice = random.choice(["quote", "tip", "lucky", "mixed"])
        if choice == "quote":
            q = random.choice(QUOTES)
            text = f"🎁 <b>صندوقك يحتوي على اقتباس ملهم!</b>\n\n💬 <i>«{q}»</i>"
        elif choice == "tip":
            t = random.choice(TIPS)
            text = f"🎁 <b>صندوقك يحتوي على نصيحة ذهبية!</b>\n\n{t}"
        elif choice == "lucky":
            nums = sorted(random.sample(range(1, 100), 6))
            text = f"🎁 <b>صندوقك يحتوي على أرقام حظك!</b>\n\n🍀 <b>{' · '.join(map(str, nums))}</b>"
        else:
            q    = random.choice(QUOTES)
            t    = random.choice(TIPS)
            nums = sorted(random.sample(range(1, 50), 3))
            text = (f"🎁 <b>صندوق مزدوج المفاجآت!</b>\n\n"
                    f"💬 <i>«{q}»</i>\n\n{t}\n\n"
                    f"🍀 أرقام حظك: <b>{' · '.join(map(str, nums))}</b>")
        bot.edit_message_text(text, cid, mid, reply_markup=again_kb())

    elif act == "tip":
        t = random.choice(TIPS)
        bot.edit_message_text(
            f"💡 <b>نصيحة اليوم:</b>\n\n{t}", cid, mid, reply_markup=again_kb())

    elif act == "quote":
        q = random.choice(QUOTES)
        bot.edit_message_text(
            f"💬 <b>اقتباس ملهم:</b>\n\n<i>«{q}»</i>", cid, mid, reply_markup=again_kb())

    elif act == "lucky":
        nums = sorted(random.sample(range(1, 100), 6))
        day  = datetime.now().strftime("%A %d/%m")
        bot.edit_message_text(
            f"🍀 <b>أرقام حظك ليوم {day}:</b>\n\n"
            f"<b>{'  |  '.join(map(str, nums))}</b>\n\n"
            f"<i>✨ اليوم يوم توقيع العقود والمبادرات الجديدة!</i>",
            cid, mid, reply_markup=again_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    cmd_start(msg)

if __name__ == "__main__":
    log.info(f"🚀 {BOT_NAME} starting...")
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=20,
                         allowed_updates=["message", "callback_query"])
