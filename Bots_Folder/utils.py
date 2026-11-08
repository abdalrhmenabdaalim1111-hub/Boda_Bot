import logging
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

log = logging.getLogger("utils")

CHANNEL_URL = "https://t.me/MyToolsGuide"
CHANNEL_USERNAME = "@MyToolsGuide"
STORE_URL = "https://t.me/BodaStoreeBot"

def app_kb():
    """Default keyboard with Store connection"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪 متجر تطبيقات Boda", url=STORE_URL))
    return kb

def sub_kb():
    """Keyboard prompting for subscription"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📢 اشترك في القناة الآن", url=CHANNEL_URL),
        InlineKeyboardButton("🏪 متجر تطبيقات Boda", url=STORE_URL)
    )
    return kb

def is_subscribed(bot, user_id):
    """
    Check if the user is a member/admin/creator of the specific channel.
    The bot MUST be an admin in CHANNEL_USERNAME for this to work.
    """
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except ApiTelegramException as e:
        err = str(e).lower()
        # If the bot is not an admin, it'll raise "inaccessible", "chat not found", or "not a member"
        if "chat not found" in err or "not a member" in err or "inaccessible" in err:
            log.error(f"Cannot check subscription for {CHANNEL_USERNAME}. The bot MUST BE AN ADMIN! Error: {e}")
            try:
                bot.send_message(user_id, "⚠️ <b>خطأ تقني:</b> البوت ليس (أدمن - Administrator) في القناة. برجاء إخبار صاحب البوت برفع البوت كمسؤول ليتمكن من التحقق من الاشتراك.", parse_mode="HTML")
            except: pass
            return False 
        return False
    except Exception as e:
        log.error(f"Subscription check error: {e}")
        return True

def send_subscription_prompt(bot, chat_id):
    """Send the elegant mandatory subscription message"""
    bot.send_message(
        chat_id,
        "⚠️ <b>عذراً، يجب عليك الاشتراك في قناتنا أولاً!</b>\n\n"
        "لضمان استمرار عمل البوت مجاناً وبأعلى جودة، يُرجى الاشتراك في القناة الرسمية ثم العودة لاستخدام البوت.\n\n"
        "👇 <b>بعد الاشتراك، أرسل أي رسالة أو اضغط /start للتحقق:</b>",
        parse_mode="HTML",
        reply_markup=sub_kb()
    )
