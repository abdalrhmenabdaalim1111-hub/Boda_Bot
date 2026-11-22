# =============================================================================
#  Bots_Folder/unified_middleware.py — الطبقة الموحدة لكل البوتات (v1.0)
#
#  تُركَّب تلقائياً عبر bot_base.start_polling / start_bot على أي بوت فور تشغيله
#  وتوفر WITHOUT تعديل كود البوتات نفسها:
#
#    1. 📊 تتبع كل مستخدم في قاعدة البيانات (users + usage_stats)
#    2. 📱 بطاقة "افتح التطبيق" — تُرسل مرة واحدة لكل مستخدم عند /start
#    3. 🎛️ زر قائمة التطبيق (Menu Button) يفتح تطبيق الويب الخاص بالبوت
#
#  المصدر الحقيقي لعنوان التطبيقات: متغير البيئة MINIAPPS_BASE_URL في .env
#  مثال:  MINIAPPS_BASE_URL=https://myuser.github.io/boda-bots
#  إذا كان فارغاً → تُعطَّل مزايا الويب بأمان دون أي خطأ.
# =============================================================================
import os
import json
import re
from pathlib import Path
import time
import threading

from telebot.handler_backends import BaseMiddleware
from telebot.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                           MenuButtonWebApp, WebAppInfo, BotCommand)

from bot_base import get_logger, track_user

# ── عنوان قاعدة التطبيقات ─────────────────────────────────────────────────────
MINIAPPS_BASE_URL = os.getenv("MINIAPPS_BASE_URL", "").strip().rstrip("/")


def get_miniapps_url(bot_id: str) -> str:
    """رابط تطبيق بوت معيّن (أو نص فارغ إن لم تُضبط القاعدة)"""
    if not MINIAPPS_BASE_URL:
        return ""
    return f"{MINIAPPS_BASE_URL}/{bot_id}/"


def webapp_keyboard(bot_id: str) -> InlineKeyboardMarkup:
    """لوحة أزرار التطبيق: افتح التطبيق + الموقع بالمتصفح + راعي + المتجر"""
    kb = InlineKeyboardMarkup(row_width=1)
    url = get_miniapps_url(bot_id)
    if url:
        kb.add(InlineKeyboardButton(
            "📱  افتح التطبيق",
            web_app=WebAppInfo(url=url)))
        # رابط الموقع مباشرة بالمتصفح — يعمل دائماً حتى قبل توثيق النطاق من BotFather
        kb.add(InlineKeyboardButton(
            "🌐  الموقع بالمتصفح",
            url=url))
    # زر الراعي Monetag (إن ضُبطت شفرة) — يمر عبر تتبع النقرات في بوت المتجر
    try:
        from ad_manager import get_ad_manager
        sponsor_url = get_ad_manager().build_ad_click_url(bot_id)
        if sponsor_url:
            kb.add(InlineKeyboardButton("🔥  عرض حصري", url=sponsor_url))
    except Exception:
        pass
    # زر مشاركة البوت
    try:
        entry = _load_registry_entry(bot_id)
        username = (entry.get("username") or "").lstrip("@") or bot_id
        share_text = entry.get("short_desc") or entry.get("name") or bot_id
        from urllib.parse import quote_plus
        kb.add(InlineKeyboardButton(
            "📤  شارك البوت",
            url=f"https://t.me/share/url?url=https://t.me/{username}&text={quote_plus(share_text)}"))
    except Exception:
        pass
    kb.add(InlineKeyboardButton("🏪  متجر تطبيقات بودة",
                                url="https://t.me/BodaStoreeBot"))
    return kb


def setup_menu_button(bot, bot_id: str):
    """ضبط زر القائمة (☰ بجانل مربع الكتابة) ليفتح تطبيق الويب مباشرة"""
    url = get_miniapps_url(bot_id)
    if not url:
        return False
    try:
        bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="📱 افتح التطبيق",
                                         web_app=WebAppInfo(url=url)))
        return True
    except Exception:
        # بعض البوتات قد تفشل (اتصال/صلاحيات) — لا نعطّل التشغيل
        return False


def _load_registry_entry(bot_name: str) -> dict:
    """قراءة إدخال البوت من bots_registry.json (best-effort)."""
    try:
        path = Path(__file__).resolve().parent.parent / "bots_registry.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data:
            if item.get("id") == bot_name:
                return item
    except Exception:
        pass
    return {}


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text[:limit] if len(text) > limit else text


