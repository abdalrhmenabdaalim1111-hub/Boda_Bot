# -*- coding: utf-8 -*-
"""
Bots_Folder/gate_middleware.py — نظام بوابة الاشتراك الإجباري (القنوات الرسمية)
"""

import logging
from telebot import TeleBot, types

logger = logging.getLogger("GateMiddleware")

# القنوات الرسمية المطلوب الاشتراك بها
REQUIRED_CHANNELS = [
    {"username": "@Stick_boda", "title": "عالم بودة ✨"},
    {"username": "@ebdo_4", "title": "قناة التحديثات 🚀"}
]

class GateMiddleware:
    def __init__(self, bot: TeleBot, bot_id: str, db=None):
        self.bot = bot
        self.bot_id = bot_id

    def is_subscribed(self, user_id: int) -> bool:
        """يتحقق من اشتراك المستخدم في القناتين."""
        for channel in REQUIRED_CHANNELS:
            try:
                status = self.bot.get_chat_member(channel["username"], user_id).status
                if status not in ['member', 'administrator', 'creator']:
                    return False
            except Exception:
                # في حال تعذر الفحص (مثلاً البوت ليس آدمن)، نتجاوز القناة للأمان
                continue
        return True

    def check_and_show_gate(self, message: types.Message) -> bool:
        """يفحص الاشتراك ويظهر الرسالة إذا لزم الأمر."""
        user_id = message.from_user.id
        
        # استثناء الأدمن (اختياري)
        # if user_id == YOUR_ADMIN_ID: return False

        if self.is_subscribed(user_id):
            return False

        # إذا لم يكن مشتركاً، تظهر الرسالة
        self.show_gate(message)
        return True

    def show_gate(self, message: types.Message):
        """إرسال رسالة الاشتراك الإجباري."""
        text = (
            "🔒 <b>تفعيل الحساب — نظام بودة الموحد</b>\n"
            "────────────────────────\n"
            "مرحباً بك! للاستمتاع بخدمات هذا البوت وكافة ميزاته مجاناً وبدون توقف، "
            "يُشترط تفعيل عضويتك عبر الاشتراك في قنواتنا الرسمية:\n\n"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, channel in enumerate(REQUIRED_CHANNELS, 1):
            text += f"{i}️⃣ <b>{channel['title']}</b> ({channel['username']})\n"
            markup.add(types.InlineKeyboardButton(f"📢 اشترك في: {channel['title']}", url=f"https://t.me/{channel['username'].replace('@', '')}"))
        
        text += "\n👇 <b>اشترك في القنوات أعلاه، ثم اضغط على 'تحقق من التفعيل':</b>"
        
        markup.add(types.InlineKeyboardButton("✅ تحقق من التفعيل", callback_data="gate_verify:direct"))
        
        self.bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=markup)

    def handle_verify_callback(self, call: types.CallbackQuery):
        """معالجة ضغطة زر التحقق."""
        user_id = call.from_user.id
        
        if self.is_subscribed(user_id):
            self.bot.answer_callback_query(call.id, "✅ تم تفعيل حسابك بنجاح! يمكنك الآن استخدام البوت.")
            try:
                self.bot.edit_message_text(
                    "<b>✅ تم تفعيل العضوية بنجاح!</b>\n\nأرسل /start الآن للبدء.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        else:
            self.bot.answer_callback_query(call.id, "❌ ما زلت غير مشترك في جميع القنوات!", show_alert=True)
