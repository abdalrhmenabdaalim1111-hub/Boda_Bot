"""
control_center/botconfig.py — per-bot runtime configuration.

``bots_registry.json`` remains the catalogue (decision D4); this module
stores the *runtime* configuration that the catalogue has no room for:
encrypted token, display name, category, feature flags, ad group and the
enabled/disabled switch.

The table is created by migration ``001_control_center_foundation``. Rows
are created lazily on first access, so a bot that was never touched by the
Control Center still shows up in the UI with sensible defaults.
"""

import json
from datetime import datetime

from . import crypto
from .db import get_db

FEATURE_FLAGS = (
    "ads", "growth_gate", "miniapp", "store_promo", "menu_button",
    "a_b_testing", "referrals",
)


def _now() -> str:
    return datetime.now().isoformat()


def _row_to_dict(row) -> dict:
    data = dict(row)
    features = data.get("features")
    if isinstance(features, str) and features:
        try:
            data["features"] = json.loads(features)
        except ValueError:
            data["features"] = {}
    else:
        data["features"] = {}
    data["enabled"] = bool(data.get("enabled", 1))
    data.pop("token_enc", None)   # never leaves the database
    return data


def get(bot_id: str) -> dict:
    """Return the stored configuration of a bot (never the token itself)."""
    db = get_db()
    if db is None:
        return {}
    try:
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM bot_config WHERE bot_id=?", (bot_id,)
            ).fetchone()
            if row is None:
                return {}
            return _row_to_dict(row)
    except Exception:
        return {}


def ensure(bot_id: str, display_name: str = "", category: str = "") -> dict:
    """Create the row for a bot when it does not exist yet."""
    db = get_db()
    if db is None:
        return {}
    now = _now()
    try:
        with db._get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO bot_config
                    (bot_id, display_name, category, enabled, token_env,
                     features, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (bot_id, display_name, category, crypto.env_var_name(bot_id),
                 json.dumps({}), now, now),
            )
            row = conn.execute(
                "SELECT * FROM bot_config WHERE bot_id=?", (bot_id,)
            ).fetchone()
            return _row_to_dict(row) if row else {}
    except Exception:
        return {}


def all_configs() -> dict:
    """All stored configurations, keyed by bot id."""
    db = get_db()
    if db is None:
        return {}
    try:
        with db._get_conn() as conn:
            rows = conn.execute("SELECT * FROM bot_config").fetchall()
        return {r["bot_id"]: _row_to_dict(r) for r in rows}
    except Exception:
        return {}


def update(bot_id: str, **fields) -> dict:
    """
    Update the configuration of a bot.

    Accepted keys: ``display_name``, ``category``, ``enabled``, ``features``,
    ``ad_group``, ``token``.

    A ``token`` value is encrypted before it is written (when encryption is
    available) and replaced by a masked hint. The plain token is never
    stored and never returned.
    """
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    ensure(bot_id)
    allowed = {"display_name", "category", "enabled", "features", "ad_group"}
    assignments, params = [], []

    if "display_name" in fields:
        assignments.append("display_name=?")
        params.append(str(fields["display_name"] or "")[:120])
    if "category" in fields:
        assignments.append("category=?")
        params.append(str(fields["category"] or "")[:80])
    if "enabled" in fields:
        assignments.append("enabled=?")
        params.append(1 if fields["enabled"] else 0)
    if "ad_group" in fields:
        assignments.append("ad_group=?")
        params.append(str(fields["ad_group"] or "")[:80])
    if "features" in fields:
        flags = fields["features"] or {}
        if not isinstance(flags, dict):
            flags = {}
        clean = {k: bool(v) for k, v in flags.items() if k in FEATURE_FLAGS}
        assignments.append("features=?")
        params.append(json.dumps(clean, ensure_ascii=False))

    token = fields.get("token")
    token_changed = False
    if token:
        clean_token = str(token).strip()
        if clean_token:
            box = crypto.get_secret_box()
            blob = box.encrypt_or_none(clean_token)
            if blob:
                assignments.append("token_enc=?")
                params.append(blob)
            assignments.append("token_hint=?")
            params.append(crypto.token_hint(clean_token))
            assignments.append("token_env=?")
            params.append(crypto.env_var_name(bot_id))
            token_changed = True

    assignments.append("updated_at=?")
    params.append(_now())
    params.append(bot_id)

    try:
        with db._get_conn() as conn:
            conn.execute(
                f"UPDATE bot_config SET {', '.join(assignments)} WHERE bot_id=?",
                params,
            )
        return {"ok": True, "token_stored": token_changed}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def resolve_token(bot_id: str) -> str:
    """
    Resolve the effective token of a bot.

    Order: encrypted blob in the database (when a key is configured), then
    the environment. Returns an empty string when neither is available.
    """
    db = get_db()
    if db is not None:
        try:
            with db._get_conn() as conn:
                row = conn.execute(
                    "SELECT token_enc FROM bot_config WHERE bot_id=?", (bot_id,)
                ).fetchone()
            if row and row["token_enc"]:
                box = crypto.get_secret_box()
                if box.available:
                    try:
                        return box.decrypt(row["token_enc"])
                    except Exception:
                        pass
        except Exception:
            pass
    return crypto.read_env_token(bot_id)


