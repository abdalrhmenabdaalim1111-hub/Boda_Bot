"""
control_center/gate.py — Subscription Gate Manager (Phase 3-4).

Channels library, gate profiles, membership validation, stats, compliance.
"""

import csv
import io
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .db import get_db

# ─────────────────────────────────────────────────────────────────────────────
# Constants & Helpers
# ─────────────────────────────────────────────────────────────────────────────

CACHE_TTL_HOURS = 24
CHECKER_BOT_ENV = "BOT_GATE_CHECKER_TOKEN"

# Compliance: keywords that trigger honest-copy warnings
COMPLIANCE_RISK_KEYWORDS = {
    "medical": [
        "cure", "heal", "treat", "diagnose", "prescribe", "medical", "health",
        "شفاء", "علاج", "تشخيص", "وصف", "طبي", "صحة", "دواء", "مريض"
    ],
    "financial": [
        "guaranteed profit", "guaranteed return", "risk free", "get rich",
        "double your money", "guaranteed income", "ربح مضمون", "عائد مضمون",
        "بدون مخاطرة", "غني", "مضاعفة", "دخل مضمون"
    ],
    "guarantee": [
        "guaranteed", "100%", "assured", "promise", "مضمون", "مؤكد", "وعد",
        "بالتأكيد", "قطعا", "أكيد"
    ],
    "deceptive": [
        "verify you are human", "prove you're not a bot", "human verification",
        "تحقق من أنك إنسان", "أثبت أنك لست بوت", "تحقق بشري"
    ]
}


def _now() -> str:
    return datetime.now().isoformat()


def _user_id_hash(user_id: int, salt: str = None) -> str:
    """Privacy-safe hash for gate_events."""
    if salt is None:
        salt = config.gate_salt()
    return hashlib.sha256(f"{user_id}{salt}".encode()).hexdigest()[:16]


def _compliance_check(text: str) -> list:
    """Check text for risky wording. Returns list of warnings."""
    if not text:
        return []
    warnings = []
    text_lower = text.lower()
    for category, keywords in COMPLIANCE_RISK_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                warnings.append({
                    "category": category,
                    "keyword": kw,
                    "message": f"⚠️ '{kw}' قد ينتهك سياسة الاستخدام الصادق ({category})"
                })
    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# Channels Library (sub_channels table)
# ─────────────────────────────────────────────────────────────────────────────

CHANNEL_FIELDS = (
    "id", "title", "chat_type", "chat_id", "username", "invite_link",
    "language", "is_active", "checker_bot_admin", "last_validated",
    "created_at", "updated_at"
)


def _row_to_channel(row) -> dict:
    if row is None:
        return {}
    return {f: row[f] for f in CHANNEL_FIELDS}


def list_channels(active_only: bool = False) -> list:
    """List all gate channels."""
    db = get_db()
    if db is None:
        return []
    try:
        with db._get_conn() as conn:
            where = "WHERE is_active=1" if active_only else ""
            rows = conn.execute(
                f"SELECT {', '.join(CHANNEL_FIELDS)} FROM sub_channels {where} ORDER BY id"
            ).fetchall()
            return [_row_to_channel(r) for r in rows]
    except Exception:
        return []


def get_channel(channel_id: int) -> dict:
    """Get a single channel by ID."""
    db = get_db()
    if db is None:
        return {}
    try:
        with db._get_conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(CHANNEL_FIELDS)} FROM sub_channels WHERE id=?",
                (channel_id,)
            ).fetchone()
            return _row_to_channel(row)
    except Exception:
        return {}


