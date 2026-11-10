"""
Bots_Folder/growth_engine.py — محرك النمو والانتشار وربط البوتات بالمتجر
يوفر:
1. بوابة التفعيل الإجباري في شبكة الـ 5 بوتات بنظام التعيين الذكي:
   • لكل مستخدم بوتات مختلفة (عشوائية متوازنة) لضمان انتشار كل البوتات
   • المتجر بوت ثابت دائماً ضمن الخمسة (من الإعدادات fixed_bot_ids)
2. تحقق حقيقي عبر قاعدة البيانات المشتركة — لا قنوات ولا صلاحيات أدمن
   (حل نهائي لرسالة "البوت ليس أدمن": تيليجرام لا يسمح أصلاً بالتحقق من
   الاشتراك في بوت آخر عبر get_chat_member)
3. إعادة تحقق دورية (افتراضياً كل 7 أيام) وكشف تلقائي لإلغاء الاشتراك:
   حظر المستخدم لأي بوت يُرصد عبر رفض 403 ويُستبدل البوت تلقائياً بآخر
4. نظام الإحالات الفيروسي ورابط الدعوة لكل مستخدم (Referral & Viral Growth)
5. الربط التلقائي لكل بوت مع متجر التطبيقات (Store Cross-linking)
"""
import os
import sys
import json
import time
import random
import logging
from pathlib import Path
from urllib.parse import quote_plus
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger("GrowthEngine")

DATA_DIR = Path(__file__).parent.parent / "Data"
NETWORK_CONFIG_FILE = DATA_DIR / "network_config.json"
REGISTRY_FILE = Path(__file__).parent.parent / "bots_registry.json"

