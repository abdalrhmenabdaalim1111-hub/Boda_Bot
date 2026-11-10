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
import re
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("AdManager")

DATA_DIR = Path(__file__).parent.parent / "Data"
ADS_CONFIG_FILE = DATA_DIR / "ads_config.json"
MONETAG_CONFIG_FILE = DATA_DIR / "monetag_config.json"

# ── تتبع نقرات الإعلانات بلا استضافة ─────────────────────────────────────────
# زر الإعلان يفتح رابطاً عميقاً لبوت المتجر: /start adclick_<bot_id>
# فيسجّل المتجر النقرة في قاعدة البيانات ثم يعرض رابط Monetag للعرض.
STORE_BOT_USERNAME = os.getenv("BODA_STORE_BOT_USERNAME", "BodaStoreeBot").lstrip("@")
AD_CLICK_PREFIX = "adclick_"

DEFAULT_MONETAG_CONFIG = {
    "_version": "1.0",
    "_provider": "Monetag (monetag.com)",
    "_description": "إعدادات شفرات إعلانات Monetag المخصصة لكل بوت وتطبيق مصغر",
    "global_default": {
        "enabled": True,
        "direct_link": "",
        "zone_id": "",
        "script_url": "",
        "format": "direct_link",
        "frequency": 3,
        "note": "الشفرات الافتراضية الموحدة لجميع البوتات التي لا تملك شفرات مخصصة"
    },
    "bots": {}
}

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

    def __init__(self, config_file: Optional[Path] = None, monetag_file: Optional[Path] = None):
        self.config_file = config_file or ADS_CONFIG_FILE
        self.monetag_file = monetag_file or MONETAG_CONFIG_FILE
        self._user_msg_count: Dict[int, int] = {}
        self.config = self._load_config()
        self.monetag_config = self._load_monetag_config()

    def _load_monetag_config(self) -> dict:
        """تحميل إعدادات شفرات إعلانات Monetag المخصصة لكل بوت"""
        self.monetag_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.monetag_file.exists():
            try:
                with open(self.monetag_file, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_MONETAG_CONFIG, f, ensure_ascii=False, indent=2)
                return DEFAULT_MONETAG_CONFIG.copy()
            except Exception:
                return DEFAULT_MONETAG_CONFIG.copy()

        try:
            with open(self.monetag_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في قراءة ملف إعدادات Monetag: {e}")
            return DEFAULT_MONETAG_CONFIG.copy()

    def save_monetag_config(self, new_config: dict):
        """حفظ إعدادات إعلانات Monetag المحدثة"""
        self.monetag_config = new_config
        with open(self.monetag_file, "w", encoding="utf-8") as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)

    def get_monetag_config(self, bot_id: str) -> dict:
        """الحصول على إعدادات Monetag لبوت معين مع استخدام الشفرة العامة كـ fallback."""
        clean_id = bot_id.replace("bot_", "")
        bots_cfg = self.monetag_config.get("bots", {})
        bot_cfg = bots_cfg.get(clean_id, {})
        
        # إذا كان للبوت إعداد مخصص نشط وبه رابط أو معرف
        if bot_cfg.get("has_custom_ads") and bot_cfg.get("active", True) and (bot_cfg.get("direct_link") or bot_cfg.get("zone_id") or bot_cfg.get("script_url")):
            return bot_cfg

        # الرجوع إلى الإعداد العام الموحد
        global_cfg = self.monetag_config.get("global_default", {})
        merged = dict(bot_cfg) if bot_cfg else {"bot_name": clean_id}
        merged["direct_link"] = merged.get("direct_link") or global_cfg.get("direct_link", "")
        merged["zone_id"] = merged.get("zone_id") or global_cfg.get("zone_id", "")
        merged["script_url"] = merged.get("script_url") or global_cfg.get("script_url", "")
        merged["format"] = merged.get("format") or global_cfg.get("format", "direct_link")
        merged["frequency"] = merged.get("frequency") or global_cfg.get("frequency", 3)
        merged["is_global_fallback"] = True
        return merged

    def set_monetag_config(self, bot_id: str, direct_link: str = "", zone_id: str = "",
                           script_url: str = "", format_type: str = "direct_link",
                           frequency: int = 3, active: bool = True) -> bool:
        """تحديث وحفظ شفرات إعلانات Monetag لبوت معين."""
        from datetime import datetime
        clean_id = bot_id.replace("bot_", "")
        if "bots" not in self.monetag_config:
            self.monetag_config["bots"] = {}

        has_code = bool(direct_link.strip() or zone_id.strip() or script_url.strip())
        current = self.monetag_config["bots"].get(clean_id, {})
        current.update({
            "has_custom_ads": has_code,
            "direct_link": direct_link.strip(),
            "zone_id": zone_id.strip(),
            "script_url": script_url.strip(),
            "format": format_type,
            "frequency": frequency,
            "active": active if has_code else False,
            "last_updated": datetime.now().isoformat()
        })
        self.monetag_config["bots"][clean_id] = current
        self.save_monetag_config(self.monetag_config)
        logger.info(f"✅ تم تحديث شفرات إعلانات Monetag للبوت [{clean_id}]")
        return True

    def set_global_monetag_default(self, direct_link: str = "", zone_id: str = "",
                                   script_url: str = "", format_type: str = "direct_link",
                                   frequency: int = 3, enabled: bool = True) -> bool:
        """ضبط الشفرة الإعلانية الموحدة (Global Default) لجميع البوتات التي ليس لها شفرة خاصة."""
        self.monetag_config["global_default"] = {
            "enabled": enabled,
            "direct_link": direct_link.strip(),
            "zone_id": zone_id.strip(),
            "script_url": script_url.strip(),
            "format": format_type,
            "frequency": frequency,
            "note": "الشفرات الافتراضية الموحدة لجميع البوتات التي لا تملك شفرات مخصصة"
        }
        self.save_monetag_config(self.monetag_config)
        logger.info("✅ تم تحديث الشفرة الإعلانية الموحدة لـ Monetag")
        return True

    def has_monetag_ad(self, bot_id: str) -> bool:
        """هل هذا البوت/التطبيق مزود بشفرة إعلانية (مخصصة أو عامة)؟"""
        cfg = self.get_monetag_config(bot_id)
        return bool(cfg.get("direct_link") or cfg.get("zone_id") or cfg.get("script_url"))

    def has_custom_monetag_ad(self, bot_id: str) -> bool:
        """هل هذا البوت تحديداً له شفرة خاصة به (وليس مجرد fallback عام)؟"""
        clean_id = bot_id.replace("bot_", "")
        b = self.monetag_config.get("bots", {}).get(clean_id, {})
        return bool(b.get("has_custom_ads") and (b.get("direct_link") or b.get("zone_id") or b.get("script_url")))

    def record_ad_view(self, bot_id: str, format_type: str = "direct_link"):
        """تسجيل مشاهدة إعلان في قاعدة البيانات المركزية."""
        try:
            from database import get_db
            db = get_db()
            if db:
                db.record_ad_impression(bot_id, format_type)
        except Exception as e:
            logger.debug(f"record_ad_view error: {e}")

    def record_ad_click(self, bot_id: str, format_type: str = "direct_link"):
        """تسجيل نقرة إعلان في قاعدة البيانات المركزية."""
        try:
            from database import get_db
            db = get_db()
            if db:
                db.record_ad_click(bot_id, format_type)
        except Exception as e:
            logger.debug(f"record_ad_click error: {e}")

    # ── A/B Testing: تعيين ثابت لكل مستخدم + تسجيل بُعد المجموعة ─────────────
    @staticmethod
    def compute_ab_variant(user_id: int) -> str:
        """
        تعيين A/B ثابت للمستخدم — نفس المستخدم = نفس المجموعة دائماً.
        تجزئة md5 على "boda:<user_id>" → توزيع متوازن تقريباً 50/50
        ومستقل عن ترتيب التسجيل أو حفظ أي شيء.
        """
        import hashlib
        digest = hashlib.md5(f"boda:{user_id}".encode()).hexdigest()
        return "A" if int(digest[:8], 16) % 2 == 0 else "B"

    def record_ab_view(self, bot_id: str, user_id: int,
                       format_type: str = "direct_link") -> str:
        """تسجيل ظهور إعلان مع مجموعة A/B للمستخدم — يعيد المجموعة."""
        variant = self.compute_ab_variant(user_id)
        try:
            from database import get_db
            db = get_db()
            if db:
                db.record_ab_event(bot_id, format_type, variant, is_click=False)
        except Exception as e:
            logger.debug(f"record_ab_view error: {e}")
        return variant

    def record_ab_click(self, bot_id: str, user_id: int,
                        format_type: str = "direct_link") -> str:
        """تسجيل نقرة إعلان مع مجموعة A/B للمستخدم — يعيد المجموعة."""
        variant = self.compute_ab_variant(user_id)
        try:
            from database import get_db
            db = get_db()
            if db:
                db.record_ab_event(bot_id, format_type, variant, is_click=True)
        except Exception as e:
            logger.debug(f"record_ab_click error: {e}")
        return variant

    def get_all_monetag_statuses(self) -> Dict[str, dict]:
        """إرجاع تقرير شامل بحالة إعلانات Monetag لجميع البوتات الـ 36."""
        statuses = {}
        bots_cfg = self.monetag_config.get("bots", {})
        global_cfg = self.monetag_config.get("global_default", {})
        global_has = bool(global_cfg.get("direct_link") or global_cfg.get("zone_id") or global_cfg.get("script_url"))

        # جلب إحصائيات المشاهدات والنقرات إن وجدت
        ad_stats_map = {}
        try:
            from database import get_db
            db = get_db()
            if db:
                stats = db.get_ad_stats()
                for s in stats:
                    ad_stats_map[s["bot_name"]] = s
        except Exception:
            pass

        for bid, b in bots_cfg.items():
            has_custom = bool(b.get("has_custom_ads") and (b.get("direct_link") or b.get("zone_id") or b.get("script_url")))
            active = has_custom or global_has
            st = ad_stats_map.get(bid, {})
            statuses[bid] = {
                "bot_name": b.get("bot_name", bid),
                "has_ad": active,
                "is_custom": has_custom,
                "is_global": (not has_custom and global_has),
                "format": b.get("format", "direct_link"),
                "zone_id": b.get("zone_id", ""),
                "direct_link": b.get("direct_link") or (global_cfg.get("direct_link", "") if global_has else ""),
                "impressions": st.get("impressions", 0),
                "clicks": st.get("clicks", 0),
                "ctr_percent": st.get("ctr_percent", 0.0),
                "last_updated": b.get("last_updated")
            }
        return statuses

    # ── تتبع نقرات Monetag عبر رابط عميق لبوت المتجر ─────────────────────────
    def build_ad_click_url(self, bot_id: str) -> str:
        """رابط عميق لتسجيل النقرة ثم عرض الإعلان — يعيد "" إن لم تُضبط شفرة."""
        clean_id = bot_id.replace("bot_", "").strip().lower()
        if not clean_id:
            return ""
        cfg = self.get_monetag_config(clean_id)
        if not cfg.get("direct_link"):
            return ""
        return f"https://t.me/{STORE_BOT_USERNAME}?start={AD_CLICK_PREFIX}{clean_id}"

    def resolve_ad_click(self, bot_id: str) -> Optional[dict]:
        """تسجيل نقرة إعلان من رابط التتبع وإرجاع معلومات العرض للعرض."""
        clean_id = bot_id.replace("bot_", "").strip().lower()
        cfg = self.get_monetag_config(clean_id)
        direct = cfg.get("direct_link", "").strip()
        if not clean_id or not direct:
            return None
        self.record_ad_click(clean_id, "direct_link")
        return {
            "bot_id": clean_id,
            "bot_name": cfg.get("bot_name", clean_id),
            "direct_link": direct,
            "zone_id": cfg.get("zone_id", ""),
        }

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


