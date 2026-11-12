"""
Bots_Folder/gate_core.py — Checker Bot Integration & Membership Verification.

Handles real-time Telegram API calls via the dedicated checker bot.

Key invariants (see docs/GATE_POLICY.md):
- **Fail-Open**: any checker-bot failure (network, rate limit, bad token) must
  let the user through — only a definitive 'left'/'kicked' status blocks.
- **Shared cache key**: membership_cache rows are keyed by ``sub_channels.id``
  (the DB id), never by the raw Telegram chat_id, so control-center and bots
  read/write the same rows and the FK constraint holds.
- **Shared hash salt**: user hashes use ``BODA_GATE_SALT`` — the same value
  control_center/config.py::gate_salt() reads — so funnel events from both
  sides match for one user.
"""

import os
import hashlib
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from .database import BodaDatabase

logger = logging.getLogger("GateCore")

DEFAULT_GATE_SALT = "boda_gate_salt_2026"


def gate_salt() -> str:
    """Same salt as control_center.config.gate_salt()."""
    return os.getenv("BODA_GATE_SALT", "").strip() or DEFAULT_GATE_SALT


def user_id_hash(user_id: int) -> str:
    """Privacy-safe user hash — identical to control_center gate._user_id_hash."""
    return hashlib.sha256(f"{user_id}{gate_salt()}".encode()).hexdigest()[:16]