def apply_bot_profile(bot, bot_name: str) -> None:
    """ضبط وصف/أوامر البوت في تيليجرام من الريجستري (best-effort)."""
    entry = _load_registry_entry(bot_name)
    if not entry:
        return
    try:
        desc = _clip(entry.get("description", ""), 512)
        short = _clip(entry.get("short_desc", ""), 120)
        if desc:
            bot.set_my_description(description=desc)
        if short:
            bot.set_my_short_description(short_description=short)
        commands = [
            BotCommand("start", "بدء الاستخدام"),
            BotCommand("app", "فتح التطبيق المصغّر"),
            BotCommand("store", "متجر تطبيقات بودة"),
        ]
        bot.set_my_commands(commands)
    except Exception as e:
        get_logger(bot_name).debug(f"bot profile apply: {e}")


try:
    from .gate_middleware import GateMiddleware
except ImportError:
    from gate_middleware import GateMiddleware


# ── البرمجية الوسيطة ──────────────────────────────────────────────────────────
class UnifiedBotMiddleware(BaseMiddleware):
    """
    تعمل قبل معالجات الرسائل لكل تحديث:
      • تتبع المستخدمين الخاصين في قاعدة البيانات
      • إرسال بطاقة التطبيق مرة واحدة لكل مستخدم عند /start
      • فحص بوابة الاشتراك (Gate)
    """
    def __init__(self, bot, bot_name: str):
        self.bot = bot
        self.bot_name = bot_name
        self.update_types = ["message", "callback_query"]
        self._promo_sent = set()
        self._tracked = {}
        self._track_lock = threading.Lock()
        self._lock = threading.Lock()
        self.log = get_logger(bot_name)
        # Gate middleware
        self.gate = GateMiddleware(bot, bot_name)

    def pre_process(self, message, data: dict):
        """تُستدعى قبل أي معالج رسائل في البوت"""
        # Handle callback queries for gate verification + enforce gate
        if message.content_type == "callback_query":
            if (message.data or "").startswith("gate_verify"):
                self.gate.handle_verify_callback(message)
                from telebot.handler_backends import CancelMiddleware
                raise CancelMiddleware("gate verify handled")
            user = getattr(message, "from_user", None)
            if user and getattr(user, "id", None):
                chat = getattr(message, "message", None)
                chat_id = getattr(getattr(chat, "chat", None), "id", None) or user.id
                lang = (getattr(user, "language_code", "") or "ar").lower()
                if self.gate.check_user(user.id, chat_id, lang, use_cache=False):
                    try:
                        self.bot.answer_callback_query(
                            message.id,
                            "🔐 اشترك في القناتين ثم اضغط «تحقق».",
                            show_alert=True,
                        )
                    except Exception:
                        pass
                    from telebot.handler_backends import CancelMiddleware
                    raise CancelMiddleware("Subscription Gate active")
            return

        if data is not None:
            data["_t0"] = time.time()

        try:
            user = getattr(message, "from_user", None)
            if not user or not getattr(user, "id", None):
                return

            chat_type = getattr(getattr(message, "chat", None), "type", "")
            is_private = chat_type == "private"

            # 1) تتبع المستخدمين وترقيتهم (المحادثات الخاصة فقط — إحصائيات نظيفة)
            if is_private:
                # أولاً: فحص بوابة الاشتراك الإجباري
                # فحص فوري بدون كاش → يتعقب إلغاء الاشتراك تلقائياً عند الاستخدام
                if self.gate.check_and_show_gate(message, use_cache=False):
                    from telebot.handler_backends import CancelMiddleware
                    raise CancelMiddleware("Subscription Gate active")

                # أوامر موحّدة: /app و /store (لا تعتمد على كود البوت)
                text = (getattr(message, "text", "") or "").strip()
                cmd = text.split()[0].lower() if text else ""
                if cmd in ("/app", "/apps", "/store"):
                    if cmd == "/store":
                        kb = InlineKeyboardMarkup()
                        kb.add(InlineKeyboardButton(
                            "🏪  متجر تطبيقات بودة", url="https://t.me/BodaStoreeBot"))
                        self.bot.send_message(
                            message.chat.id,
                            "🏪 <b>متجر تطبيقات بودة</b>\n"
                            "33 بوتاً وتطبيقاً في 7 فئات — بدون إعلانات.",
                            parse_mode="HTML", reply_markup=kb)
                    else:
                        url = get_miniapps_url(self.bot_name)
                        if url:
                            self.bot.send_message(
                                message.chat.id,
                                "📱 <b>التطبيق المصغّر</b> لهذا البوت:",
                                parse_mode="HTML",
                                reply_markup=webapp_keyboard(self.bot_name))
                        else:
                            self.bot.send_message(
                                message.chat.id,
                                "📱 التطبيق المصغّر قيد التفعيل. "
                                "استخدم المتجر: https://t.me/BodaStoreeBot")
                    from telebot.handler_backends import CancelMiddleware
                    raise CancelMiddleware("global command handled")
                if cmd in ("/about", "/intro"):
                    entry = _load_registry_entry(self.bot_name)
                    name = entry.get("name", self.bot_name)
                    desc = (entry.get("short_desc") or entry.get("description") or "").strip()
                    features = entry.get("features") or []
                    feat_text = "\n".join(f"• {f}" for f in features[:3])
                    parts = [
                        f"ℹ️ <b>{name}</b>",
                        desc or "أداة ذكية من منظومة بودة.",
                    ]
                    if feat_text:
                        parts.append("المميزات:\n" + feat_text)
                    parts.append("📱 جرّب النسخة التفاعلية: " + (get_miniapps_url(self.bot_name) or "https://t.me/BodaStoreeBot"))
                    parts.append(
                        "🔐 <b>مميزات نظام التحقق:</b>\n"
                        "• اشتراك إجباري: @Stick_boda + @ebdo_4\n"
                        "• فحص تلقائي فوري (بدون كاش) عند الاستخدام\n"
                        "• العمل يتوقف حتى التحقق\n"
                        "• زر «تحقق» يعيد الفحص فوراً")
                    self.bot.send_message(
                        message.chat.id, "\n\n".join(parts),
                        parse_mode="HTML",
                        reply_markup=webapp_keyboard(self.bot_name))
                    from telebot.handler_backends import CancelMiddleware
                    raise CancelMiddleware("global about handled")
                if cmd == "/verify":
                    # إعادة فحص فوري (مميز لنظام التحقق)
                    user = getattr(message, "from_user", None)
                    if user and getattr(user, "id", None):
                        chat_id = getattr(message, "chat", None)
                        chat_id = getattr(chat_id, "id", None) or user.id
                        lang = (getattr(user, "language_code", "") or "ar").lower()
                        missing = gate_check.get_missing_channels(user.id, use_cache=False)
                        if not missing:
                            self.bot.send_message(
                                chat_id,
                                "✅ <b>أنت مشترك في القناتين ✓</b>\n"
                                "اشترك في @Stick_boda + @ebdo_4، ثم استمر في استخدام البوت.",
                                parse_mode="HTML")
                        else:
                            gate_check.invalidate(user.id)
                            missing = gate_check.get_missing_channels(user.id, use_cache=False)
                            self.gate.show_gate(chat_id, missing, lang)
                    from telebot.handler_backends import CancelMiddleware
                    raise CancelMiddleware("verify handled")

                _now = time.time()
                with self._track_lock:
                    _last = self._tracked.get(user.id, 0)
                    _do_track = (_now - _last) >= 60
                    if _do_track:
                        self._tracked[user.id] = _now
                if _do_track:
                    res = track_user(self.bot_name, user.id,
                                 f"{getattr(user, 'first_name', '') or ''} "
                                 f"{getattr(user, 'last_name', '') or ''}".strip(),
                                 getattr(user, "username", "") or "")
                else:
                    res = None
                if res and isinstance(res, dict) and res.get("leveled_up"):
                    self.send_level_up_notification(user.id, res.get("new_level", ""))

            # 2) بطاقة التطبيق عند /start (مرة واحدة لكل مستخدم)
            text = (getattr(message, "text", "") or "").strip()
            if is_private and text.split() and text.split()[0].lower() in ("/start", "/start@app"):
                app_url = get_miniapps_url(self.bot_name)
                if app_url:
                    with self._lock:
                        first_time = user.id not in self._promo_sent
                        self._promo_sent.add(user.id)
                    if first_time:
                        # مؤشر خيط خفي — لا يمنع إغلاق البرنامج
                        threading.Timer(
                            2.0, self._send_promo, args=(user.id,)
                        ).start()

        except Exception as e:
            from telebot.handler_backends import CancelMiddleware
            if isinstance(e, CancelMiddleware):
                raise
            if "Subscription Gate active" not in str(e):
                self.log.debug(f"middleware: {e}")
            else:
                raise # Re-raise CancelMiddleware to actually cancel

    def send_level_up_notification(self, user_id: int, level_name: str):
        """إرسال بطاقة تهنئة احترافية عند ارتقاء المستوى."""
        try:
            text = (
                "🎊 <b>تهانينا! لقد ارتقيت لمستوى جديد</b> 🎊\n"
                "────────────────────────\n\n"
                "🏆 رتبتك الحالية: <b>" + str(level_name) + "</b>\n\n"
                "شكراً لاستخدامك خدمات منظومة بودة الموحدة. استمر في استخدام البوتات لرفع نقاطك وفتح ميزات حصرية قريباً! ✨"
            )
            
            kb = InlineKeyboardMarkup()
            share_text = f"🔥 لقد وصلت لرتبة {level_name} في منظومة بودة للبوتات! جربها الآن واكتشف رتبتك 🚀"
            share_url = "https://t.me/BodaStoreeBot"
            
            kb.add(InlineKeyboardButton("📤 شارك الإنجاز", 
                url=f"https://t.me/share/url?url={share_url}&text={share_text}"))
            
            self.bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            self.log.debug(f"level_up notification error: {e}")

    def post_process(self, message, data: dict, exception):
        """تُستدعى بعد انتهاء معالجة التحديث لالتقاط الأخطاء وتتبع الأداء تلقائياً."""
        try:
            if exception is not None:
                user = getattr(message, "from_user", None)
                uid = getattr(user, "id", None) if user else None
                text = getattr(message, "text", "") or ""
                from error_tracker import track_exception
                track_exception(self.bot_name, exception, user_id=uid, context=text)

            # قياس زمن الاستجابة (Latency)
            if data and "_t0" in data:
                latency_ms = (time.time() - data["_t0"]) * 1000
                if latency_ms > 3000:
                    self.log.warning(f"⚠️ استجابة بطيئة في {self.bot_name}: {latency_ms:.0f}ms")
        except Exception as e:
            self.log.debug(f"post_process error: {e}")

    def _send_promo(self, chat_id: int):
        """إرسال بطاقة التطبيق المصغّر"""
        try:
            entry = _load_registry_entry(self.bot_name)
            name = entry.get("name", self.bot_name)
            desc = (entry.get("short_desc") or entry.get("description") or "").strip()
            features = entry.get("features") or []
            feat_text = "\n".join(f"• {f}" for f in features[:3])
            parts = [f"✨ <b>{name}</b>"]
            if desc:
                parts.append(desc)
            if feat_text:
                parts.append(feat_text)
            parts.append("جرّب النسخة التفاعلية داخل تيليجرام 👇")
            parts.append("🔐 مميزات الاشتراك: @Stick_boda + @ebdo_4 — زر «تحقق» يعيد الفحص فوراً (/verify)")
            text = "\n\n".join(parts)
            self.bot.send_message(
                chat_id, text, parse_mode="HTML",
                reply_markup=webapp_keyboard(self.bot_name))
        except Exception:
            pass  # المستخدم قد يكون حظر البوت — نتجاهل بهدوء


