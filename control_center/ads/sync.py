"""
control_center/ads/sync.py — keep the legacy JSON mirrors in sync.

The Control Center DB is the source of truth (decision D6), but the existing
readers (``Bots_Folder/ad_manager.py``, the Tkinter dialog, the watcher,
``/api/ads/set``) still read ``Data/ads_config.json`` and
``Data/monetag_config.json``. This module rewrites those files from the DB so
nothing breaks and no second source of truth appears.
"""

import json
from pathlib import Path

from .. import config
from .model import Ad, AdLibrary
from .resolver import resolve_ad_for_bot


def _data_dir() -> Path:
    return config.DATA_DIR


def sync_monetag_config(library: AdLibrary | None = None,
                       bot_ids: list[str] | None = None) -> dict:
    """
    Rebuild ``Data/monetag_config.json`` from the ad library.

    For each bot that has a ``smartlink``/``custom`` ad assigned to the
    ``bot_message`` slot, write a per-bot entry mirroring the legacy schema
    (direct_link, zone_id, script_url, format, frequency, active). Bots with
    no assignment keep ``has_custom_ads=False``.
    """
    lib = library or AdLibrary()
    data_dir = _data_dir()
    path = data_dir / "monetag_config.json"

    # Load existing to preserve bot_name and any untouched entries.
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    bots = dict(existing.get("bots", {}))
    targets = bot_ids or list(bots.keys()) or []
    # Ensure every known bot is present.
    try:
        import json as _j
        reg = _j.loads((config.BASE_DIR / "bots_registry.json").read_text(
            encoding="utf-8"))
        for entry in (reg if isinstance(reg, list) else reg.get("bots", [])):
            bid = entry.get("id")
            if bid and bid not in bots:
                bots[bid] = {"bot_name": entry.get("name", bid),
                             "has_custom_ads": False, "direct_link": "",
                             "zone_id": "", "script_url": "", "format": "direct_link",
                             "frequency": 3, "active": False,
                             "last_updated": None}
            elif bid:
                bots[bid].setdefault("bot_name", entry.get("name", bid))
    except Exception:
        pass

    for bid in bots:
        ad = resolve_ad_for_bot(bid, "bot_message", library=lib)
        entry = bots[bid]
        if ad is not None and ad.enabled:
            entry.update({
                "has_custom_ads": True,
                "direct_link": ad.direct_link or "",
                "zone_id": ad.zone_id or "",
                "script_url": "",
                "format": ad.format,
                "frequency": 3,
                "active": True,
                "last_updated": ad.updated_at,
            })
        else:
            # keep existing scalar config if present; otherwise mark inactive
            entry.setdefault("has_custom_ads", entry.get("has_custom_ads", False))
            entry["active"] = bool(entry.get("has_custom_ads") and
                                  (entry.get("direct_link") or entry.get("zone_id")
                                   or entry.get("script_url")))

    payload = {
        "_version": "2.0",
        "_provider": "Monetag (monetag.com)",
        "_description": "Auto-synced from the Ad Code Manager (control_center.ads)",
        "global_default": existing.get("global_default", {
            "enabled": False, "direct_link": "", "zone_id": "", "script_url": "",
            "format": "direct_link", "frequency": 3}),
        "bots": bots,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return {"ok": True, "path": str(path), "bots": len(bots)}


def sync_ads_config(library: AdLibrary | None = None) -> dict:
    """
    Keep ``Data/ads_config.json`` (footer/button/force_subscribe) in sync.

    The ad library does not own footer/button/force_subscribe today, so this
    only ensures the file still exists and is valid JSON; Phase A4 will extend
    it with per-ad footer/button assignment.
    """
    path = _data_dir() / "ads_config.json"
    if not path.exists():
        path.write_text(json.dumps({"enabled": True}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return {"ok": True, "path": str(path)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def sync_all(library: AdLibrary | None = None) -> dict:
    """Run every sync. Returns a combined report."""
    return {"monetag": sync_monetag_config(library),
            "ads": sync_ads_config(library)}