def token_display(bot_id: str) -> str:
    """A masked representation of the effective token, safe for the UI."""
    return crypto.mask_token(resolve_token(bot_id))


# ─────────────────────────────────────────────────────────────────────────────
# Bot Profile Fields (per-language) — Phase 1.5
# ─────────────────────────────────────────────────────────────────────────────

PROFILE_FIELDS = (
    "profile_name_ar", "profile_name_en",
    "profile_desc_ar", "profile_desc_en",
    "profile_short_ar", "profile_short_en",
    "profile_commands_ar", "profile_commands_en",
    "profile_menu_ar", "profile_menu_en",
)

# Length limits from Telegram API (validated client-side before apply)
PROFILE_LIMITS = {
    "profile_name_ar": 64, "profile_name_en": 64,
    "profile_desc_ar": 512, "profile_desc_en": 512,
    "profile_short_ar": 120, "profile_short_en": 120,
    # commands: validated separately (100 commands, each cmd 32 chars, desc 256)
    # menu: text 16 chars, url validated separately
}


def get_profile(bot_id: str) -> dict:
    """Return the stored profile fields of a bot (per-language)."""
    db = get_db()
    if db is None:
        return {}
    try:
        with db._get_conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(PROFILE_FIELDS)} FROM bot_config WHERE bot_id=?",
                (bot_id,)
            ).fetchone()
            if row is None:
                return {f: "" for f in PROFILE_FIELDS}
            return {f: row[f] or "" for f in PROFILE_FIELDS}
    except Exception:
        return {f: "" for f in PROFILE_FIELDS}


def update_profile(bot_id: str, **fields) -> dict:
    """
    Update the profile fields of a bot.
    Accepted keys: all PROFILE_FIELDS.
    """
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    ensure(bot_id)
    assignments, params = [], []

    for field in PROFILE_FIELDS:
        if field in fields:
            limit = PROFILE_LIMITS.get(field, 4096)
            val = str(fields[field] or "")[:limit]
            assignments.append(f"{field}=?")
            params.append(val)

    if not assignments:
        return {"ok": True, "updated": False}

    assignments.append("updated_at=?")
    params.append(_now())
    params.append(bot_id)

    try:
        with db._get_conn() as conn:
            conn.execute(
                f"UPDATE bot_config SET {', '.join(assignments)} WHERE bot_id=?",
                params,
            )
        return {"ok": True, "updated": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def validate_profile_limits(profile: dict) -> list:
    """Validate profile fields against Telegram API limits. Returns list of errors."""
    errors = []
    for field, limit in PROFILE_LIMITS.items():
        val = profile.get(field, "")
        if val and len(val) > limit:
            errors.append(f"{field}: {len(val)} chars exceeds limit {limit}")
    return errors
