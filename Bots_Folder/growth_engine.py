"""
Bots_Folder/growth_engine.py — محرك النمو والانتشار وربط البوتات بالمتجر
يوفر:
1. بوابة الاشتراك والتفعيل الإجباري في شبكة الـ 5 بوتات (من ضمنها المتجر)
2. نظام الإحالات الفيروسي ورابط الدعوة لكل مستخدم (Referral & Viral Growth)
3. الربط التلقائي لكل بوت مع متجر التطبيقات (Store Cross-linking)
4. أزرار المشاركة السريعة في تيليجرام
"""
import os
import sys
import json
import logging
from pathlib import Path
from urllib.parse import quote_plus
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger("GrowthEngine")

DATA_DIR = Path(__file__).parent.parent / "Data"
NETWORK_CONFIG_FILE = DATA_DIR / "network_config.json"

DEFAULT_NETWORK_CONFIG = {
    "enabled": True,
    "require_5_bots_activation": True,
    "store_bot_username": "@BodaStoreeBot",
    "store_bot_url": "https://t.me/BodaStoreeBot",
    "required_network_bots": [
        {
            "id": "store",
            "name": "🏪 متجر تطبيقات بودا",
            "username": "@BodaStoreeBot",
            "url": "https://t.me/BodaStoreeBot"
        },
        {
            "id": "vidload",
            "name": "📥 تحميل الفيديوهات (VidLoad)",
            "username": "@VidLoadXBot",
            "url": "https://t.me/VidLoadXBot"
        },
        {
            "id": "stickerx",
            "name": "🎨 صانع الملصقات (StickerX)",
            "username": "@StickerXMakerBot",
            "url": "https://t.me/StickerXMakerBot"
        },
        {
            "id": "cleantok",
            "name": "🎵 تيك توك بلا علامة (CleanTok)",
            "username": "@CleanTokVidBot",
            "url": "https://t.me/CleanTokVidBot"
        },
        {
            "id": "transbot",
            "name": "🌐 المترجم الفوري (TransBot)",
            "username": "@TransXNowBot",
            "url": "https://t.me/TransXNowBot"
        }
    ],
    "viral_rewards": {
        "required_invites_for_vip": 3,
        "vip_title": "🌟 عضوية VIP الذهبية"
    }
}


def _get_db():
    try:
        from database import get_db
        return get_db()
    except Exception:
        return None


