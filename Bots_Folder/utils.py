"""
Bots_Folder/utils.py — أدوات موحدة لبوابات الاشتراك

⚠️ تغيير جذري (إصلاح رسالة "البوت ليس أدمن"):
الفحص القديم كان يستخدم get_chat_member على قناة — وهو ما يتطلب أن يكون البوت
أدمن في القناة، ويفشل تماماً عند التحقق من الاشتراك في *بوتات* (تيليجرام لا يسمح
لبوت بمعرفة ما إذا بدأ المستخدم بوتاً آخر عبر الـ API).

النظام الجديد: نفس التوقيع القديم تماماً (is_subscribed / send_subscription_prompt)
لكن التحقق يتم عبر شبكة الـ 5 بوتات وقاعدة البيانات المشتركة — كل بوت يسجل
مستخدميه فيها، فالتحقق يصبح سؤالاً محلياً بلا قنوات وبلا صلاحيات أدمن.
"""
import logging
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

log = logging.getLogger("utils")

STORE_URL = "https://t.me/BodaStoreeBot"


def app_kb():
    """Default keyboard with Store connection"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪 متجر تطبيقات Boda", url=STORE_URL))
    return kb


def _engine():
    """تحميل محرك النمو (مرة واحدة عبر singleton)"""
    try:
        from growth_engine import get_growth_engine
        return get_growth_engine()
    except Exception as e:
        log.error(f"تعذر تحميل محرك النمو: {e}")
        return None


def _current_bot_id(bot):
    """استنتاج معرّف البوت الحالي من اليوزرنيم (مخزن مؤقتاً على الكائن)"""
    cached = getattr(bot, "_boda_bot_id", None)
    if cached:
        return cached
    try:
        me = bot.get_me()
        uname = (me.username or "").lower()
        engine = _engine()
        bot_id = ""
        if engine:
            for b in engine._load_registry_pool():
                if b["username"].lstrip("@").lower() == uname:
                    bot_id = b["id"]
                    break
        if not bot_id:
            bot_id = uname
        bot._boda_bot_id = bot_id
        return bot_id
    except Exception:
        return ""


def is_subscribed(bot, user_id):
    """
    فحص تفعيل المستخدم في شبكة الـ 5 بوتات عبر قاعدة البيانات المشتركة.

    نفس توقيع النسخة القديمة — تعمل في كل البوتات دون أي تعديل.
    ترجع True عند التفعيل أو عند أي خطأ (فشل مفتوح — لا نعطل البوتات).
    """
    engine = _engine()
    if engine is None or not engine.is_enabled():
        return True
    try:
        allowed, _gate_text, _kb = engine.check_network_activation(
            bot, user_id, current_bot=_current_bot_id(bot))
        return allowed
    except Exception as e:
        log.error(f"خطأ فحص شبكة التفعيل: {e}")
        return True


def send_subscription_prompt(bot, chat_id):
    """إرسال بوابة التفعيل الشخصية — البوتات الخمسة الخاصة بهذا المستخدم"""
    engine = _engine()
    if engine is None:
        bot.send_message(chat_id, "⚠️ حدث خطأ تقني مؤقت، حاول مجدداً بعد قليل.")
        return
    try:
        # في المحادثات الخاصة chat_id == user_id
        allowed, gate_text, kb = engine.check_network_activation(
            bot, chat_id, current_bot=_current_bot_id(bot))
        if allowed:
            return
        bot.send_message(chat_id, gate_text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        log.error(f"خطأ إرسال بوابة التفعيل: {e}")
