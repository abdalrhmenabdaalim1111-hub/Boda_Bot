# -*- coding: utf-8 -*-
"""
Bots_Folder/utils.py — أدوات البوابة الموحدة (القناتان فقط).

كل البوتات التي تستورد is_subscribed / send_subscription_prompt من هنا
تحصل تلقائياً على بوابة القناتين:
    @Stick_boda  +  @ebdo_4

لا توجد أي بوابة "5 بوتات" بعد الآن.
"""
import logging

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

try:
    from . import gate_check
except ImportError:  # تشغيل مباشر من داخل Bots_Folder
    import gate_check

log = logging.getLogger("utils")

STORE_URL = "https://t.me/BodaStoreeBot"


def app_kb():
    """لوحة أزرار المتجر الافتراضية."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🏪 متجر تطبيقات Boda", url=STORE_URL))
    return kb


def is_subscribed(bot, user_id):
    """
    فحص اشتراك المستخدم في القناتين المطلوبتين.

    نفس التوقيع القديم — تعمل في كل البوتات دون أي تعديل.
    ترجع True عند الاشتراك أو عند عطل البنية (فشل مفتوح).
    """
    try:
        return gate_check.is_subscribed(int(user_id))
    except Exception as exc:
        log.error("gate check error: %s", exc)
        return True


def send_subscription_prompt(bot, chat_id):
    """إرسال بوابة القناتين مع زر التحقق."""
    try:
        missing = gate_check.get_missing_channels(int(chat_id), use_cache=False)
        if not missing:
            return
        bot.send_message(
            chat_id,
            gate_check.gate_text(missing),
            reply_markup=gate_check.gate_markup(missing),
            parse_mode="HTML",
        )
    except Exception as exc:
        log.error("gate prompt error: %s", exc)
