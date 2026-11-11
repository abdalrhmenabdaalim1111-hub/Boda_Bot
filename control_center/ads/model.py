"""
control_center/ads/model.py — ad library CRUD.

The SQLite tables are the source of truth (Phase A1). Legacy JSON mirrors
(``Data/ads_config.json``, ``Data/monetag_config.json``) are kept in sync by
``control_center.ads.sync`` so the existing readers (ad_manager, watcher,
Tkinter, /api/ads/set) keep working unchanged.
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from ..db import get_db

VALID_FORMATS = (
    "rewarded_popup", "rewarded_interstitial", "in_app_interstitial",
    "smartlink", "custom",
)
VALID_SLOTS = (
    "head", "body_end", "banner_top", "banner_bottom", "interstitial",
    "bot_message",
)
VALID_SCOPES = ("bot", "category", "global")


def _now() -> str:
    return datetime.now().isoformat()


def _new_id() -> str:
    return "ad_" + uuid.uuid4().hex[:12]


@dataclass
class Ad:
    """One entry in the ad library."""

    ad_id: str = field(default_factory=_new_id)
    name: str = ""
    provider: str = "monetag"
    format: str = "custom"
    slot: str = "body_end"
    snippet: str = ""
    zone_id: Optional[str] = None
    direct_link: Optional[str] = None
    notes: Optional[str] = None
    enabled: bool = True
    cpm_rate: float = 0.0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    created_by: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row) -> "Ad":
        data = dict(row)
        return cls(
            ad_id=data.get("ad_id", ""),
            name=data.get("name", "") or "",
            provider=data.get("provider", "monetag") or "monetag",
            format=data.get("format", "custom") or "custom",
            slot=data.get("slot", "body_end") or "body_end",
            snippet=data.get("snippet", "") or "",
            zone_id=data.get("zone_id"),
            direct_link=data.get("direct_link"),
            notes=data.get("notes"),
            enabled=bool(data.get("enabled", 1)),
            cpm_rate=float(data.get("cpm_rate") or 0),
            created_at=data.get("created_at") or _now(),
            updated_at=data.get("updated_at") or _now(),
            created_by=data.get("created_by"),
        )


class AdLibrary:
    """CRUD over the ``ads`` table."""

    def __init__(self, db=None):
        self.db = db or get_db()

    # ── Create ──────────────────────────────────────────────────────────────
    def create(self, ad: Ad, actor: str = "system") -> Ad:
        if not ad.ad_id:
            ad.ad_id = _new_id()
        now = _now()
        ad.created_at = ad.created_at or now
        ad.updated_at = now
        if ad.created_by is None:
            ad.created_by = actor
        if self.db is None:
            return ad
        try:
            with self.db._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO ads
                        (ad_id, name, provider, format, slot, snippet, zone_id,
                         direct_link, notes, enabled, cpm_rate, created_at,
                         updated_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (ad.ad_id, ad.name, ad.provider, ad.format, ad.slot,
                     ad.snippet, ad.zone_id, ad.direct_link, ad.notes,
                     1 if ad.enabled else 0, ad.cpm_rate, ad.created_at,
                     ad.updated_at, ad.created_by),
                )
        except Exception:
            pass
        return ad

    # ── Read ────────────────────────────────────────────────────────────────
    def get(self, ad_id: str) -> Optional[Ad]:
        if self.db is None:
            return None
        try:
            with self.db._get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM ads WHERE ad_id=?", (ad_id,)
                ).fetchone()
            return Ad.from_row(row) if row else None
        except Exception:
            return None

    def list(self, enabled_only: bool = False, slot: str = "") -> list:
        if self.db is None:
            return []
        clauses, params = [], []
        if enabled_only:
            clauses.append("enabled=1")
        if slot:
            clauses.append("slot=?")
            params.append(slot)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with self.db._get_conn() as conn:
                rows = conn.execute(
                    f"SELECT * FROM ads {where} ORDER BY updated_at DESC", params
                ).fetchall()
            return [Ad.from_row(r) for r in rows]
        except Exception:
            return []

    def count(self) -> int:
        if self.db is None:
            return 0
        try:
            with self.db._get_conn() as conn:
                row = conn.execute("SELECT COUNT(*) AS c FROM ads").fetchone()
            return int(row["c"]) if row else 0
        except Exception:
            return 0

    # ── Update ──────────────────────────────────────────────────────────────
    def update(self, ad_id: str, **fields) -> Optional[Ad]:
        ad = self.get(ad_id)
        if ad is None:
            return None
        allowed = {"name", "provider", "format", "slot", "snippet", "zone_id",
                   "direct_link", "notes", "enabled", "cpm_rate"}
        for key, value in fields.items():
            if key in allowed:
                setattr(ad, key, value)
        ad.updated_at = _now()
        if self.db is None:
            return ad
        try:
            with self.db._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE ads SET name=?, provider=?, format=?, slot=?, snippet=?,
                        zone_id=?, direct_link=?, notes=?, enabled=?, cpm_rate=?,
                        updated_at=?
                    WHERE ad_id=?
                    """,
                    (ad.name, ad.provider, ad.format, ad.slot, ad.snippet,
                     ad.zone_id, ad.direct_link, ad.notes,
                     1 if ad.enabled else 0, ad.cpm_rate, ad.updated_at, ad.ad_id),
                )
        except Exception:
            pass
        return ad

    def set_enabled(self, ad_id: str, enabled: bool) -> bool:
        ad = self.update(ad_id, enabled=bool(enabled))
        return ad is not None

    # ── Delete ──────────────────────────────────────────────────────────────
    def delete(self, ad_id: str) -> bool:
        if self.db is None:
            return False
        try:
            with self.db._get_conn() as conn:
                conn.execute("DELETE FROM ad_assignments WHERE ad_id=?", (ad_id,))
                cur = conn.execute("DELETE FROM ads WHERE ad_id=?", (ad_id,))
                return (cur.rowcount or 0) > 0
        except Exception:
            return False

    # ── Assignment ──────────────────────────────────────────────────────────
    def assign(self, ad_id: str, scope: str, target_id: Optional[str] = None,
               priority: int = 0) -> bool:
        if scope not in VALID_SCOPES:
            return False
        if self.db is None:
            return False
        try:
            with self.db._get_conn() as conn:
                conn.execute(
                    "INSERT INTO ad_assignments (ad_id, scope, target_id, priority, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (ad_id, scope, target_id, int(priority or 0), _now()),
                )
            return True
        except Exception:
            return False

    def unassign(self, ad_id: str, scope: str,
                 target_id: Optional[str] = None) -> int:
        if self.db is None:
            return 0
        try:
            with self.db._get_conn() as conn:
                if target_id is None:
                    cur = conn.execute(
                        "DELETE FROM ad_assignments WHERE ad_id=? AND scope=?",
                        (ad_id, scope))
                else:
                    cur = conn.execute(
                        "DELETE FROM ad_assignments WHERE ad_id=? AND scope=? AND target_id=?",
                        (ad_id, scope, target_id))
                return int(cur.rowcount or 0)
        except Exception:
            return 0

    def assignments_for(self, ad_id: str) -> list:
        if self.db is None:
            return []
        try:
            with self.db._get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, ad_id, scope, target_id, priority, created_at "
                    "FROM ad_assignments WHERE ad_id=? ORDER BY priority DESC, id",
                    (ad_id,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def ads_for_target(self, bot_id: str, category: str = "") -> list:
        """All ads assigned to this bot (any scope), enabled only."""
        if self.db is None:
            return []
        try:
            with self.db._get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT a.* FROM ads a
                    JOIN ad_assignments asg ON asg.ad_id = a.ad_id
                    WHERE a.enabled = 1 AND (
                          (asg.scope='bot' AND asg.target_id=?) OR
                          (asg.scope='category' AND asg.target_id=?) OR
                          (asg.scope='global')
                    )
                    ORDER BY
                        CASE asg.scope
                            WHEN 'bot' THEN 0
                            WHEN 'category' THEN 1
                            ELSE 2
                        END ASC,
                        asg.priority DESC,
                        asg.id ASC
                    """, (bot_id, category)).fetchall()
            return [Ad.from_row(r) for r in rows]
        except Exception:
            return []

    # ── Tracking ────────────────────────────────────────────────────────────
    def record_event(self, ad_id: str, bot_id: str, event_type: str,
                     user_id: int = 0) -> bool:
        if self.db is None:
            return False
        try:
            with self.db._get_conn() as conn:
                conn.execute(
                    "INSERT INTO ad_events (ad_id, bot_id, event_type, user_id, occurred_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (ad_id, bot_id, event_type, int(user_id or 0), _now()),
                )
            return True
        except Exception:
            return False

    def stats(self, ad_id: str = "") -> dict:
        if self.db is None:
            return {"impressions": 0, "clicks": 0, "ctr": 0.0}
        clauses, params = [], []
        if ad_id:
            clauses.append("ad_id=?")
            params.append(ad_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with self.db._get_conn() as conn:
                views = int(conn.execute(
                    f"SELECT COUNT(*) AS c FROM ad_events {where} "
                    + ("AND " if where else "WHERE ") + "event_type='view'",
                    params).fetchone()["c"])
                clicks = int(conn.execute(
                    f"SELECT COUNT(*) AS c FROM ad_events {where} "
                    + ("AND " if where else "WHERE ") + "event_type='click'",
                    params).fetchone()["c"])
        except Exception:
            return {"impressions": 0, "clicks": 0, "ctr": 0.0}
        ctr = round(clicks * 100.0 / views, 2) if views else 0.0
        return {"impressions": views, "clicks": clicks, "ctr": ctr}

    def per_bot_stats(self, ad_id: str = "") -> list:
        if self.db is None:
            return []
        clauses, params = [], []
        if ad_id:
            clauses.append("ad_id=?")
            params.append(ad_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with self.db._get_conn() as conn:
                rows = conn.execute(
                    f"""
                    SELECT bot_id,
                           SUM(CASE WHEN event_type='view'  THEN 1 ELSE 0 END) AS views,
                           SUM(CASE WHEN event_type='click' THEN 1 ELSE 0 END) AS clicks
                    FROM ad_events {where}
                    GROUP BY bot_id ORDER BY views DESC
                    """, params).fetchall()
            return [{"bot_id": r["bot_id"],
                     "impressions": int(r["views"] or 0),
                     "clicks": int(r["clicks"] or 0)} for r in rows]
        except Exception:
            return []


def get_ad_library(db=None) -> AdLibrary:
    """Shared instance."""
    return AdLibrary(db or get_db())
