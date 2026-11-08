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
import re
import threading

from telebot.handler_backends import BaseMiddleware
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, MenuButtonWebApp, WebAppInfo

from bot_base import get_logger, track_user

# ── عنوان قاعدة التطبيقات ─────────────────────────────────────────────────────
MINIAPPS_BASE_URL = os.getenv("MINIAPPS_BASE_URL", "").strip().rstrip("/")


def get_miniapps_url(bot_id: str) -> str:
    """رابط تطبيق بوت معيّن (أو نص فارغ إن لم تُضبط القاعدة)"""
    if not MINIAPPS_BASE_URL:
        return ""
    return f"{MINIAPPS_BASE_URL}/{bot_id}/"


def webapp_keyboard(bot_id: str) -> InlineKeyboardMarkup:
    """لوحة أزرار التطبيق: افتح التطبيق + المتجر + مشاركة"""
    kb = InlineKeyboardMarkup(row_width=1)
    url = get_miniapps_url(bot_id)
    if url:
        kb.add(InlineKeyboardButton(
            "📱  افتح التطبيق",
            web_app=WebAppInfo(url=url)))
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


# ── البرمجية الوسيطة ──────────────────────────────────────────────────────────
class UnifiedBotMiddleware(BaseMiddleware):
    """
    تعمل قبل معالجات الرسائل لكل تحديث:
      • تتبع المستخدمين الخاصين في قاعدة البيانات
      • إرسال بطاقة التطبيق مرة واحدة لكل مستخدم عند /start
    """
    def __init__(self, bot, bot_name: str):
        self.bot = bot
        self.bot_name = bot_name
        self.update_types = ["message"]
        self._promo_sent = set()          # مستخدمو /start الذين استلموا البطاقة
        self._lock = threading.Lock()
        self.log = get_logger(bot_name)

    def pre_process(self, message, data: dict):
        """تُستدعى قبل أي معالج رسائل في البوت"""
        try:
            user = getattr(message, "from_user", None)
            if not user or not getattr(user, "id", None):
                return

            chat_type = getattr(getattr(message, "chat", None), "type", "")
            is_private = chat_type == "private"

            # 1) تتبع المستخدمين (المحادثات الخاصة فقط — إحصائيات نظيفة)
            if is_private:
                track_user(self.bot_name, user.id,
                           f"{getattr(user, 'first_name', '') or ''} "
                           f"{getattr(user, 'last_name', '') or ''}".strip(),
                           getattr(user, "username", "") or "")

            # 2) بطاقة التطبيق عند /start (مرة واحدة لكل مستخدم)
            text = (getattr(message, "text", "") or "").strip()
            if is_private and text.split()[0].lower() in ("/start", "/start@app"):
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
            self.log.debug(f"middleware: {e}")

    def post_process(self, message, data: dict, exception):
        """مطلوب من الواجهة — لا شيء بعد المعالجة"""
        pass

    def _send_promo(self, chat_id: int):
        """إرسال بطاقة التطبيق المصغّر"""
        try:
            self.bot.send_message(
                chat_id,
                "✨ <b>جرّب النسخة التفاعلية من هذا البوت!</b>\n"
                "واجهة عصرية تعمل داخل تيليجرام 👇",
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
