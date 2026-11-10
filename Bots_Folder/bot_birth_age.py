"""
bot_birth_age.py — BirthAge | حاسبة العمر المتطورة
@BirthAgeCalcBot
"""
import time, os, sys, re
from datetime import datetime, date
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    from logger_config import get_logger, configure_windows_encoding
    configure_windows_encoding()
    log = get_logger("birth-age")
except ImportError:
    import logging
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(level=logging.INFO, format="[BirthAge] %(asctime)s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("birthage")

from bot_base import get_token
TOKEN = get_token("BOT_BIRTH_AGE_TOKEN")
STORE_URL = "https://t.me/BodaStoreeBot"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

def app_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات Boda", url=STORE_URL))
    return kb

def get_day_name_arabic(date_obj):
    days = {
        'Saturday': 'السبت', 'Sunday': 'الأحد', 'Monday': 'الاثنين',
        'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء', 'Thursday': 'الخميس', 'Friday': 'الجمعة'
    }
    return days.get(date_obj.strftime('%A'), date_obj.strftime('%A'))

def get_zodiac_sign(day, month):
    if (month == 1 and day >= 20) or (month == 2 and day <= 18): return "الدلو ♒"
    elif (month == 2 and day >= 19) or (month == 3 and day <= 20): return "الحوت ♓"
    elif (month == 3 and day >= 21) or (month == 4 and day <= 19): return "الحمل ♈"
    elif (month == 4 and day >= 20) or (month == 5 and day <= 20): return "الثور ♉"
    elif (month == 5 and day >= 21) or (month == 6 and day <= 20): return "الجوزاء ♊"
    elif (month == 6 and day >= 21) or (month == 7 and day <= 22): return "السرطان ♋"
    elif (month == 7 and day >= 23) or (month == 8 and day <= 22): return "الأسد ♌"
    elif (month == 8 and day >= 23) or (month == 9 and day <= 22): return "العذراء ♍"
    elif (month == 9 and day >= 23) or (month == 10 and day <= 22): return "الميزان ♎"
    elif (month == 10 and day >= 23) or (month == 11 and day <= 21): return "العقرب ♏"
    elif (month == 11 and day >= 22) or (month == 12 and day <= 21): return "القوس ♐"
    elif (month == 12 and day >= 22) or (month == 1 and day <= 19): return "الجدي ♑"
    return "غير معروف ❓"

def age_in_details(birth_date):
    today = date.today()
    years = today.year - birth_date.year
    months = today.month - birth_date.month
    days = today.day - birth_date.day
    
    if days < 0:
        months -= 1
        try:
            last_month = today.replace(month=today.month - 1)
        except ValueError:
            last_month = today.replace(year=today.year - 1, month=12)
        import calendar
        days += calendar.monthrange(last_month.year, last_month.month)[1]
        
    if months < 0:
        years -= 1
        months += 12
        
    total_days = (today - birth_date).days
    total_weeks = total_days // 7
    total_hours = total_days * 24
    total_minutes = total_hours * 60
    total_seconds = total_minutes * 60
    
    heartbeats = total_minutes * 80
    breaths = total_minutes * 16
    
    return {
        'years': years, 'months': months, 'days': days,
        'total_months': (years * 12) + months, 'total_weeks': total_weeks,
        'total_days': total_days, 'total_hours': total_hours,
        'total_minutes': total_minutes, 'total_seconds': total_seconds,
        'heartbeats': heartbeats, 'breaths': breaths
    }

def calculate_next_birthday(birth_date):
    today = date.today()
    try:
        next_birthday = date(today.year, birth_date.month, birth_date.day)
    except ValueError:
        next_birthday = date(today.year, 2, 28)
    if next_birthday < today:
        try:
            next_birthday = date(today.year + 1, birth_date.month, birth_date.day)
        except ValueError:
            next_birthday = date(today.year + 1, 2, 28)
    return (next_birthday - today).days

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 مرحباً بك في <b>حاسبة العمر المتطورة</b>!\n\n"
        "أكثر من مجرد حساب عمر، نحن نقدم لك:\n"
        "🔹 تحليلاً دقيقاً لأيامك، أسابيعك، وشهورك.\n"
        "🔹 معرفة برجك الفلكي ولغة جسدك.\n"
        "🔹 إحصائيات لحياتك مثل خفقات قلبك.\n\n"
        "👇 <b>للشروع، فقط أرسل تاريخ ميلادك بأحد الصيغ التالية:</b>\n"
        "📅 <code>1995-12-25</code> (سنة-شهر-يوم)\n"
        "📅 <code>25-12-1995</code> (يوم-شهر-سنة)\n"
        "📅 <code>1995/12/25</code>\n"
        "📅 <code>25/12/1995</code>"
    )
    bot.reply_to(message, welcome_text, reply_markup=app_kb())

