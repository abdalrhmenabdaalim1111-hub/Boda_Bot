# -*- coding: utf-8 -*-
"""security.py — تحقق initData، هاش المستخدم، تنقية الاسم، وتحديد المعدل.

كل الدوال تستخدم مكتبة قياسية فقط (hmac/hashlib/re/time) ما عدا Telegram نفسه.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
import urllib.parse
from typing import Optional, Dict, List

# ── هاش المستخدم (لا نخزن المعرّف الخام في الإحصائيات) ──────────────────────
_SALT = (os.getenv("BODA_GATE_SALT") or "boda-namecards-v1").encode("utf-8")


def user_hash(user_id: int) -> str:
    """هاش ثابت ومجهول للمستخدم (12 hex)."""
    return hmac.new(_SALT, str(int(user_id)).encode(), hashlib.sha256).hexdigest()[:12]


def hash_to_int(value: str) -> int:
    """تحويل الهاش إلى عدد صحيح موجب لاستخدامه في جدول referrals الموجود."""
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:4], "big") & 0x7FFFFFFF


# ── تنقية الاسم ─────────────────────────────────────────────────────────────
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
_ALLOWED_RE = re.compile(r"[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\-'.,!؟?]", re.UNICODE)


def sanitize_name(text: str, max_len: int = 30) -> str:
    """إزالة الرموز الغريبة والأحرف غير المرئية وتحديد الطول."""
    s = str(text or "").translate(_INVISIBLE)
    s = s.replace("\r", " ").replace("\n", " ")
    s = _ALLOWED_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len]


# ── تحقق initData (HMAC الرسمي لتليجرام) ───────────────────────────────────
def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> Optional[Dict]:
    """يرجع قاموس المستخدم إذا كان initData صحيحاً وغير منتهٍ، وإلا None."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        data = dict(pairs)
        received = data.pop("hash", "")
        if not received:
            return None
        check_string = "\n".join(f"{k}={v}" for k, v in
                                 sorted(data.items(), key=lambda x: x[0]))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received):
            return None
        auth_ts = int(data.get("auth_date", "0") or 0)
        if auth_ts and (time.time() - auth_ts) > max_age:
            return None
        raw_user = data.get("user")
        if not raw_user:
            return None
        import json
        user = json.loads(raw_user)
        uid = int(user.get("id") or 0)
        if uid <= 0:
            return None
        return {"id": uid, "first_name": user.get("first_name", ""),
                "username": user.get("username", ""), "hash": user_hash(uid),
                "auth_date": auth_ts}
    except Exception:
        return None


# ── حد المعدل لكل مستخدم (ذاكرة خفيفة) ─────────────────────────────────────
class RateLimiter:
    """حد بسيط: N طلبات خلال WINDOW ثانية لكل هاش مستخدم."""

    def __init__(self, limit: int = 8, window: int = 60):
        self.limit = int(limit)
        self.window = int(window)
        self._hits: Dict[str, List[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        if len(hits) >= self.limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


limiter = RateLimiter()