def create_channel(**fields) -> dict:
    """Create a new gate channel."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    required = ["title", "chat_type", "chat_id"]
    for f in required:
        if not fields.get(f):
            return {"ok": False, "error": f"Missing required field: {f}"}

    now = _now()
    defaults = {
        "title": fields["title"],
        "chat_type": fields["chat_type"],
        "chat_id": int(fields["chat_id"]),
        "username": fields.get("username", ""),
        "invite_link": fields.get("invite_link", ""),
        "language": fields.get("language", "ar"),
        "is_active": 1,
        "checker_bot_admin": 1 if fields.get("checker_bot_admin") else 0,
        "last_validated": None,
    }

    cols = [f for f in CHANNEL_FIELDS if f not in ("id", "created_at", "updated_at")]
    placeholders = ", ".join(["?"] * len(cols))
    values = tuple(defaults[f] for f in cols)

    try:
        with db._get_conn() as conn:
            cur = conn.execute(
                f"INSERT INTO sub_channels ({', '.join(cols)}, created_at, updated_at) VALUES ({placeholders}, ?, ?)",
                values + (now, now)
            )
            cid = cur.lastrowid
        return {"ok": True, "channel": get_channel(cid)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def update_channel(channel_id: int, **fields) -> dict:
    """Update a gate channel."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    existing = get_channel(channel_id)
    if not existing:
        return {"ok": False, "error": "Channel not found"}

    allowed = {"title", "chat_type", "chat_id", "username", "invite_link",
               "language", "is_active", "checker_bot_admin"}
    assignments, params = [], []

    for field in allowed:
        if field in fields:
            assignments.append(f"{field}=?")
            params.append(fields[field])

    if not assignments:
        return {"ok": True, "updated": False, "channel": existing}

    assignments.append("updated_at=?")
    params.append(_now())
    params.append(channel_id)

    try:
        with db._get_conn() as conn:
            conn.execute(
                f"UPDATE sub_channels SET {', '.join(assignments)} WHERE id=?",
                params
            )
        return {"ok": True, "updated": True, "channel": get_channel(channel_id)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def delete_channel(channel_id: int) -> dict:
    """Soft delete a channel (set is_active=0)."""
    return update_channel(channel_id, is_active=0)


def validate_channel_health(channel_id: int) -> dict:
    """
    Validate channel health using checker bot:
    - getChat: channel exists and is accessible
    - getChatAdministrators: checker bot is admin
    Returns health status dict.
    """
    channel = get_channel(channel_id)
    if not channel:
        return {"ok": False, "error": "Channel not found"}

    # In real implementation, this would call the checker bot API
    # For now, return structure that dashboard expects
    return {
        "ok": True,
        "channel_id": channel_id,
        "reachable": True,
        "checker_is_admin": bool(channel.get("checker_bot_admin")),
        "member_count": None,  # would come from getChat
        "chat_type": channel.get("chat_type"),
        "username": channel.get("username"),
        "last_validated": channel.get("last_validated"),
    }


def generate_invite_link(channel_id: int, name: str = None, expire_hours: int = 24) -> dict:
    """Generate temporary invite link via checker bot."""
    channel = get_channel(channel_id)
    if not channel:
        return {"ok": False, "error": "Channel not found"}

    # In real implementation, calls createChatInviteLink via checker bot
    # For now, return mock
    invite = f"https://t.me/{channel.get('username', 'join')}/{secrets.token_urlsafe(8)}"
    return {"ok": True, "invite_link": invite, "expires_in_hours": expire_hours}


# ─────────────────────────────────────────────────────────────────────────────
# Gate Profiles & Slots
# ─────────────────────────────────────────────────────────────────────────────

PROFILE_FIELDS = ("id", "name", "scope_type", "scope_value", "mode",
                  "required_count", "soft_free_uses", "is_active",
                  "created_at", "updated_at")
SLOT_FIELDS = ("id", "profile_id", "position", "channel_id", "is_required",
               "is_pinned", "display_order", "created_at")


def _row_to_profile(row) -> dict:
    if row is None:
        return {}
    return {f: row[f] for f in PROFILE_FIELDS}


def _row_to_slot(row) -> dict:
    if row is None:
        return {}
    return {f: row[f] for f in SLOT_FIELDS}


def list_profiles() -> list:
    """List all gate profiles with their slots."""
    db = get_db()
    if db is None:
        return []
    try:
        with db._get_conn() as conn:
            profiles = conn.execute(
                f"SELECT {', '.join(PROFILE_FIELDS)} FROM gate_profiles WHERE is_active=1 ORDER BY id"
            ).fetchall()
            result = []
            for p in profiles:
                profile = _row_to_profile(p)
                slots = conn.execute(
                    f"SELECT {', '.join(SLOT_FIELDS)} FROM gate_slots WHERE profile_id=? ORDER BY position",
                    (profile["id"],)
                ).fetchall()
                profile["slots"] = [_row_to_slot(s) for s in slots]
                # Enrich with channel info
                for slot in profile["slots"]:
                    ch = get_channel(slot["channel_id"])
                    slot["channel"] = ch
                result.append(profile)
            return result
    except Exception:
        return []


def get_profile(profile_id: int) -> dict:
    """Get a single profile with slots and channel info."""
    db = get_db()
    if db is None:
        return {}
    try:
        with db._get_conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(PROFILE_FIELDS)} FROM gate_profiles WHERE id=?",
                (profile_id,)
            ).fetchone()
            if not row:
                return {}
            profile = _row_to_profile(row)
            slots = conn.execute(
                f"SELECT {', '.join(SLOT_FIELDS)} FROM gate_slots WHERE profile_id=? ORDER BY position",
                (profile_id,)
            ).fetchall()
            profile["slots"] = [_row_to_slot(s) for s in slots]
            for slot in profile["slots"]:
                slot["channel"] = get_channel(slot["channel_id"])
            return profile
    except Exception:
        return {}