class GrowthEngine:
    """محرك النمو والانتشار وشبكة البوتات المترابطة"""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or NETWORK_CONFIG_FILE
        self.config = self._load_config()

    def _load_config(self) -> dict:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_file.exists():
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_NETWORK_CONFIG, f, ensure_ascii=False, indent=2)
                return DEFAULT_NETWORK_CONFIG.copy()
            except Exception:
                return DEFAULT_NETWORK_CONFIG.copy()

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في قراءة ملف شبكة البوتات: {e}")
            return DEFAULT_NETWORK_CONFIG.copy()

    def is_enabled(self) -> bool:
        return self.config.get("enabled", True)

    # ── 1. فحص التفعيل الإجباري في شبكة الـ 5 بوتات ───────────────────────────
    def check_network_activation(self, bot, user_id: int) -> Tuple[bool, Optional[str], Optional[Any]]:
        """
        التحقق من تفعيل المستخدم في شبكة البوتات الـ 5.
        Returns:
            (is_activated, gate_message, inline_keyboard)
        """
        if not self.is_enabled() or not self.config.get("require_5_bots_activation", True):
            return True, None, None

        db = _get_db()
        if db and db.is_network_activated(user_id):
            return True, None, None

        # إنشاء رسالة وكيبورد التفعيل
        bots_list = self.config.get("required_network_bots", [])
        gate_text = (
            "🔒 <b>تفعيل الحساب — شبكة تطبيقات بودا</b>\n"
            "────────────────────────\n"
            "مرحباً بك! للاستمتاع بخدمات هذا البوت وكافة ميزاته مجاناً وبأعلى سرعة، "
            "يُشترط تفعيل عضويتك لمرة واحدة عبر الدخول للبوتات الـ 5 التابعة للشبكة:\n\n"
        )
        for i, b in enumerate(bots_list, start=1):
            gate_text += f"{i}️⃣ <b>{b['name']}</b> ({b['username']})\n"

        gate_text += (
            "\n👇 <b>اضغط على البوتات أدناه لفتحها وتفعيلها، ثم اضغط 'تحقق من التفعيل':</b>"
        )

        kb = self._build_activation_keyboard(bots_list)
        return False, gate_text, kb

    def _build_activation_keyboard(self, bots_list: list):
        """بناء لوحة الأزرار الشفافة لقائمة التفعيل"""
        try:
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(row_width=1)
            for b in bots_list:
                kb.add(InlineKeyboardButton(text=f"🚀 دخول: {b['name']}", url=b['url']))
            kb.add(InlineKeyboardButton(text="✅ تحقق من التفعيل والتشغيل الآن ⚡", callback_data="verify_network_activation"))
            return kb
        except ImportError:
            class DummyBtn:
                def __init__(self, text, url=None, callback_data=None):
                    self.text = text
                    self.url = url
                    self.callback_data = callback_data
            class DummyMarkup:
                def __init__(self):
                    self.keyboard = []
                def add(self, *btns):
                    self.keyboard.extend(btns)
            kb = DummyMarkup()
            for b in bots_list:
                kb.add(DummyBtn(text=f"🚀 دخول: {b['name']}", url=b['url']))
            kb.add(DummyBtn(text="✅ تحقق من التفعيل والتشغيل الآن ⚡", callback_data="verify_network_activation"))
            return kb

    def verify_and_activate_user(self, user_id: int) -> bool:
        """تسجيل تفعيل المستخدم بعد التحقق"""
        db = _get_db()
        if db:
            db.set_network_activated(user_id, True)
            return True
        return True

    # ── 2. الربط مع متجر التطبيقات (Store Cross-Linking) ──────────────────────
    def get_store_button(self):
        """إرجاع زر مباشر لمتجر التطبيقات"""
        store_url = self.config.get("store_bot_url", "https://t.me/BodaStoreeBot")
        try:
            from telebot.types import InlineKeyboardButton
            return InlineKeyboardButton(text="🏪 متجر التطبيقات (35+ بوت) 🌟", url=store_url)
        except ImportError:
            class DummyBtn:
                def __init__(self, text, url=None):
                    self.text = text
                    self.url = url
            return DummyBtn(text="🏪 متجر التطبيقات (35+ بوت) 🌟", url=store_url)

    def get_store_card_text(self) -> str:
        """بطاقة عرض المتجر"""
        return (
            "🏪 <b>متجر تطبيقات بودا — Boda Apps Store</b>\n"
            "────────────────────────\n"
            "استكشف أكثر من <b>35+ بوتاً مجانياً</b> يغطي كافة احتياجاتك اليومية:\n\n"
            "🛠️ <b>أدوات:</b> تحويل العملات، كود QR، اختصار الروابط، حاسبة العمر\n"
            "📥 <b>تحميل:</b> فيديوهات يوتيوب وإنستغرام وتيك توك بلا علامة\n"
            "🎨 <b>تصميم وذكاء اصطناعي:</b> صانع الملصقات، مزيل الخلفيات، محسّن الصور\n"
            "🌐 <b>ترجمة ولغات:</b> ترجمة فورية للملفات والنصوص لأكثر من 10 لغات\n"
            "💪 <b>صحة وإنتاجية:</b> حاسبة BMI، عداد السعرات، المنبه، والملاحظات\n\n"
            "👇 <b>افتح المتجر الآن وتصفح كل البوتات بضغطة زر:</b>"
        )

    # ── 3. نظام الإحالات الفيروسي والمشاركة (Viral Growth) ────────────────────
    def get_referral_link(self, bot_username: str, user_id: int) -> str:
        """توليد رابط الإحالة الخاص بالمستخدم"""
        clean_user = bot_username.lstrip("@")
        return f"https://t.me/{clean_user}?start=ref_{user_id}"

    def get_share_url(self, bot_username: str, user_id: int, bot_title: str) -> str:
        """توليد رابط مشاركة تيليجرام بنقرة واحدة (1-Click Share)"""
        ref_link = self.get_referral_link(bot_username, user_id)
        share_text = f"🔥 جرب بوت {bot_title} الأقوى على تيليجرام مجاناً وبسرعة فائقة!\nادخل الآن من الرابط:\n{ref_link}"
        return f"https://t.me/share/url?url={quote_plus(ref_link)}&text={quote_plus(share_text)}"

    def get_referral_stats(self, user_id: int, bot_name: str) -> dict:
        """إحصائيات إحالات المستخدم وحالة الـ VIP"""
        db = _get_db()
        count = db.get_referral_count(user_id, bot_name) if db else 0
        target = self.config.get("viral_rewards", {}).get("required_invites_for_vip", 3)
        is_vip = count >= target
        return {
            "invites": count,
            "target": target,
            "is_vip": is_vip,
            "remaining": max(0, target - count)
        }

    def record_referral(self, referrer_id: int, new_user_id: int, bot_name: str) -> bool:
        """تسجيل الإحالة في قاعدة البيانات"""
        db = _get_db()
        if db:
            return db.record_referral(referrer_id, new_user_id, bot_name)
        return False


_growth_engine_instance = None

def get_growth_engine() -> GrowthEngine:
    global _growth_engine_instance
    if _growth_engine_instance is None:
        _growth_engine_instance = GrowthEngine()
    return _growth_engine_instance


