"""
Bots_Folder/gate_middleware.py — Subscription Gate Enforcement.

Middleware-like logic to be called by bots to check membership
and show the subscription gate message if needed.

Notes:
- Events written here MUST be one of the gate_events CHECK values:
  gate_shown / join_clicked / verify_clicked / verified / failed_open / skipped_admin.
- User hashing goes through gate_core.user_id_hash so both sides of the
  system produce identical hashes (shared BODA_GATE_SALT).
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict

from telebot import TeleBot, types

from .gate_core import GateCore, user_id_hash
from .database import BodaDatabase

logger = logging.getLogger("GateMiddleware")


class GateMiddleware:
    def __init__(self, bot: TeleBot, bot_id: str, db: Optional[BodaDatabase] = None):
        self.bot = bot
        self.bot_id = bot_id
        self.db = db or BodaDatabase()
        self.core = GateCore(self.db, bot_id=bot_id)

    def should_enforce(self, user_id: int) -> bool:
        """Check if gate is enabled for this bot and user needs to see it."""
        # Check bot_config for growth_gate feature flag
        try:
            with self.db._get_conn() as conn:
                row = conn.execute(
                    "SELECT features FROM bot_config WHERE bot_id=?",
                    (self.bot_id,)
                ).fetchone()
                if not row:
                    return False
                features = json.loads(row["features"] or "{}")
                if not features.get("growth_gate"):
                    return False
        except Exception:
            return False

        # Soft-gate logic: if profile mode is 'soft', check free uses
        # (This is a Phase 4+ enhancement)

        return True

    def check_and_show_gate(self, message: types.Message) -> bool:
        """
        Check if user is subscribed to required channels.
        If not, show gate message and return True (indicating blocked).
        If yes, return False (indicating allowed).
        """
        user_id = message.from_user.id
        if not self.should_enforce(user_id):
            return False

        profile = self.core.get_effective_profile(self.bot_id)
        if not profile:
            return False

        missing_slots = []
        for slot in profile.get("slots", []):
            if slot.get("is_required"):
                # chat target for the API, DB id for the cache key
                cid = slot.get("channel_chat_id") or slot.get("username")
                if not cid:
                    continue

                if not self.core.is_subscribed(user_id, cid, channel_id=slot.get("channel_id")):
                    missing_slots.append(slot)

        if not missing_slots:
            return False

        # Show gate message
        self.show_gate(message, profile, missing_slots)

        # Record event
        self.record_event(user_id, "gate_shown", profile["id"])

        return True

    @staticmethod
    def _slot_url(slot: Dict) -> Optional[str]:
        """Invite link or public username URL for a slot (None when unusable)."""
        invite = (slot.get("invite_link") or "").strip()
        if invite:
            return invite
        username = (slot.get("username") or "").strip().lstrip("@")
        if username:
            return f"https://t.me/{username}"
        return None

    def show_gate(self, message: types.Message, profile: Dict, missing: List[Dict]):
        """Send the subscription gate message with buttons."""
        # Text based on language (detect from message)
        lang = (message.from_user.language_code or "ar").lower()

        if lang.startswith("ar"):
            # Telegram legacy Markdown bold is *text* — ** renders literally
            text = "⚠️ *يجب عليك الاشتراك في القنوات التالية لاستخدام هذا البوت:*\n\n"
            for i, slot in enumerate(missing, start=1):
                text += f"{i}. {slot.get('title') or 'قناة'}\n"
            text += "\nبعد الاشتراك، اضغط على زر *التحقق* بالأسفل."
            verify_btn_text = "✅ تحقق من الاشتراك"
        else:
            text = "⚠️ *You must subscribe to the following channels to use this bot:*\n\n"
            for i, slot in enumerate(missing, start=1):
                text += f"{i}. {slot.get('title') or 'Channel'}\n"
            text += "\nAfter subscribing, click the *Verify* button below."
            verify_btn_text = "✅ Verify Subscription"

        markup = types.InlineKeyboardMarkup(row_width=1)
        for slot in missing:
            url = self._slot_url(slot)
            if not url:
                # private channel with no invite link yet — nothing to open
                logger.warning(
                    "Gate slot '%s' (id=%s) has neither invite_link nor username",
                    slot.get("title"), slot.get("channel_id"))
                continue
            markup.add(types.InlineKeyboardButton(f"📺 {slot.get('title') or 'قناة'}", url=url))

        # Add verify button (callback)
        markup.add(types.InlineKeyboardButton(verify_btn_text, callback_data=f"gate_verify:{profile['id']}"))

        self.bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

    def handle_verify_callback(self, call: types.CallbackQuery):
        """Handle the 'Verify' button click."""
        user_id = call.from_user.id
        try:
            profile_id = int(call.data.split(":")[1])
        except (IndexError, ValueError):
            self.bot.answer_callback_query(call.id, "❌ بيانات غير صالحة")
            return

        # Fetch profile
        profile = self.core.get_effective_profile(self.bot_id)
        if not profile or profile["id"] != profile_id:
            self.bot.answer_callback_query(call.id, "❌ خطأ في البروفايل")
            return

        # The verify attempt itself is a funnel step (always valid taxonomy)
        self.record_event(user_id, "verify_clicked", profile_id)

        missing = []
        for slot in profile.get("slots", []):
            if slot.get("is_required"):
                cid = slot.get("channel_chat_id") or slot.get("username")
                if not cid:
                    continue
                # Force skip cache to re-verify
                if not self.core.is_subscribed(user_id, cid, channel_id=slot.get("channel_id"), use_cache=False):
                    missing.append(slot)

        lang = (call.from_user.language_code or "ar").lower()
        if not missing:
            # Success!
            msg = "✅ تم التحقق بنجاح! يمكنك الآن استخدام البوت." if lang.startswith("ar") else "✅ Verified successfully! You can now use the bot."
            self.bot.answer_callback_query(call.id, msg)
            if call.message:
                self.bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id)
            self.record_event(user_id, "verified", profile_id)
        else:
            # Still missing
            msg = f"❌ ما زال هناك {len(missing)} قناة لم تشترك بها بعد!" if lang.startswith("ar") else f"❌ You are still missing {len(missing)} channels!"
            self.bot.answer_callback_query(call.id, msg, show_alert=True)

    def record_event(self, user_id: int, event: str, profile_id: int):
        """Record gate event for analytics (shared salt with control_center)."""
        try:
            now = datetime.now().isoformat()

            with self.db._get_conn() as conn:
                conn.execute(
                    "INSERT INTO gate_events (bot_id, user_id_hash, event, profile_id, created_at) VALUES (?, ?, ?, ?, ?)",
                    (self.bot_id, user_id_hash(user_id), event, profile_id, now)
                )
        except Exception as e:
            logger.debug(f"Event record error: {e}")