def get_effective_profile(bot_id: str, category: str = None) -> dict:
    """
    Resolve the effective gate profile for a bot:
    1. Per-bot profile (scope_type='bot', scope_value=bot_id)
    2. Per-category profile (scope_type='category', scope_value=category)
    3. Global default (scope_type='global')
    Returns profile with slots enriched.
    """
    db = get_db()
    if db is None:
        return {}

    # Check per-bot
    with db._get_conn() as conn:
        row = conn.execute(
            f"SELECT {', '.join(PROFILE_FIELDS)} FROM gate_profiles "
            "WHERE scope_type='bot' AND scope_value=? AND is_active=1",
            (bot_id,)
        ).fetchone()
        if row:
            return _enrich_profile(_row_to_profile(row))

    # Check per-category
    if category:
        with db._get_conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(PROFILE_FIELDS)} FROM gate_profiles "
                "WHERE scope_type='category' AND scope_value=? AND is_active=1",
                (category,)
            ).fetchone()
            if row:
                return _enrich_profile(_row_to_profile(row))

    # Global default
    with db._get_conn() as conn:
        row = conn.execute(
            f"SELECT {', '.join(PROFILE_FIELDS)} FROM gate_profiles "
            "WHERE scope_type='global' AND is_active=1 LIMIT 1"
        ).fetchone()
        if row:
            return _enrich_profile(_row_to_profile(row))

    return {}


def _enrich_profile(profile: dict) -> dict:
    """
    Add slots with channel info to profile (effective/enforcement view).

    Slots pointing at soft-deleted (is_active=0) or missing channels are
    dropped — a disabled channel must stop gating users immediately.
    Management views (list_profiles/get_profile) keep every slot.
    """
    db = get_db()
    if db is None:
        return profile
    try:
        with db._get_conn() as conn:
            slots = conn.execute(
                f"SELECT {', '.join(SLOT_FIELDS)} FROM gate_slots WHERE profile_id=? ORDER BY position",
                (profile["id"],)
            ).fetchall()
            profile["slots"] = []
            for s in slots:
                slot = _row_to_slot(s)
                channel = get_channel(slot["channel_id"])
                if not channel or not channel.get("is_active"):
                    continue
                slot["channel"] = channel
                profile["slots"].append(slot)
            return profile
    except Exception:
        return profile


