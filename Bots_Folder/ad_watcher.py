# =============================================================================
#  Bots_Folder/ad_watcher.py — مراقب ومُزامن شفرات الإعلانات التلقائي
#  يراقب ملفات الإعدادات ويحدّث الذاكرة الحية وملفات تطبيقات الويب فوراً
# =============================================================================
import os
import sys
import time
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger("AdWatcher")

BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / "Data"
MONETAG_FILE = DATA_DIR / "monetag_config.json"
ADS_FILE = DATA_DIR / "ads_config.json"
TOOLS_DIR = BASE_DIR / "tools"


def sync_mini_apps() -> Dict[str, Any]:
    """
    إعادة توليد وحقن شفرات الإعلانات (Monetag) فورياً في ملفات تطبيقات الويب:
    webapps/<bot_id>.html و webroot/<bot_id>/index.html
    """
    try:
        if str(TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(TOOLS_DIR))
        from build_mini_apps import main as build_main
        rc = build_main()
        return {
            "ok": rc == 0,
            "timestamp": datetime.now().isoformat(),
            "status": "synchronized"
        }
    except Exception as e:
        logger.error(f"❌ خطأ أثناء مزامنة تطبيقات الويب: {e}")
        return {
            "ok": False,
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


def reload_ad_manager():
    """تحديث إعدادات الإعلانات المحملة في الذاكرة الحية لجميع البوتات (Hot Reload)."""
    try:
        from ad_manager import get_ad_manager
        mgr = get_ad_manager()
        mgr.config = mgr._load_config()
        mgr.monetag_config = mgr._load_monetag_config()
        logger.info("🔄 تم تحديث ذاكرة نظام الإعلانات و Monetag بنجاح.")
        return True
    except Exception as e:
        logger.debug(f"reload_ad_manager: {e}")
        return False


class AdConfigWatcher:
    """مراقب لملفات إعدادات الإعلانات يقوم بإعادة البناء والتحديث التلقائي عند أي تعديل."""

    def __init__(self, check_interval: float = 2.0, on_sync: Optional[Callable] = None):
        self.check_interval = check_interval
        self.on_sync = on_sync
        self._last_monetag_mtime = self._get_mtime(MONETAG_FILE)
        self._last_ads_mtime = self._get_mtime(ADS_FILE)
        self._lock = threading.Lock()

    def _get_mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime if path.exists() else 0.0
        except Exception:
            return 0.0

    def check_and_sync(self) -> bool:
        """فحص ما إذا طرأ أي تعديل على ملفات الإعلانات وتنفيذ المزامنة التلقائية."""
        with self._lock:
            cur_monetag_mtime = self._get_mtime(MONETAG_FILE)
            cur_ads_mtime = self._get_mtime(ADS_FILE)

            changed = False
            if cur_monetag_mtime != self._last_monetag_mtime:
                self._last_monetag_mtime = cur_monetag_mtime
                changed = True

            if cur_ads_mtime != self._last_ads_mtime:
                self._last_ads_mtime = cur_ads_mtime
                changed = True

            if changed:
                logger.info("📢 تم رصد تعديل في شفرات إعلانات Monetag — جاري المزامنة التلقائية...")
                reload_ad_manager()
                report = sync_mini_apps()
                if self.on_sync:
                    try:
                        self.on_sync(report)
                    except Exception:
                        pass
                return True

            return False


def start_ad_watcher(stop_event: threading.Event,
                     check_interval: float = 2.0,
                     on_sync: Optional[Callable] = None,
                     custom_logger: Optional[logging.Logger] = None) -> threading.Thread:
    """
    تشغيل خيط خلفي (Daemon) يراقب ملفات الإعلانات ويحدث ملفات تطبيقات الويب تلقائياً.
    """
    log = custom_logger or logger
    watcher = AdConfigWatcher(check_interval=check_interval, on_sync=on_sync)

    def _watcher_loop():
        log.info(f"👀 خيط مراقبة شفرات الإعلانات التلقائي يعمل (كل {check_interval:g}ث)...")
        while not stop_event.is_set():
            try:
                watcher.check_and_sync()
            except Exception as e:
                log.debug(f"Ad watcher check error: {e}")
            if stop_event.wait(check_interval):
                break
        log.info("⏹ توقف خيط مراقبة شفرات الإعلانات.")

    t = threading.Thread(target=_watcher_loop, name="AdConfigWatcher", daemon=True)
    t.start()
    return t