def attach_growth_engine(bot, bot_name: str = "bot"):
    """
    تطبيق محرك النمو والانتشار تلقائياً على أي بوت:
    1. تفعيل بوابة التفعيل الإجباري لشبكة الـ 5 بوتات
    2. معالجة روابط الدعوة والإحالات الفيروسية (start=ref_xxx)
    3. تسجيل أوامر المتجر (/store, /apps, متجر) وأوامر المشاركة (/share, /ref)
    4. ربط زر المتجر في كافة الردود
    """
    engine = get_growth_engine()
    if not engine.is_enabled():
        return

    # استخراج يوزر البوت
    try:
        me = bot.get_me()
        bot_username = me.username or "BodaBot"
    except Exception:
        bot_username = f"{bot_name}_bot"

    # 1. اعتراض معالجة الرسائل الجديدة (Activation & Referral Gate)
    if hasattr(bot, "process_new_messages"):
        orig_process = bot.process_new_messages

        def wrapped_process_new_messages(new_messages):
            filtered = []
            for msg in new_messages:
                if getattr(msg, "chat", None) and getattr(msg.chat, "type", "") == "private":
                    user_id = getattr(msg.from_user, "id", None)
                    text = getattr(msg, "text", "") or ""

                    # فحص إن كانت رسالة إحالة (/start ref_12345)
                    if text.startswith("/start ref_"):
                        try:
                            ref_id = int(text.split("ref_")[1].split()[0])
                            if user_id and ref_id != user_id:
                                engine.record_referral(ref_id, user_id, bot_name)
                        except (ValueError, IndexError):
                            pass

                    # فحص بوابة التفعيل الإجباري للشبكة
                    if user_id:
                        allowed, gate_text, markup = engine.check_network_activation(bot, user_id)
                        if not allowed:
                            try:
                                bot.send_message(msg.chat.id, gate_text, reply_markup=markup, parse_mode="HTML")
                            except Exception as e:
                                logger.error(f"خطأ إرسال بوابة التفعيل: {e}")
                            continue  # منع المعالجة حتى يتم التفعيل

                filtered.append(msg)

            if filtered:
                orig_process(filtered)

        bot.process_new_messages = wrapped_process_new_messages

    # 2. تسجيل زر التحقق من تفعيل الشبكة Callback
    if hasattr(bot, "callback_query_handler"):
        try:
            @bot.callback_query_handler(func=lambda call: getattr(call, "data", None) == "verify_network_activation")
            def _verify_callback(call):
                engine.verify_and_activate_user(call.from_user.id)
                try:
                    bot.answer_callback_query(call.id, "🎉 تم التحقق وتفعيل حسابك بنجاح في الشبكة!", show_alert=True)
                    welcome_back = (
                        "✅ <b>تهانينا! تم تفعيل اشتراكك في شبكة تطبيقات بودا بنجاح!</b>\n\n"
                        "أصبحت الآن كافة ميزات البوت وشبكتنا متاحة لك مجاناً وبلا حدود.\n"
                        "أرسل /start للبدء فوراً في الاستخدام! 🚀"
                    )
                    bot.send_message(call.message.chat.id, welcome_back, parse_mode="HTML")
                except Exception:
                    pass
        except Exception:
            pass

    # 3. تسجيل أوامر المتجر والمشاركة التلقائية
    if hasattr(bot, "message_handler"):
        try:
            @bot.message_handler(commands=["store", "apps", "متجر"])
            def _cmd_store(msg):
                card_text = engine.get_store_card_text()
                try:
                    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
                    kb = InlineKeyboardMarkup(row_width=1)
                    kb.add(engine.get_store_button())
                    bot.reply_to(msg, card_text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    bot.reply_to(msg, card_text, parse_mode="HTML")

            @bot.message_handler(commands=["ref", "share", "مشاركة", "دعوة"])
            def _cmd_share(msg):
                stats = engine.get_referral_stats(msg.from_user.id, bot_name)
                ref_link = engine.get_referral_link(bot_username, msg.from_user.id)
                share_url = engine.get_share_url(bot_username, msg.from_user.id, bot_name)

                vip_badge = "🌟 <b>عضو VIP متميز!</b>" if stats["is_vip"] else f"⏳ باقي <b>{stats['remaining']}</b> دعوات لفتح ميزات VIP!"
                reply_text = (
                    "👥 <b>نظام المشاركة والمكافآت</b>\n"
                    "────────────────────────\n"
                    f"🔗 <b>رابط الدعوة الخاص بك:</b>\n<code>{ref_link}</code>\n\n"
                    f"📊 <b>عدد الذين قمت بدعوتهم:</b> {stats['invites']} أصدقاء\n"
                    f"{vip_badge}\n\n"
                    "💡 انقر على زر المشاركة السريعة أدناه لنشر البوت في قنواتك ومجموعاتك فوراً:"
                )

                try:
                    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
                    kb = InlineKeyboardMarkup(row_width=1)
                    kb.add(
                        InlineKeyboardButton("🚀 شارك البوت مع أصدقائك الآن", url=share_url),
                        engine.get_store_button()
                    )
                    bot.reply_to(msg, reply_text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    bot.reply_to(msg, reply_text, parse_mode="HTML")

        except Exception as e:
            logger.warning(f"تعذر تسجيل أوامر النمو: {e}")

    logger.info(f"[{bot_name}] تم ربط محرك النمو والمتجر بنجاح.")