def create_profile(**fields) -> dict:
    """Create a new gate profile with slots."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    required = ["name", "scope_type"]
    for f in required:
        if not fields.get(f):
            return {"ok": False, "error": f"Missing required field: {f}"}

    now = _now()
    defaults = {
        "name": fields["name"],
        "scope_type": fields["scope_type"],
        "scope_value": fields.get("scope_value"),
        "mode": fields.get("mode", "all"),
        "required_count": fields.get("required_count", 5),
        "soft_free_uses": fields.get("soft_free_uses", 0),
        "is_active": 1,
    }

    try:
        with db._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO gate_profiles 
                   (name, scope_type, scope_value, mode, required_count, soft_free_uses, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (defaults["name"], defaults["scope_type"], defaults["scope_value"],
                 defaults["mode"], defaults["required_count"], defaults["soft_free_uses"],
                 defaults["is_active"], now, now)
            )
            pid = cur.lastrowid

            # Create slots if provided
            slots = fields.get("slots", [])
            for i, slot in enumerate(slots):
                conn.execute(
                    """INSERT INTO gate_slots 
                       (profile_id, position, channel_id, is_required, is_pinned, display_order, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (pid, i + 1, slot.get("channel_id"),
                     slot.get("is_required", 1), slot.get("is_pinned", 0),
                     slot.get("display_order", 0), now)
                )
        return {"ok": True, "profile": get_profile(pid)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def update_profile(profile_id: int, **fields) -> dict:
    """Update a gate profile and its slots."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    existing = get_profile(profile_id)
    if not existing:
        return {"ok": False, "error": "Profile not found"}

    allowed_profile = {"name", "scope_type", "scope_value", "mode",
                       "required_count", "soft_free_uses", "is_active"}
    assignments, params = [], []

    for field in allowed_profile:
        if field in fields:
            assignments.append(f"{field}=?")
            params.append(fields[field])

    if assignments:
        assignments.append("updated_at=?")
        params.append(_now())
        params.append(profile_id)
        try:
            with db._get_conn() as conn:
                conn.execute(
                    f"UPDATE gate_profiles SET {', '.join(assignments)} WHERE id=?",
                    params
                )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # Update slots if provided
    if "slots" in fields:
        slots = fields["slots"]
        try:
            with db._get_conn() as conn:
                # Delete existing slots
                conn.execute("DELETE FROM gate_slots WHERE profile_id=?", (profile_id,))
                # Insert new slots
                for i, slot in enumerate(slots):
                    conn.execute(
                        """INSERT INTO gate_slots 
                           (profile_id, position, channel_id, is_required, is_pinned, display_order, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (profile_id, i + 1, slot.get("channel_id"),
                         slot.get("is_required", 1), slot.get("is_pinned", 0),
                         slot.get("display_order", 0), _now())
                    )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    return {"ok": True, "profile": get_profile(profile_id)}


def delete_profile(profile_id: int) -> dict:
    """Soft delete a profile."""
    return update_profile(profile_id, is_active=0)


# ─────────────────────────────────────────────────────────────────────────────
# Membership Cache
# ─────────────────────────────────────────────────────────────────────────────

CACHE_FIELDS = ("user_id", "channel_id", "status", "checked_at", "expires_at")


def get_cached_membership(user_id: int, channel_id: int) -> dict:
    """Get cached membership status."""
    db = get_db()
    if db is None:
        return {}
    try:
        with db._get_conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(CACHE_FIELDS)} FROM membership_cache WHERE user_id=? AND channel_id=?",
                (user_id, channel_id)
            ).fetchone()
            if row:
                return dict(row)
            return {}
    except Exception:
        return {}


