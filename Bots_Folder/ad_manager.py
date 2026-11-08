"""
Bots_Folder/ad_manager.py — نظام إدارة الإعلانات والاشتراك الإجباري للبوتات
يوفر تحكماً مركزياً للإعلانات والربح عبر كافة بوتات النظام دون تعديل الكود في كل مرة.

الميزات:
1. الاشتراك الإجباري بقنوات الرعاة (Force Subscribe Gate)
2. إعلان في ذيل الرسائل (Footer Text Ad)
3. أزرار إعلانية تفاعلية (Inline Sponsor Buttons)
4. حملات بث إعلاني للمستخدمين (Broadcast Engine)
5. تفعيل / إيقاف الإعلانات والتحكم بنسب الظهور من ملف الإعدادات Data/ads_config.json
"""
import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("AdManager")

DATA_DIR = Path(__file__).parent.parent / "Data"
ADS_CONFIG_FILE = DATA_DIR / "ads_config.json"

DEFAULT_ADS_CONFIG = {
    "enabled": True,
    "force_subscribe": {
        "enabled": False,
        "channel_username": "@MySponsorChannel",
        "channel_title": "قناة العروض والخصومات",
        "invite_link": "https://t.me/MySponsorChannel",
        "gate_message": "⚠️ <b>عذراً عزيزي المستخدم!</b>\n\nلاستخدام البوت مجاناً، يرجى الاشتراك في قناة الراعي أولاً ثم اضغط تحقق:\n👇"
    },
    "footer_ad": {
        "enabled": True,
        "frequency": 3,
        "text": "\n\n──────────────\n📢 <b>برعاية:</b> <a href='https://t.me/BodaStoreeBot'>متجر تطبيقات بودا</a> — حمّل أقوى البوتات مجاناً!"
    },
    "button_ad": {
        "enabled": True,
        "button_text": "🌟 قناة الراعي الرسمي",
        "url": "https://t.me/BodaStoreeBot"
    }
}


class AdManager:
    """مدير الإعلانات المركزي"""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or ADS_CONFIG_FILE
        self._user_msg_count: Dict[int, int] = {}
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """تحميل إعدادات الإعلانات من الملف"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_file.exists():
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_ADS_CONFIG, f, ensure_ascii=False, indent=2)
                return DEFAULT_ADS_CONFIG.copy()
            except Exception:
                return DEFAULT_ADS_CONFIG.copy()

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في قراءة ملف الإعلانات: {e}")
            return DEFAULT_ADS_CONFIG.copy()

    def save_config(self, new_config: dict):
        """حفظ إعدادات إعلانية جديدة"""
        self.config = new_config
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)

    def is_enabled(self) -> bool:
        """هل نظام الإعلانات مفعّل كلياً؟"""
        return self.config.get("enabled", True)

    def check_force_subscribe(self, bot, user_id: int) -> Tuple[bool, Optional[str], Optional[Any]]:
        """
        التحقق من اشتراك المستخدم في القناة الإجبارية.

        Returns:
            (is_subscribed, alert_message, inline_keyboard)
        """
        if not self.is_enabled():
            return True, None, None

        fs = self.config.get("force_subscribe", {})
        if not fs.get("enabled"):
            return True, None, None

        channel = fs.get("channel_username")
        if not channel or channel == "@MySponsorChannel":
            return True, None, None

        try:
            member = bot.get_chat_member(channel, user_id)
            # الحالات المقبولة في تيليجرام
            if member.status in ("member", "administrator", "creator"):
                return True, None, None
        except Exception as e:
            logger.warning(f"تعذر التحقق من عضوية القناة للمستخدم {user_id}: {e}")
            # عند فشل الاتصال بتيليجرام نسمح للمستخدم بالمرور منعاً لتعطيل الخدمة
            return True, None, None

        # إنشاء كيبورد الاشتراك والتحقق
        msg = fs.get("gate_message", "يرجى الاشتراك في القناة للاستمرار.")

        try:
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(
                InlineKeyboardButton(f"📢 اشترك في {fs.get('channel_title', 'القناة')}", url=fs.get("invite_link")),
                InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_subscription_status")
            )
        except ImportError:
            class DummyButton:
                def __init__(self, text, url=None, callback_data=None):
                    self.text = text
                    self.url = url
                    self.callback_data = callback_data
            class DummyMarkup:
                def __init__(self):
                    self.keyboard = []
                def add(self, *buttons):
                    self.keyboard.extend(buttons)
            kb = DummyMarkup()
            kb.add(
                DummyButton(f"📢 اشترك في {fs.get('channel_title', 'القناة')}", url=fs.get("invite_link")),
                DummyButton("🔄 تحقق من الاشتراك", callback_data="check_subscription_status")
            )

        return False, msg, kb

    def get_footer_ad(self, user_id: Optional[int] = None) -> str:
        """
        إرجاع نص إعلان الذيل المرفق بالرسائل بحسب التكرار (Frequency)
        """
        if not self.is_enabled():
            return ""

        f_ad = self.config.get("footer_ad", {})
        if not f_ad.get("enabled"):
            return ""

        freq = f_ad.get("frequency", 1)
        if user_id:
            count = self._user_msg_count.get(user_id, 0) + 1
            self._user_msg_count[user_id] = count
            if count % freq != 0:
                return ""

        return f_ad.get("text", "")

    def attach_ad_to_text(self, text: str, user_id: Optional[int] = None) -> str:
        """دمج الإعلان مع نص الرسالة تلقائياً"""
        ad = self.get_footer_ad(user_id)
        return f"{text}{ad}" if ad else text

    def get_ad_button(self):
        """إرجاع زر إعلاني Inline إذا كان مفعلاً"""
        if not self.is_enabled():
            return None

        b_ad = self.config.get("button_ad", {})
        if not b_ad.get("enabled"):
            return None

        try:
            from telebot.types import InlineKeyboardButton
            return InlineKeyboardButton(
                text=b_ad.get("button_text", "🌟 إعلان"),
                url=b_ad.get("url", "https://t.me/BodaStoreeBot")
            )
        except ImportError:
            class DummyButton:
                def __init__(self, text, url=None):
                    self.text = text
                    self.url = url
            return DummyButton(
                text=b_ad.get("button_text", "🌟 إعلان"),
                url=b_ad.get("url", "https://t.me/BodaStoreeBot")
            )


_ad_manager_instance = None

def get_ad_manager() -> AdManager:
    """الحصول على نسخة نظام الإعلانات المشتركة (Singleton)"""
    global _ad_manager_instance
    if _ad_manager_instance is None:
        _ad_manager_instance = AdManager()
    return _ad_manager_instance