class GateCore:
    def __init__(self, db: Optional[BodaDatabase] = None, bot_id: Optional[str] = None):
        self.db = db or BodaDatabase()
        self.bot_id = bot_id  # optional: enables failed_open event recording
        self.checker_token = os.getenv("BOT_GATE_CHECKER_TOKEN")
        self.api_url = f"https://api.telegram.org/bot{self.checker_token}"

    def _call(self, method: str, payload: dict) -> dict:
        """Call Telegram Bot API."""
        if not self.checker_token:
            logger.error("BOT_GATE_CHECKER_TOKEN not set")
            return {"ok": False, "error": "checker token missing"}
        try:
            resp = requests.post(f"{self.api_url}/{method}", json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            logger.error(f"Telegram API error ({method}): {e}")
            return {"ok": False, "error": str(e)}

    def get_chat_member(self, user_id: int, chat_id: Any) -> str:
        """
        Get membership status using checker bot.
        Returns: 'member', 'creator', 'administrator', 'left', 'kicked',
                 'error_not_found', 'error_not_admin' or 'error_api'.

        Anything prefixed with 'error_' triggers the fail-open rule in
        is_subscribed() — an infrastructure problem must never block a user.
        """
        res = self._call("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        if res.get("ok"):
            return res["result"].get("status", "left")

        err = res.get("description", "").lower()
        if "chat not found" in err:
            logger.warning(f"Gate channel {chat_id} not found")
            return "error_not_found"
        if ("not an administrator" in err) or ("not enough rights" in err):
            logger.warning(f"Checker bot not admin in {chat_id}")
            return "error_not_admin"

        # Generic failure (network, timeout, rate limit, malformed reply):
        # 'left' would wrongly block the user — return an error status instead.
        logger.warning(f"Checker API generic error for {chat_id}: {err or res.get('error', 'unknown')}")
        return "error_api"

    def is_subscribed(self, user_id: int, chat_id: Any,
                      channel_id: Optional[int] = None, use_cache: bool = True) -> bool:
        """
        Check if user is subscribed to a specific channel (with caching).

        ``chat_id`` is what the Telegram API receives (numeric id or
        @username); ``channel_id`` is the ``sub_channels.id`` cache key.
        """
        cache_key = channel_id if channel_id is not None else chat_id
        if use_cache:
            cached = self.get_cached_status(user_id, cache_key)
            if cached == "member":
                return True

        status = self.get_chat_member(user_id, chat_id)
        is_member = status in ("member", "creator", "administrator")

        # Fail-open rule: infrastructure errors must not block users
        if status.startswith("error"):
            logger.error(f"Gate Fail-Open triggered for user {user_id} on channel {chat_id}: {status}")
            self._record_failed_open(user_id, channel_id, status)
            return True

        # Cache: CHECK constraint only allows member/not_member/unknown
        self.set_cached_status(user_id, cache_key, "member" if is_member else "not_member")

        return is_member

    def _record_failed_open(self, user_id: int, channel_id: Optional[int], reason: str):
        """Record a failed_open gate event (analytics: excluded from drop-off)."""
        if not self.bot_id:
            return
        try:
            with self.db._get_conn() as conn:
                conn.execute(
                    "INSERT INTO gate_events (bot_id, user_id_hash, event, channel_id, metadata, created_at) "
                    "VALUES (?, ?, 'failed_open', ?, ?, ?)",
                    (self.bot_id, user_id_hash(user_id), channel_id,
                     f'{{"reason": "{reason}"}}', datetime.now().isoformat())
                )
        except Exception as e:
            logger.debug(f"failed_open record error: {e}")

    def get_cached_status(self, user_id: int, channel_id: int) -> Optional[str]:
        """Read status from membership_cache table ('member'/'not_member')."""
        try:
            with self.db._get_conn() as conn:
                row = conn.execute(
                    "SELECT status, expires_at FROM membership_cache WHERE user_id=? AND channel_id=?",
                    (user_id, channel_id)
                ).fetchone()
                if row:
                    expires = datetime.fromisoformat(row["expires_at"])
                    if datetime.now() < expires:
                        return row["status"]
        except Exception as e:
            logger.debug(f"Cache read error: {e}")
        return None

    def set_cached_status(self, user_id: int, channel_id: int, status: str, ttl_hours: int = 24):
        """Write status to membership_cache table (CHECK: member/not_member/unknown)."""
        status = {"left": "not_member", "kicked": "not_member"}.get(status, status)
        try:
            expires = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
            now = datetime.now().isoformat()
            with self.db._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO membership_cache (user_id, channel_id, status, checked_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, channel_id, status, now, expires)
                )
        except Exception as e:
            logger.error(f"Cache write error: {e}")

    def _bot_category(self, bot_id: str) -> Optional[str]:
        """Look up the bot's category from bot_config (for category-scoped profiles)."""
        try:
            with self.db._get_conn() as conn:
                row = conn.execute(
                    "SELECT category FROM bot_config WHERE bot_id=?",
                    (bot_id,)
                ).fetchone()
                return row["category"] if row else None
        except Exception as e:
            logger.debug(f"bot_config category lookup failed: {e}")
            return None

    def get_effective_profile(self, bot_id: str, category: Optional[str] = None) -> Optional[Dict]:
        """
        Fetch the effective gate profile for a bot from the DB.

        Resolution order (must match control_center/gate.py::get_effective_profile):
        1. Per-bot profile    (scope_type='bot',    scope_value=bot_id)
        2. Per-category       (scope_type='category', scope_value=category)
        3. Global default     (scope_type='global')
        """
        if category is None:
            category = self._bot_category(bot_id)
        try:
            with self.db._get_conn() as conn:
                # 1. Bot-specific
                p = conn.execute(
                    "SELECT * FROM gate_profiles WHERE scope_type='bot' AND scope_value=? AND is_active=1",
                    (bot_id,)
                ).fetchone()

                # 2. Category-specific
                if not p and category:
                    p = conn.execute(
                        "SELECT * FROM gate_profiles WHERE scope_type='category' AND scope_value=? AND is_active=1",
                        (category,)
                    ).fetchone()

                # 3. Global
                if not p:
                    p = conn.execute(
                        "SELECT * FROM gate_profiles WHERE scope_type='global' AND is_active=1 LIMIT 1"
                    ).fetchone()

                if not p:
                    return None

                profile = dict(p)
                # Only active channels participate — a disabled (soft-deleted)
                # channel must stop gating users immediately.
                slots = conn.execute(
                    "SELECT s.*, c.title, c.username, c.invite_link, c.chat_id as channel_chat_id "
                    "FROM gate_slots s JOIN sub_channels c ON s.channel_id = c.id "
                    "WHERE s.profile_id=? AND c.is_active=1 ORDER BY s.position",
                    (profile["id"],)
                ).fetchall()
                profile["slots"] = [dict(s) for s in slots]
                return profile
        except Exception as e:
            logger.error(f"Error fetching gate profile: {e}")
            return None