def set_cached_membership(user_id: int, channel_id: int, status: str, ttl_hours: int = CACHE_TTL_HOURS) -> dict:
    """Set cached membership status with TTL."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    # membership_cache has a CHECK(status IN ('member','not_member','unknown')) —
    # normalise Telegram's raw statuses so the write never violates it.
    status = {"left": "not_member", "kicked": "not_member"}.get(status, status)

    now = datetime.now()
    expires_at = now + timedelta(hours=ttl_hours)

    try:
        with db._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO membership_cache 
                   (user_id, channel_id, status, checked_at, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, channel_id, status, now.isoformat(), expires_at.isoformat())
            )
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def is_user_member_cached(user_id: int, channel_id: int) -> bool:
    """Check if user is member via cache (returns False if expired/missing)."""
    cached = get_cached_membership(user_id, channel_id)
    if not cached:
        return False
    if cached.get("status") != "member":
        return False
    try:
        expires = datetime.fromisoformat(cached["expires_at"])
        if datetime.now() > expires:
            return False
    except Exception:
        return False
    return True


def clear_expired_cache() -> int:
    """Remove expired cache entries. Returns count deleted."""
    db = get_db()
    if db is None:
        return 0
    try:
        with db._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM membership_cache WHERE expires_at < ?",
                (datetime.now().isoformat(),)
            )
            return cur.rowcount
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Gate Events (Audit & Funnel)
# ─────────────────────────────────────────────────────────────────────────────

EVENT_TYPES = (
    "gate_shown", "join_clicked", "verify_clicked",
    "verified", "failed_open", "skipped_admin"
)


def record_gate_event(bot_id: str, user_id: int, event: str,
                      channel_id: int = None, profile_id: int = None,
                      metadata: dict = None) -> dict:
    """Record a gate event for analytics."""
    if event not in EVENT_TYPES:
        return {"ok": False, "error": f"Invalid event type: {event}"}

    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    try:
        with db._get_conn() as conn:
            conn.execute(
                """INSERT INTO gate_events 
                   (bot_id, user_id_hash, event, channel_id, profile_id, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (bot_id, _user_id_hash(user_id), event, channel_id,
                 profile_id, json.dumps(metadata or {}), _now())
            )
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Gate Stats & Funnel Analytics
# ─────────────────────────────────────────────────────────────────────────────

def get_gate_funnel(bot_id: str = None, days: int = 30) -> dict:
    """
    Get gate funnel stats per bot or global.
    Returns: {bot_id: {shown, join_clicked, verify_clicked, verified, failed_open, drop_off_pct}}
    """
    db = get_db()
    if db is None:
        return {}

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    where = "WHERE created_at >= ?"
    params = [cutoff]
    if bot_id:
        where += " AND bot_id = ?"
        params.append(bot_id)

    try:
        with db._get_conn() as conn:
            rows = conn.execute(
                f"""SELECT bot_id, event, COUNT(*) as count
                    FROM gate_events
                    {where}
                    GROUP BY bot_id, event
                    ORDER BY bot_id""",
                params
            ).fetchall()

        result = {}
        for row in rows:
            bid = row["bot_id"]
            if bid not in result:
                result[bid] = {e: 0 for e in EVENT_TYPES}
            result[bid][row["event"]] = row["count"]

        # Calculate drop-off
        for bid, counts in result.items():
            shown = counts.get("gate_shown", 0)
            verified = counts.get("verified", 0)
            failed_open = counts.get("failed_open", 0)
            drop_off = 0
            if shown > 0:
                # clamp at 0: verified/failed_open can exceed shown when events
                # from a wider window (e.g. re-verification) overlap the bucket
                drop_off = max(0.0, round(100 * (shown - verified - failed_open) / shown, 2))
            counts["drop_off_pct"] = drop_off
            counts["total_shown"] = shown
            counts["conversion_pct"] = round(100 * verified / shown, 2) if shown > 0 else 0

        return result
    except Exception:
        return {}


