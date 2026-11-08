"""
bot_termgloss.py — TermGloss | قاموس المصطلحات التقنية
الاسم العربي: قاموس المصطلحات
English Name: TermGloss
Username: @TermGlossXBot
الوصف: يشرح مصطلحات التقنية والبرمجة والتسويق والأعمال بالعربي بأسلوب بسيط وسهل.

TOKEN = "ضع_التوكن_هنا"
"""
import sys, logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[TermGloss] %(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("termgloss")

TOKEN     = "ضع_التوكن_هنا"
STORE_URL = "https://t.me/BodaStoreeBot"
BOT_NAME  = "قاموس المصطلحات"
bot       = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

GLOSSARY = {
    # برمجة
    "api": ("API", "واجهة برمجة التطبيقات", "مجموعة من القواعد التي تسمح لتطبيقات مختلفة بالتواصل مع بعضها. مثل: استخدام API الطقس لعرض درجة الحرارة في تطبيقك.", "برمجة"),
    "sdk": ("SDK", "مجموعة أدوات التطوير", "حزمة تحتوي على أدوات ومكتبات تساعد المبرمجين في بناء تطبيقات لمنصة معينة.", "برمجة"),
    "ci/cd": ("CI/CD", "التكامل والتسليم المستمر", "ممارسة أتمتة بناء واختبار ونشر الكود البرمجي بشكل تلقائي ومستمر.", "برمجة"),
    "debugger": ("Debugger", "مصحح الأخطاء", "أداة تساعد المبرمج على تتبع الأخطاء في الكود وإصلاحها خطوة بخطوة.", "برمجة"),
    "framework": ("Framework", "إطار العمل", "هيكل جاهز يوفر بنية أساسية لبناء التطبيقات، مثل Django لـ Python أو React لـ JavaScript.", "برمجة"),
    "git": ("Git", "نظام التحكم في الإصدارات", "نظام يصحب التغييرات في الكود ويسمح لفرق العمل بالتعاون بلا مشاكل.", "برمجة"),
    "saas": ("SaaS", "البرمجيات كخدمة", "نموذج أعمال حيث يُقدَّم البرنامج عبر الإنترنت بدلاً من تثبيته محلياً. مثل: Google Workspace.", "تقنية"),
    "cloud": ("Cloud", "الحوسبة السحابية", "تخزين البيانات وتشغيل التطبيقات عبر الإنترنت على خوادم بعيدة بدلاً من جهازك.", "تقنية"),
    "vpn": ("VPN", "الشبكة الخاصة الافتراضية", "تقنية تشفير الاتصال بالإنترنت وإخفاء عنوان IP لتحقيق الخصوصية.", "أمان"),
    "ssl": ("SSL/TLS", "طبقة المقابس الآمنة", "بروتوكول تشفير يُأمّن الاتصال بين المتصفح والموقع. المواقع الآمنة تبدأ بـ https://", "أمان"),
    "seo": ("SEO", "تحسين محركات البحث", "مجموعة تقنيات تجعل موقعك يظهر في أعلى نتائج جوجل بشكل طبيعي بدون دفع.", "تسويق"),
    "kpi": ("KPI", "مؤشرات الأداء الرئيسية", "مقاييس تستخدمها الشركات لقياس مدى نجاحها في تحقيق أهدافها.", "أعمال"),
    "roi": ("ROI", "العائد على الاستثمار", "نسبة الربح مقارنةً بالتكلفة. ROI 100% = ربحت ضعف ما أنفقت.", "أعمال"),
    "mvp": ("MVP", "الحد الأدنى من المنتج القابل للتطبيق", "نسخة أولية من المنتج بأقل ميزات ممكنة لاختباره في السوق بسرعة وتقليل المخاطر.", "أعمال"),
    "ux": ("UX", "تجربة المستخدم", "علم تصميم المنتجات بحيث تكون سهلة وممتعة للاستخدام من وجهة نظر المستخدم.", "تصميم"),
    "ui": ("UI", "واجهة المستخدم", "كل ما يراه المستخدم ويتفاعل معه في التطبيق أو الموقع — الأزرار والألوان والنصوص.", "تصميم"),
    "blockchain": ("Blockchain", "سلسلة الكتل", "قاعدة بيانات موزعة لا يمكن تعديلها أو حذفها — تُستخدم في العملات الرقمية.", "تقنية"),
    "ai": ("AI", "الذكاء الاصطناعي", "قدرة الآلات على محاكاة التفكير البشري — مثل التعرف على الصور والترجمة.", "تقنية"),
    "machine learning": ("Machine Learning", "تعلم الآلة", "برمجة الآلات على التعلم من البيانات وتحسين أدائها دون برمجة صريحة.", "تقنية"),
    "scrum": ("Scrum", "سكرم", "منهجية تطوير رشيقة تعتمد على تقسيم العمل لدورات قصيرة تُسمى Sprint مدتها 2-4 أسابيع.", "إدارة"),
}

def cats_kb():
    cats = list(set(v[3] for v in GLOSSARY.values()))
    kb   = InlineKeyboardMarkup(row_width=3)
    btns = [InlineKeyboardButton(c, callback_data=f"tg:cat:{c}") for c in cats]
    kb.add(*btns)
    kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
    return kb

@bot.message_handler(commands=["start", "help"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        f"📚 <b>أهلاً في {BOT_NAME}!</b>\n\n"
        "ابحث عن أي مصطلح تقني وسأشرحه لك بالعربي!\n\n"
        "<b>مثال:</b> أرسل <code>API</code> أو <code>SEO</code> أو <code>AI</code>\n\n"
        "👇 أو تصفح حسب الفئة:",
        reply_markup=cats_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("tg:"))
def handle_tg(call):
    parts    = call.data.split(":")
    cid, mid = call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if parts[1] == "cat":
        cat   = parts[2]
        terms = [(k, v) for k, v in GLOSSARY.items() if v[3] == cat]
        kb    = InlineKeyboardMarkup(row_width=1)
        for k, (en, ar, _, _cat) in terms:
            kb.add(InlineKeyboardButton(f"{en} — {ar}", callback_data=f"tg:term:{k}"))
        kb.add(InlineKeyboardButton("🔙 رجوع", callback_data="tg:home"))
        bot.edit_message_text(f"📂 <b>مصطلحات {cat}:</b>", cid, mid, reply_markup=kb)

    elif parts[1] == "term":
        key  = parts[2]
        data = GLOSSARY.get(key)
        if data:
            en, ar, desc, cat = data
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(
                InlineKeyboardButton("🔙 رجوع للفئة", callback_data=f"tg:cat:{cat}"),
                InlineKeyboardButton("🏪 متجر Boda",  url=STORE_URL),
            )
            bot.edit_message_text(
                f"📌 <b>{en}</b>\n"
                f"🇸🇦 <b>{ar}</b>\n"
                f"🏷️ <i>#{cat}</i>\n"
                f"━━━━━━━━━━━━\n"
                f"📖 {desc}",
                cid, mid, reply_markup=kb)

    elif parts[1] == "home":
        bot.edit_message_text(
            f"📚 <b>{BOT_NAME}</b>\n\nأرسل مصطلحاً أو تصفح الفئات:",
            cid, mid, reply_markup=cats_kb())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    query = (msg.text or "").strip().lower()
    if not query: cmd_start(msg); return

    # Search
    found = []
    for k, (en, ar, desc, cat) in GLOSSARY.items():
        if query in k or query in en.lower() or query in ar:
            found.append((k, en, ar, desc, cat))

    if not found:
        bot.reply_to(msg,
            f"🔍 لم أجد مصطلح «{msg.text}»\n\n"
            "جرب البحث بالإنجليزي أو تصفح الفئات:",
            reply_markup=cats_kb())
        return

    for k, en, ar, desc, cat in found[:3]:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("🏪 متجر Boda", url=STORE_URL))
        bot.reply_to(msg,
            f"📌 <b>{en}</b>\n"
            f"🇸🇦 <b>{ar}</b>\n"
            f"🏷️ <i>#{cat}</i>\n"
            f"━━━━━━━━━━━━\n"
            f"📖 {desc}",
            reply_markup=kb)

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "termgloss", allowed_updates=["message", "callback_query"])