# ─────────────────────────────────────────────────────────────────────────────
#  التركيب التلقائي على أي بوت — attach_unified_ads(bot, bot_name)
#  يُستدعى من bot_base.start_polling/start_webhook تلقائياً:
#    • يغلّف bot.send_message بحيث يُلحق إعلان الذيل حسب التكرار المضبوط
#      (في المحادثات الخاصة فقط، مع احترام وضع HTML أو النص العادي)
# ─────────────────────────────────────────────────────────────────────────────
_TAG_RE = None


def _strip_html(text: str) -> str:
    """إزالة وسوم HTML من نص الإعلان عند إرساله في رسالة نصية عادية"""
    global _TAG_RE
    if _TAG_RE is None:
        import re
        _TAG_RE = re.compile(r"<[^>]+>")
    return _TAG_RE.sub("", text)


def attach_unified_ads(bot, bot_name: str = "bot"):
    """تطبيق نظام الإعلانات المركزي على بوت دون تعديل كوده"""
    mgr = get_ad_manager()
    if not mgr.is_enabled():
        return

    original_send = bot.send_message
    logger.info(f"📢 نظام الإعلانات الموحد مفعّل على: {bot_name}")

    def send_message_with_ads(*args, **kwargs):
        try:
            text = args[1] if len(args) > 1 else kwargs.get("text", "")
            chat_id = args[0] if args else kwargs.get("chat_id")
            # إعلانات المحادثات الخاصة فقط (chat_id موجب = مستخدم)
            uid = chat_id if isinstance(chat_id, int) and chat_id > 0 else None

            if isinstance(text, str) and text and uid:
                ad = mgr.get_footer_ad(uid)
                if ad:
                    parse_mode = kwargs.get("parse_mode") or (len(args) > 2 and args[2])
                    if parse_mode:
                        kwargs["parse_mode"] = parse_mode
                        text = text + ad
                    else:
                        # رسالة نصية عادية → ننظف الوسوم من الإعلان
                        text = text + _strip_html(ad)
                    if len(args) > 1:
                        args = (args[0], text) + tuple(args[2:])
                    else:
                        kwargs["text"] = text
                    mgr.record_ad_view(bot_name, "footer")
        except Exception:
            pass  # الإعلان لا يعطّل الرسالة أبداً
        return original_send(*args, **kwargs)

    bot.send_message = send_message_with_ads


def parse_ad_click_payload(text: str) -> str:
    """استخراج معرف البوت من /start adclick_<id> — يعيد "" إن لم يكن أمر تتبع."""
    parts = (text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        return ""
    payload = parts[1].strip()
    if not payload.startswith(AD_CLICK_PREFIX):
        return ""
    bot_id = payload[len(AD_CLICK_PREFIX):].strip().lower()
    if re.fullmatch(r"[a-z0-9_]{2,32}", bot_id):
        return bot_id
    return ""


def get_monetag_button(bot_name: str = "bot"):
    """زر راعي Inline مرتبط بـ Monetag — عبر رابط تتبع يسجّل النقرة تلقائياً."""
    mgr = get_ad_manager()
    cfg = mgr.get_monetag_config(bot_name)
    link = cfg.get("direct_link", "").strip()
    if not link:
        return None
    url = mgr.build_ad_click_url(bot_name) or link
    try:
        from telebot.types import InlineKeyboardButton
        return InlineKeyboardButton(text="🔥 عرض حصري / راعي التطبيق", url=url)
    except Exception:
        return None