def get_channel_joins(days: int = 30) -> list:
    """Get join counts per channel."""
    db = get_db()
    if db is None:
        return []

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    try:
        with db._get_conn() as conn:
            rows = conn.execute(
                """SELECT channel_id, COUNT(*) as joins
                   FROM gate_events
                   WHERE event='join_clicked' AND created_at >= ?
                   GROUP BY channel_id
                   ORDER BY joins DESC""",
                (cutoff,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_conversion_by_category(days: int = 30) -> dict:
    """Get conversion stats by bot category."""
    # This would need to join with bot_config or registry
    # Simplified for now
    return {}


def export_gate_events_csv(bot_id: str = None, days: int = 30) -> str:
    """Export gate events as CSV."""
    db = get_db()
    if db is None:
        return ""

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    where = "WHERE created_at >= ?"
    params = [cutoff]
    if bot_id:
        where += " AND bot_id = ?"
        params.append(bot_id)

    try:
        with db._get_conn() as conn:
            rows = conn.execute(
                f"""SELECT bot_id, user_id_hash, event, channel_id, profile_id, metadata, created_at
                    FROM gate_events
                    {where}
                    ORDER BY created_at""",
                params
            ).fetchall()

        lines = ["bot_id,user_id_hash,event,channel_id,profile_id,metadata,created_at"]
        # csv module: metadata is JSON and freely contains commas/quotes/newlines
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(lines[0].split(","))
        for r in rows:
            writer.writerow([
                r["bot_id"], r["user_id_hash"], r["event"],
                r["channel_id"] or "", r["profile_id"] or "",
                r["metadata"] or "", r["created_at"],
            ])
        return buf.getvalue()
    except Exception:
        return ""


def export_gate_events_json(bot_id: str = None, days: int = 30) -> str:
    """Export gate events as JSON."""
    db = get_db()
    if db is None:
        return "[]"

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    where = "WHERE created_at >= ?"
    params = [cutoff]
    if bot_id:
        where += " AND bot_id = ?"
        params.append(bot_id)

    try:
        with db._get_conn() as conn:
            rows = conn.execute(
                f"""SELECT bot_id, user_id_hash, event, channel_id, profile_id, metadata, created_at
                    FROM gate_events
                    {where}
                    ORDER BY created_at""",
                params
            ).fetchall()

        data = [dict(r) for r in rows]
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        return "[]"


# ─────────────────────────────────────────────────────────────────────────────
# Gate Health & Alerts
# ─────────────────────────────────────────────────────────────────────────────

def get_gate_health() -> dict:
    """Overall gate system health."""
    channels = list_channels(active_only=True)
    healthy = 0
    issues = []

    for ch in channels:
        health = validate_channel_health(ch["id"])
        if health.get("reachable") and health.get("checker_is_admin"):
            healthy += 1
        else:
            issues.append({
                "channel_id": ch["id"],
                "title": ch["title"],
                "reachable": health.get("reachable"),
                "checker_is_admin": health.get("checker_is_admin"),
            })

    return {
        "total_channels": len(channels),
        "healthy_channels": healthy,
        "issues": issues,
        "status": "healthy" if len(issues) == 0 else ("degraded" if healthy > 0 else "critical"),
        "checked_at": _now(),
    }


def check_and_alert_channels() -> dict:
    """Background job: check all channels, log errors, return alerts."""
    alerts = []
    for ch in list_channels(active_only=True):
        health = validate_channel_health(ch["id"])
        if not health.get("reachable"):
            alerts.append({
                "type": "channel_unreachable",
                "channel_id": ch["id"],
                "title": ch["title"],
                "message": f"Channel '{ch['title']}' is unreachable via checker bot"
            })
        elif not health.get("checker_is_admin"):
            alerts.append({
                "type": "checker_not_admin",
                "channel_id": ch["id"],
                "title": ch["title"],
                "message": f"Checker bot is not admin in '{ch['title']}'"
            })

    # In real implementation, send alerts to admin chat here
    return {"alerts": alerts, "checked_at": _now()}