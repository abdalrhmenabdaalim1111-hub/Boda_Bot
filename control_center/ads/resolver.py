"""
control_center/ads/resolver.py — assignment conflict resolution.

Precedence (highest → lowest): **bot** > **category** > **global**.
Multiple ads at the same scope are ordered by (priority DESC, id ASC).
"""

from .model import Ad, AdLibrary, VALID_SCOPES


def resolve_ads_for_bot(bot_id: str, category: str = "",
                       library: AdLibrary | None = None) -> list[Ad]:
    """
    All ads that apply to ``bot_id`` (any scope), enabled only, ordered so
    that the most specific assignment wins first.
    """
    lib = library or AdLibrary()
    ads = lib.ads_for_target(bot_id, category)
    # ads_for_target already filters enabled=1 and orders by priority.
    return ads


def resolve_ad_for_bot(bot_id: str, slot: str, category: str = "",
                      library: AdLibrary | None = None) -> Ad | None:
    """
    The single ad that should be injected into ``slot`` for ``bot_id``.

    Resolution order:
      1. bot-level assignment for an ad whose ``slot`` matches
      2. category-level assignment for a matching slot
      3. global assignment for a matching slot
    Returns None when nothing applies (slot stays empty).
    """
    lib = library or AdLibrary()
    candidates = resolve_ads_for_bot(bot_id, category, lib)
    matching = [a for a in candidates if a.slot == slot]
    if not matching:
        return None
    # ads_for_target is ordered by priority DESC, id ASC — first match wins.
    return matching[0]


def effective_ad(bot_id: str, slot: str, category: str = "",
                 library: AdLibrary | None = None) -> dict:
    """
    Human-readable resolution result for the UI: which ad won and why.
    """
    ad = resolve_ad_for_bot(bot_id, slot, category, library)
    if ad is None:
        return {"bot_id": bot_id, "slot": slot, "ad_id": None,
                "name": None, "reason": "no assignment"}
    return {"bot_id": bot_id, "slot": slot, "ad_id": ad.ad_id,
            "name": ad.name, "provider": ad.provider, "format": ad.format,
            "enabled": ad.enabled, "reason": "assigned"}


def effective_map(bot_id: str, category: str = "",
                 library: AdLibrary | None = None) -> dict:
    """Effective ad for every slot of a bot (used by the panel)."""
    from .model import VALID_SLOTS
    return {slot: effective_ad(bot_id, slot, category, library)
            for slot in VALID_SLOTS}