@bot.message_handler(func=lambda msg: True)
def process_date(message):
    text = message.text.strip().replace('/', '-')
    match = re.search(r'(\d{2,4}-\d{1,2}-\d{1,4})', text)
    
    if not match:
        bot.reply_to(message, "⚠️ يرجى إرسال تاريخ صحيح بصيغة <code>YYYY-MM-DD</code> أو <code>DD-MM-YYYY</code>.")
        return
        
    date_str = match.group(1)
    
    # Try parsing
    parts = date_str.split('-')
    if len(parts[0]) == 4:
        # YYYY-MM-DD
        fmt = "%Y-%m-%d"
    else:
        # DD-MM-YYYY
        fmt = "%d-%m-%Y"
        
    try:
        birth_date = datetime.strptime(date_str, fmt).date()
    except ValueError:
        bot.reply_to(message, "❌ التاريخ المدخل غير صالح، أو الشهر/اليوم خارج النطاق.")
        return

    if birth_date > date.today():
        bot.reply_to(message, "⏳ هل ولدت في المستقبل؟ أرسل تاريخ ميلاد حقيقي!")
        return
        
    age_info = age_in_details(birth_date)
    day_name = get_day_name_arabic(birth_date)
    zodiac = get_zodiac_sign(birth_date.day, birth_date.month)
    next_bday = calculate_next_birthday(birth_date)
    is_leap = "نعم (كبيسة 🌟)" if (birth_date.year % 4 == 0 and (birth_date.year % 100 != 0 or birth_date.year % 400 == 0)) else "لا"

    res = f"🎉 <b>نتيجتك المفصلة جاهزة!</b>\n\n"
    res += f"<b>📅 العمر الأساسي:</b>\n"
    res += f"أنت تبلغ من العمر {age_info['years']} سنة، و {age_info['months']} شهراً، و {age_info['days']} يوماً.\n\n"
    
    res += f"<b>🔮 معلوماتك الفلكية والشخصية:</b>\n"
    res += f"• يوم الميلاد: {day_name}\n"
    res += f"• البرج الفلكي: {zodiac}\n"
    res += f"• سنة الميلاد: {is_leap}\n\n"
    
    res += f"<b>📊 إحصائياتك الشاملة بالأرقام:</b>\n"
    res += f"• الشهور الإجمالية: {age_info['total_months']:,}\n"
    res += f"• الأسابيع الإجمالية: {age_info['total_weeks']:,}\n"
    res += f"• الأيام الإجمالية: {age_info['total_days']:,}\n"
    res += f"• الساعات الإجمالية: {age_info['total_hours']:,}\n"
    res += f"• الدقائق الإجمالية: {age_info['total_minutes']:,}\n"
    res += f"• الثواني الإجمالية: {age_info['total_seconds']:,}\n\n"
    
    res += f"<b>💓 لغة الجسد والحياة:</b>\n"
    res += f"• قلبـــــك نـبض: ~{age_info['heartbeats']:,} مرة\n"
    res += f"• تتنفس بمعـدل: ~{age_info['breaths']:,} مرة\n\n"
    
    res += f"<b>⏳ موعد الحفلة القادمة:</b>\n"
    res += f"عيد ميلادك القادم بعد: {next_bday} يوماً 🎈\n\n"
    
    res += "<b>بواسطة:</b> متجر تطبيقات Boda 🏪"
    
    bot.send_message(message.chat.id, res, reply_markup=app_kb())

if __name__ == "__main__":
    from bot_base import start_bot
    start_bot(bot, "birth_age")