DEFAULT_NETWORK_CONFIG = {
    "enabled": True,
    "require_5_bots_activation": True,
    # ── النظام الذكي ─────────────────────────────────────────────
    "assignment_size": 5,            # عدد بوتات التفعيل لكل مستخدم
    "activation_ttl_days": 7,        # إعادة التحقق كل N أيام
    "fixed_bot_ids": ["store"],      # بوتات ثابتة دائماً ضمن الخمسة
    "exclude_ids": [],               # بوتات مستبعدة من التعيين
    "balance": True,                 # توجيه المستخدمين للبوتات الأقل مستخدمين
    # ── قديم (احتياطي) ───────────────────────────────────────────
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
    """محرك النمو والانتشار وشبكة البوتات المترابطة (نظام التعيين الذكي)"""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or NETWORK_CONFIG_FILE
        self.config = self._load_config()
        self._registry_cache: Tuple[Optional[List[dict]], float] = (None, 0.0)
        # كاش في الذاكرة: user_id → timestamp انتهاء السماح (تقليل ضربات DB لكل رسالة)
        self._activation_cache: Dict[int, float] = {}

    def _load_config(self) -> dict:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        cfg = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception as e:
                logger.error(f"خطأ في قراءة ملف شبكة البوتات: {e}")
        elif not self.config_file.exists():
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_NETWORK_CONFIG, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        # دمج المفاتيح الجديدة الناقصة (توافق خلفي مع ملفات الإعدادات القديمة)
        merged = DEFAULT_NETWORK_CONFIG.copy()
        merged.update(cfg)
        return merged

    def is_enabled(self) -> bool:
        return self.config.get("enabled", True)

    # ── بول البوتات من الريجستري ────────────────────────────────────────────
    def _load_registry_pool(self) -> List[dict]:
        """قراءة البوتات المتاحة من bots_registry.json مع كاش 60 ثانية"""
        cached, ts = self._registry_cache
        now = time.time()
        if cached is not None and (now - ts) < 60:
            return cached

        pool: List[dict] = []
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            for b in data:
                username = (b.get("username") or "").lstrip("@")
                if not username:
                    continue
                pool.append({
                    "id": b.get("id"),
                    "name": f"{b.get('emoji', '🤖')} {b.get('name', b.get('id', 'بوت'))}",
                    "username": f"@{username}",
                    "url": f"https://t.me/{username}",
                })
        except Exception as e:
            logger.warning(f"تعذر قراءة الريجستري ({e})")

        if not pool:
            pool = [dict(x) for x in self.config.get("required_network_bots", [])]

        self._registry_cache = (pool, now)
        return pool

    def _bot_meta(self, bot_id: str) -> dict:
        """بيانات البوت من البول (أو كائن بسيط كـ fallback)"""
        for b in self._load_registry_pool():
            if b["id"] == bot_id:
                return b
        return {"id": bot_id, "name": bot_id, "username": "", "url": ""}

    def _metas(self, bot_ids: List[str]) -> List[dict]:
        return [self._bot_meta(b) for b in bot_ids]

    # ── التعيين الذكي المتوازن ──────────────────────────────────────────────
    def _balanced_pick(self, candidates: List[str]) -> List[str]:
        """ترتيب المرشحين: الأقل مستخدمين أولاً مع كسر تعادل عشوائي"""
        if self.config.get("balance", True):
            db = _get_db()
            if db:
                counts = db.get_bot_user_counts()
                random.shuffle(candidates)
                candidates.sort(key=lambda bid: counts.get(bid, 0))
                return candidates
        random.shuffle(candidates)
        return candidates

    def get_or_create_assignment(self, user_id: int, current_bot: str = "") -> List[str]:
        """
        البوتات الخمسة المخصصة للمستخدم:
        • تعيين محفوظ سابقاً → إعادة استخدامه (استقرار التحقق)
        • مستخدم جديد → الثوابت (المتجر) + الأقل مستخدمين عشوائياً
        """
        db = _get_db()
        if db:
            existing = db.get_network_assignments(user_id)
            if existing:
                return existing

        size = int(self.config.get("assignment_size", 5))
        exclude = set(self.config.get("exclude_ids", [])) | {current_bot}
        fixed_ids = [b for b in self.config.get("fixed_bot_ids", ["store"])
                     if b not in exclude]
        by_id = {b["id"] for b in self._load_registry_pool()}

        assignment = [b for b in fixed_ids if b in by_id]
        candidates = [b["id"] for b in self._load_registry_pool()
                      if b["id"] not in exclude and b["id"] not in assignment]
        need = size - len(assignment)
        if need > 0 and candidates:
            assignment += self._balanced_pick(candidates)[:need]

        if db:
            db.set_network_assignments(user_id, assignment)
        return assignment

    def _replace_blocked(self, user_id: int, assignment: List[str],
                         blocked: List[str], current_bot: str = "") -> List[str]:
        """استبدال البوتات المحظورة ببدائل جديدة متوازنة"""
        keep = [b for b in assignment if b not in blocked]
        exclude = (set(self.config.get("exclude_ids", [])) | {current_bot}
                   | set(keep) | set(blocked))
        candidates = [b["id"] for b in self._load_registry_pool()
                      if b["id"] not in exclude]
        need = int(self.config.get("assignment_size", 5)) - len(keep)
        if need > 0 and candidates:
            keep += self._balanced_pick(candidates)[:need]
        db = _get_db()
        if db:
            db.set_network_assignments(user_id, keep)
        return keep

    # ── 1. بوابة التفعيل الإجباري في شبكة الـ 5 بوتات ────────────────────────
    def _is_expired(self, activated_at: Optional[str]) -> bool:
        if not activated_at:
            return True
        try:
            dt = datetime_fromisoformat(activated_at)
        except Exception:
            return True
        ttl_days = float(self.config.get("activation_ttl_days", 7))
        return (datetime_now() - dt) >= timedelta_days(ttl_days)

    def _cache_allow(self, user_id: int, days: float = None):
        if days is None:
            days = float(self.config.get("activation_ttl_days", 7))
        self._activation_cache[user_id] = time.time() + days * 86400

    def check_network_activation(self, bot, user_id: int,
                                 current_bot: str = "") -> Tuple[bool, Optional[str], Optional[Any]]:
        """
        التحقق من تفعيل المستخدم في شبكة البوتات (عبر قاعدة البيانات المشتركة).
        Returns:
            (is_activated, gate_message, inline_keyboard)
        """
        if not self.is_enabled() or not self.config.get("require_5_bots_activation", True):
            return True, None, None

        # كاش الذاكرة — سماح سريع بدون ضربات DB لكل رسالة
        exp = self._activation_cache.get(user_id)
        if exp and time.time() < exp:
            return True, None, None

        db = _get_db()
        if db is None:
            # فشل مفتوح: لا نعطل البوتات بسبب غياب قاعدة البيانات
            return True, None, None

        if db.is_network_activated(user_id):
            activated_at = db.get_network_activation_time(user_id)
            if not self._is_expired(activated_at):
                try:
                    from datetime import datetime as _dt, timedelta as _td
                    remaining = (_dt.fromisoformat(activated_at)
                                 + _td(days=float(self.config.get("activation_ttl_days", 7)))
                                 - _dt.now()).total_seconds()
                    self._activation_cache[user_id] = time.time() + max(60.0, remaining)
                except Exception:
                    pass
                return True, None, None

            # ── انتهت صلاحية التفعيل → إعادة تحقق تلقائية ──
            assignment = (db.get_network_assignments(user_id)
                          or self.get_or_create_assignment(user_id, current_bot))
            blocked = [b for b in db.get_blocked_bot_ids(user_id)
                       if b in assignment and b != current_bot]
            # البوت الحالي يُحسب مشتركاً تلقائياً — المستخدم يراسله الآن أصلاً
            missing = [b for b in assignment
                       if b != current_bot and not db.has_user_started(b, user_id)]

            if not blocked and not missing:
                # ما زال مشتركاً في الجميع → تجديد صامت
                db.set_network_activated(user_id, True)
                self._cache_allow(user_id)
                return True, None, None

            # ألغى اشتراكه (حظر بوت) أو لم يكمل → بوابة + استبدال المحظورين
            if blocked:
                assignment = self._replace_blocked(user_id, assignment, blocked, current_bot)
            db.set_network_activated(user_id, False)
            self._activation_cache.pop(user_id, None)
            gate_text = self._build_gate_text(assignment, mode="recheck")
            return False, gate_text, self._build_activation_keyboard(self._metas(assignment))

        # ── مستخدم جديد غير مفعّل → تعيين شخصي جديد ──
        assignment = self.get_or_create_assignment(user_id, current_bot)
        gate_text = self._build_gate_text(assignment)
        return False, gate_text, self._build_activation_keyboard(self._metas(assignment))

    def _build_gate_text(self, bot_ids: List[str], mode: str = "new") -> str:
        """بناء نص البوابة — new: مستخدم جديد | recheck: ألغى اشتراكه | missing: ناقصون فقط"""
        metas = self._metas(bot_ids)
        if mode == "recheck":
            text = (
                "⚠️ <b>تم إيقاف تفعيلك مؤقتاً!</b>\n"
                "────────────────────────\n"
                "تحقق النظام تلقائياً ووجد أنك <b>لم تعد مشتركاً</b> في بوتات الشبكة المطلوبة.\n"
                "أعد الدخول للبوتات التالية لاستعادة كافة الميزات مجاناً:\n\n"
            )
        elif mode == "missing":
            text = (
                "⏳ <b>باقي خطوة واحدة!</b>\n"
                "────────────────────────\n"
                "ما زال عليك الدخول والاشتراك في هذه البوتات فقط:\n\n"
            )
        else:
            text = (
                "🔒 <b>تفعيل الحساب — شبكة تطبيقات بودا</b>\n"
                "────────────────────────\n"
                "مرحباً بك! للاستمتاع بخدمات هذا البوت وكافة ميزاته مجاناً، "
                "يُشترط تفعيل عضويتك لمرة واحدة عبر الدخول للبوتات الـ 5 التابعة للشبكة:\n\n"
            )
        for i, b in enumerate(metas, start=1):
            text += f"{i}️⃣ <b>{b['name']}</b> ({b['username']})\n"
        text += "\n👇 <b>افتح كل بوت واضغط Start، ثم عد واضغط 'تحقق من التفعيل':</b>"
        return text

    def _build_activation_keyboard(self, bots_list: list):
        """بناء لوحة الأزرار لقائمة التفعيل"""
        try:
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(row_width=1)
            for b in bots_list:
                kb.add(InlineKeyboardButton(text=f"🚀 دخول: {b['name']}", url=b['url']))
            kb.add(InlineKeyboardButton(text="✅ تحقق من التفعيل والتشغيل الآن ⚡",
                                        callback_data="verify_network_activation"))
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
            kb.add(DummyBtn(text="✅ تحقق من التفعيل والتشغيل الآن ⚡",
                            callback_data="verify_network_activation"))
            return kb

    def verify_activation(self, user_id: int,
                          current_bot: str = "") -> Tuple[bool, List[dict]]:
        """
        التحقق الحقيقي من الاشتراك: هل بدأ المستخدم كل بوتاته الخمسة؟
        Returns:
            (is_complete, missing_bots_meta)
        """
        assignment = self.get_or_create_assignment(user_id, current_bot)
        db = _get_db()
        if db is None:
            return True, []  # فشل مفتوح

        blocked = set(db.get_blocked_bot_ids(user_id))
        # البوت الحالي يُحسب مشتركاً تلقائياً — المستخدم يستخدمه الآن أصلاً
        missing = [bid for bid in assignment
                   if bid != current_bot
                   and (bid in blocked or not db.has_user_started(bid, user_id))]
        if not missing:
            db.set_network_activated(user_id, True)
            self._cache_allow(user_id)
            return True, []
        return False, self._metas(missing)

    # ── 2. الربط مع متجر التطبيقات (Store Cross-Linking) ──────────────────────
    def get_store_button(self):
        """إرجاع زر مباشر لمتجر التطبيقات"""
        store_url = self.config.get("store_bot_url", "https://t.me/BodaStoreeBot")
        try:
            from telebot.types import InlineKeyboardButton
            return InlineKeyboardButton(text="🏪 متجر التطبيقات (30+ بوت) 🌟", url=store_url)
        except ImportError:
            class DummyBtn:
                def __init__(self, text, url=None, callback_data=None):
                    self.text = text
                    self.url = url
                    self.callback_data = callback_data
            return DummyBtn(text="🏪 متجر التطبيقات (30+ بوت) 🌟", url=store_url)

    def get_store_card_text(self) -> str:
        """بطاقة عرض المتجر"""
        return (
            "🏪 <b>متجر تطبيقات بودا — Boda Apps Store</b>\n"
            "────────────────────────\n"
            "استكشف أكثر من <b>30+ بوتاً مجانياً</b> يغطي كافة احتياجاتك اليومية:\n\n"
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


# مساعدات تاريخ (قابلة للحقن في الاختبارات)
def datetime_now():
    from datetime import datetime
    return datetime.now()


def datetime_fromisoformat(value: str):
    from datetime import datetime
    return datetime.fromisoformat(value)


def timedelta_days(days: float):
    from datetime import timedelta
    return timedelta(days=days)


_growth_engine_instance = None


def get_growth_engine() -> GrowthEngine:
    global _growth_engine_instance
    if _growth_engine_instance is None:
        _growth_engine_instance = GrowthEngine()
    return _growth_engine_instance


def attach_growth_engine(bot, bot_name: str = "bot"):
    """
    تطبيق محرك النمو والانتشار تلقائياً على أي بوت:
    1. بوابة التفعيل الإجباري بشبكة الـ 5 بوتات (تعيين شخصي ذكي + تحقق حقيقي)
    2. معالجة روابط الدعوة والإحالات الفيروسية (start=ref_xxx)
    3. أوامر المتجر (/store, /apps, متجر) وأوامر المشاركة (/share, /ref)
    4. رصد حظر المستخدم للبوت (403) لتسجيله في قاعدة البيانات المشتركة
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

                    # بوابة التفعيل الإجباري للشبكة
                    if user_id:
                        allowed, gate_text, markup = engine.check_network_activation(
                            bot, user_id, current_bot=bot_name)
                        if not allowed:
                            # ⚠️ جوهري: تسجيل المستخدم في البوت الحالي قبل البوابة —
                            # مجرد مراسلته إثبات أنه "بدأ" البوت، وإلا فضل غير مسجل
                            # في كل البوتات للأبد ويفشل التحقق دائماً
                            try:
                                _db = _get_db()
                                if _db:
                                    _db.track_user(
                                        bot_name, user_id,
                                        getattr(msg.from_user, "full_name", "") or "",
                                        getattr(msg.from_user, "username", "") or "")
                            except Exception:
                                pass
                            try:
                                bot.send_message(msg.chat.id, gate_text,
                                                 reply_markup=markup, parse_mode="HTML")
                            except Exception as e:
                                logger.error(f"خطأ إرسال بوابة التفعيل: {e}")
                            continue  # منع المعالجة حتى يتم التفعيل

                filtered.append(msg)

            if filtered:
                orig_process(filtered)

        bot.process_new_messages = wrapped_process_new_messages

    # 2. زر التحقق من التفعيل — فحص حقيقي عبر قاعدة البيانات المشتركة
    if hasattr(bot, "callback_query_handler"):
        try:
            @bot.callback_query_handler(func=lambda call: getattr(call, "data", None) == "verify_network_activation")
            def _verify_callback(call):
                ok, missing = engine.verify_activation(call.from_user.id,
                                                       current_bot=bot_name)
                try:
                    if ok:
                        bot.answer_callback_query(
                            call.id, "🎉 تم التحقق وتفعيل حسابك بنجاح في الشبكة!",
                            show_alert=True)
                        bot.send_message(
                            call.message.chat.id,
                            "✅ <b>تهانينا! تم تفعيل اشتراكك في شبكة تطبيقات بودا بنجاح!</b>\n\n"
                            "أصبحت الآن كافة ميزات البوت وشبكتنا متاحة لك مجاناً وبلا حدود.\n"
                            "أرسل /start للبدء فوراً في الاستخدام! 🚀",
                            parse_mode="HTML")
                    else:
                        names = "، ".join(m['name'] for m in missing)
                        bot.answer_callback_query(
                            call.id,
                            f"❌ لم تشترك بعد في: {names}",
                            show_alert=True)
                        bot.send_message(
                            call.message.chat.id,
                            engine._build_gate_text([m['id'] for m in missing],
                                                     mode="missing"),
                            reply_markup=engine._build_activation_keyboard(missing),
                            parse_mode="HTML")
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

    # 4. رصد حظر المستخدم للبوت (403 Forbidden) — أساس كشف إلغاء الاشتراك
    try:
        from telebot.apihelper import ApiTelegramException
        _orig_send = bot.send_message

        def _send_tracking_block(chat_id, *args, **kwargs):
            try:
                return _orig_send(chat_id, *args, **kwargs)
            except ApiTelegramException as e:
                if getattr(e, "error_code", None) == 403 and isinstance(chat_id, int):
                    try:
                        dbt = _get_db()
                        if dbt:
                            dbt.mark_user_blocked(bot_name, chat_id)
                            logger.info(f"[{bot_name}] المستخدم {chat_id} حظر البوت — تم تسجيل الإلغاء")
                    except Exception:
                        pass
                raise

        bot.send_message = _send_tracking_block
    except Exception:
        pass

    logger.info(f"[{bot_name}] تم ربط محرك النمو والمتجر بنجاح.")
