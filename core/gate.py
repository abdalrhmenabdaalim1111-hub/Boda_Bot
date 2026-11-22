# -*- coding: utf-8 -*-
"""
core/gate.py — نظام بوابة الاشتراك الإجباري (Mandatory Sub Gate)
"""

import telebot
from telebot import types

# قائمة القنوات المطلوبة (يتم الفحص عليها)
REQUIRED_CHANNELS = [
    "@Stick_boda",
    "@ebdo_4"
]

def is_subscribed(bot: telebot.TeleBot, user_id: int) -> bool:
    """يتحقق مما إذا كان المستخدم مشتركاً في القنوات."""
    if not REQUIRED_CHANNELS:
        return True
    
    for channel in REQUIRED_CHANNELS:
        try:
            status = bot.get_chat_member(channel, user_id).status
            # المشترك، الآدمن، والمالك مسموح لهم
            if status not in ['member', 'administrator', 'creator']:
                return False
        except Exception:
            # إذا كان البوت ليس آدمن في القناة، لا يمكنه الفحص
            return False
    return True

def get_subscribe_keyboard():
    """لوحة أزرار القنوات مع روابط مباشرة."""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    names = {
        "@Stick_boda": "عالم بودة ✨",
        "@ebdo_4": "قناة التحديثات 🚀"
    }

    for channel in REQUIRED_CHANNELS:
        label = names.get(channel, f"اشترك في {channel}")
        markup.add(types.InlineKeyboardButton(f"📢 {label}", url=f"https://t.me/{channel.replace('@', '')}"))
    
    markup.add(types.InlineKeyboardButton("✅ تم الاشتراك، ابدأ الاستخدام", callback_data="verify_sub"))
    return markup

def send_gate_message(bot: telebot.TeleBot, chat_id: int):
    """الرسالة التي تظهر للمستخدم غير المشترك."""
    text = (
        "⚠️ <b>عذراً عزيزي، الاشتراك إجباري!</b>\n\n"
        "للاستمرار في استخدام البوت وجميع خدماتنا المجانية، "
        "يرجى الانضمام للقنوات الرسمية أولاً لضمان وصول التحديثات إليك.\n\n"
        "👇 اشترك ثم اضغط على زر التحقق بالأسفل:"
    )
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_subscribe_keyboard())
