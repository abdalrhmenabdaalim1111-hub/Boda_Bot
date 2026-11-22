# -*- coding: utf-8 -*-
"""
Bots_Folder/gate_middleware.py — بوابة الاشتراك الإجبارية (القناتان فقط).

تعتمد على gate_check.py كمصدر وحيد:
    @Stick_boda  +  @ebdo_4

تُركّب تلقائياً على كل بوت عبر unified_middleware، لذا لا تحتاج أي بوت
لتعديل كوده. زر «تحقق» يعيد الفحص فوراً (بدون كاش) ليكتشف إلغاء الاشتراك.
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional

from telebot import types

try:
    from . import gate_check
except ImportError:  # تشغيل مباشر من داخل Bots_Folder
    import gate_check

try:
    from .database import BodaDatabase
except ImportError:
    from database import BodaDatabase

logger = logging.getLogger("GateMiddleware")


class GateMiddleware:
    def __init__(self, bot, bot_id: str, db: Optional[BodaDatabase] = None):
        self.bot = bot
        self.bot_id = bot_id
        self.db = db or BodaDatabase()

    # ── الفحص ────────────────────────────────────────────────────────────
    def should_enforce(self, user_id: int) -> bool:
        """البوابة مفعّلة لكل البوتات (يمكن تعطيلها بـ BODA_SUB_GATE=0)."""
        return gate_check.gate_enabled()

    def check_and_show_gate(self, message: types.Message) -> bool:
        """
        True  = محجوب (تم إرسال رسالة الاشتراك).
        False = مسموح بالمتابعة.
        """
        user = getattr(message, "from_user", None)
        if not user or not getattr(user, "id", None):
            return False
        return self.check_user(user.id, message.chat.id,
                               (getattr(user, "language_code", "") or "ar"))

    def check_user(self, user_id: int, chat_id: int, lang: str = "ar") -> bool:
        """فحص مستخدم عبر معرّفه (يُستخدم أيضاً داخل أزرار الكولباك)."""
        if not self.should_enforce(user_id):
            return False

        missing = gate_check.get_missing_channels(user_id, use_cache=True)
        if not missing:
            return False

        self.show_gate(chat_id, missing, lang)
        self.record_event(user_id, "gate_shown")
        return True

    def show_gate(self, chat_id: int, missing: List[Dict[str, str]], lang: str = "ar"):
        """إرسال رسالة الاشتراك مع أزرار القناتين وزر التحقق."""
        if lang.startswith("ar"):
            text = gate_check.gate_text(missing)
        else:
            lines = ["⚠️ <b>Subscribe to both channels to use this bot:</b>", ""]
            for i, channel in enumerate(missing, start=1):
                lines.append(f"{i}. {channel['title']} — @{channel['username']}")
            lines += ["", "Then press <b>Verify Subscription</b> ✅"]
            text = "\n".join(lines)

        self.bot.send_message(
            chat_id,
            text,
            reply_markup=gate_check.gate_markup(missing),
            parse_mode="HTML",
        )

    # ── زر التحقق ────────────────────────────────────────────────────────
    def handle_verify_callback(self, call: types.CallbackQuery):
        """إعادة الفحص فوراً بعد ضغط «تحقق» (بدون كاش)."""
        user = getattr(call, "from_user", None)
        if not user:
            return
        user_id = user.id
        lang = (getattr(user, "language_code", "") or "ar").lower()

        gate_check.invalidate(user_id)
        missing = gate_check.get_missing_channels(user_id, use_cache=False)

        if not missing:
            msg = ("✅ تم التحقق بنجاح! يمكنك الآن استخدام البوت."
                   if lang.startswith("ar") else
                   "✅ Verified successfully! You can now use the bot.")
            try:
                self.bot.answer_callback_query(call.id, msg)
            except Exception:
                pass
            if getattr(call, "message", None):
                try:
                    self.bot.edit_message_text(
                        msg,
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                    )
                except Exception:
                    pass
            self.record_event(user_id, "verified")
            return

        if lang.startswith("ar"):
            alert = f"❌ ما زلت غير مشترك في {len(missing)} قناة. اشترك ثم اضغط تحقق مجدداً."
        else:
            alert = f"❌ You are still missing {len(missing)} channel(s). Subscribe and verify again."
        try:
            self.bot.answer_callback_query(call.id, alert, show_alert=True)
        except Exception:
            pass

    # ── تحليلات (اختيارية، لا تعطّل البوابة عند أي خطأ) ─────────────────
    def record_event(self, user_id: int, event: str):
        try:
            from .gate_core import user_id_hash
        except ImportError:
            try:
                from gate_core import user_id_hash
            except Exception:
                return
        try:
            with self.db._get_conn() as conn:
                conn.execute(
                    "INSERT INTO gate_events (bot_id, user_id_hash, event, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (self.bot_id, user_id_hash(user_id), event, datetime.now().isoformat()),
                )
        except Exception as exc:
            logger.debug("gate event record error: %s", exc)