def install_unified_layer(bot, bot_name: str):
    """
    تركيب الطبقة الموحدة على بوت قيد التشغيل:
    زر القائمة + البرمجية الوسيطة.
    تُستدعى من bot_base.start_polling/start_webhook تلقائياً.
    تعمل حتى لو أُنشئ البوت بدون use_class_middlewares (تفعيل ديناميكي).
    """
    log = get_logger(bot_name)

    apply_bot_profile(bot, bot_name)
    log.info("📝 وصف/أوامر البوت محدّثة في تيليجرام")

    menu_ok = setup_menu_button(bot, bot_name)
    if menu_ok:
        log.info("📱 زر القائمة ← التطبيق المصغّر مفعّل")

    try:
        # تفعيل الكلاس-ميدل وير ديناميكياً (البوتات أُنشئت قبل وجوده)
        if not getattr(bot, "use_class_middlewares", False):
            bot.use_class_middlewares = True
            if bot.middlewares is None:
                bot.middlewares = []
        bot.setup_middleware(UnifiedBotMiddleware(bot, bot_name))
        if get_miniapps_url(bot_name):
            log.info("📊 الطبقة الموحدة: تتبع المستخدمين + بطاقة التطبيق مفعّلة")
        else:
            log.info("📊 الطبقة الموحدة: تتبع المستخدمين مفعّل (بدون تطبيق ويب)")
    except Exception as e:
        log.debug(f"middleware install: {e}")
