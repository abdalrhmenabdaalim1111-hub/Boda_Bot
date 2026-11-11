"""control_center/ads — Ad Code Manager (Phase A1)"""

from .model import Ad, AdLibrary, VALID_FORMATS, VALID_SLOTS, VALID_SCOPES
from .resolver import (resolve_ad_for_bot, resolve_ads_for_bot, effective_ad,
                       effective_map)
from .validator import validate_snippet, ValidationResult
from .injector import (inject_markers, remove_markers, dry_run, rollback_file,
                       apply_injection, make_block, list_blocks, list_backups)
from .sync import sync_all, sync_monetag_config, sync_ads_config

__all__ = [
    "Ad", "AdLibrary", "VALID_FORMATS", "VALID_SLOTS", "VALID_SCOPES",
    "resolve_ad_for_bot", "resolve_ads_for_bot", "effective_ad", "effective_map",
    "validate_snippet", "ValidationResult",
    "inject_markers", "remove_markers", "dry_run", "rollback_file",
    "apply_injection", "make_block", "list_blocks", "list_backups",
    "sync_all", "sync_monetag_config", "sync_ads_config",
]
__version__ = "1.0.0"
