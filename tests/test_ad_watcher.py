# =============================================================================
#  tests/test_ad_watcher.py — اختبارات مراقب شفرات الإعلانات والمُزامن
# =============================================================================
import sys
import time
import types
import logging
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

import ad_watcher
from ad_watcher import sync_mini_apps, reload_ad_manager, AdConfigWatcher, start_ad_watcher


class TestSyncMiniApps:
    def test_success_returns_report(self):
        """build_mini_apps main يعيد 0 → مزامنة ناجحة"""
        fake = types.ModuleType("build_mini_apps")
        fake.main = MagicMock(return_value=0)
        with patch.dict(sys.modules, {"build_mini_apps": fake}):
            report = sync_mini_apps()
        assert report["ok"] is True
        assert report["status"] == "synchronized"
        assert report["timestamp"]
        fake.main.assert_called_once_with()

    def test_nonzero_exit_is_failure(self):
        fake = types.ModuleType("build_mini_apps")
        fake.main = MagicMock(return_value=1)
        with patch.dict(sys.modules, {"build_mini_apps": fake}):
            report = sync_mini_apps()
        assert report["ok"] is False
        assert report["status"] == "synchronized"  # الحالة تُسجل حتى مع فشل الكود

    def test_import_error_reported(self):
        """غياب وحدة البناء → تقرير فشل ولا يرفع"""
        with patch.dict(sys.modules, {"build_mini_apps": None}):
            report = sync_mini_apps()
        assert report["ok"] is False
        assert "error" in report


class TestReloadAdManager:
    def test_reload_reloads_both_configs(self):
        """إعادة تحميل config و monetag_config من الملفات"""
        mgr = MagicMock()
        mgr._load_config.return_value = {"enabled": True, "reloaded": 1}
        mgr._load_monetag_config.return_value = {"bots": {"x": 1}}
        with patch("ad_manager.get_ad_manager", return_value=mgr):
            assert reload_ad_manager() is True
        mgr._load_config.assert_called_once()
        mgr._load_monetag_config.assert_called_once()
        assert mgr.config == {"enabled": True, "reloaded": 1}
        assert mgr.monetag_config == {"bots": {"x": 1}}

    def test_reload_failure_returns_false(self):
        with patch("ad_manager.get_ad_manager", side_effect=RuntimeError("x")):
            assert reload_ad_manager() is False


class TestAdConfigWatcher:
    def test_mtime_missing_file_is_zero(self, tmp_path):
        w = AdConfigWatcher()
        assert w._get_mtime(tmp_path / "ghost.json") == 0.0

    def test_no_change_returns_false(self, tmp_path):
        """لا تعديل → False دون مزامنة"""
        ads = tmp_path / "ads_config.json"
        ads.write_text("{}", encoding="utf-8")
        w = AdConfigWatcher()
        w._last_ads_mtime = w._get_mtime(ads)
        w._last_monetag_mtime = w._get_mtime(ads)
        with patch.object(ad_watcher, "MONETAG_FILE", ads), \
                patch.object(ad_watcher, "ADS_FILE", ads):
            assert w.check_and_sync() is False

    def test_change_triggers_reload_and_sync(self, tmp_path):
        """تعديل ملف → reload + sync + استدعاء on_sync"""
        ads = tmp_path / "ads_config.json"
        ads.write_text("{}", encoding="utf-8")
        w = AdConfigWatcher(check_interval=0.1, on_sync=MagicMock())
        w._last_ads_mtime = w._get_mtime(ads)
        w._last_monetag_mtime = w._get_mtime(ads)

        with patch.object(ad_watcher, "MONETAG_FILE", ads), \
                patch.object(ad_watcher, "ADS_FILE", ads), \
                patch("ad_watcher.reload_ad_manager") as rl, \
                patch("ad_watcher.sync_mini_apps", return_value={"ok": True}) as sync:
            # تعديل الملف يغيّر mtime — قد يمر خلال ثانية واحدة، لذا نرهن على patch
            with patch.object(w, "_get_mtime", side_effect=[999.0, 999.0]):
                assert w.check_and_sync() is True
        rl.assert_called_once()
        sync.assert_called_once()
        w.on_sync.assert_called_once_with({"ok": True})

    def test_on_sync_exception_swallowed(self, tmp_path):
        """رد اتصال فاشل لا يفسد المزامنة"""
        ads = tmp_path / "a.json"
        w = AdConfigWatcher(on_sync=MagicMock(side_effect=RuntimeError("cb")))
        with patch.object(ad_watcher, "MONETAG_FILE", ads), \
                patch.object(ad_watcher, "ADS_FILE", ads), \
                patch("ad_watcher.reload_ad_manager"), \
                patch("ad_watcher.sync_mini_apps", return_value={"ok": True}), \
                patch.object(w, "_get_mtime", side_effect=[999.0, 999.0]):
            assert w.check_and_sync() is True  # لا يرفع

    def test_no_double_sync_within_lock(self, tmp_path):
        """بعد المزامنة تتحفظ الـ mtime الجديدة — الفحص التالي False"""
        ads = tmp_path / "a.json"
        w = AdConfigWatcher(on_sync=None)
        seq = iter([999.0, 999.0, 999.0, 999.0])  # نفس القيم مرتين متتاليتين
        with patch.object(ad_watcher, "MONETAG_FILE", ads), \
                patch.object(ad_watcher, "ADS_FILE", ads), \
                patch("ad_watcher.reload_ad_manager"), \
                patch("ad_watcher.sync_mini_apps", return_value={"ok": True}), \
                patch.object(w, "_get_mtime", side_effect=lambda p: next(seq)):
            assert w.check_and_sync() is True   # أول فحص: تغيّرت عن 0.0 الابتدائية
            assert w.check_and_sync() is False  # الثاني: نفس القيمة المحفوظة


class TestStartAdWatcher:
    def test_thread_runs_and_stops(self):
        """الخيط يبدأ ويفحص ويستجيب لحدث الإيقاف"""
        stop = threading.Event()
        checks = []
        watcher = MagicMock()
        watcher.check_and_sync.side_effect = lambda: checks.append(1)

        with patch("ad_watcher.AdConfigWatcher", return_value=watcher) as CW:
            t = start_ad_watcher(stop, check_interval=0.05)
            assert t.daemon is True
            assert t.name == "AdConfigWatcher"
            time.sleep(0.25)
            stop.set()
            t.join(timeout=3)
        assert not t.is_alive()
        assert len(checks) >= 2            # فحص فعلي أكثر من مرة
        CW.assert_called_once_with(check_interval=0.05, on_sync=None)

    def test_check_exception_does_not_kill_loop(self):
        """خطأ في الفحص يُسجل ويُواصل الحلقة"""
        stop = threading.Event()
        watcher = MagicMock()
        watcher.check_and_sync.side_effect = RuntimeError("x")

        log = logging.getLogger("AdWatcherTest")
        log.setLevel(logging.CRITICAL)  # إسكات الإخراج
        t = start_ad_watcher(stop, check_interval=0.05, custom_logger=log)
        time.sleep(0.2)
        stop.set()
        t.join(timeout=3)
        assert not t.is_alive()

    def test_on_sync_callback_forwarded(self):
        stop = threading.Event()
        cb = MagicMock()
        with patch("ad_watcher.AdConfigWatcher") as CW:
            t = start_ad_watcher(stop, check_interval=1.0, on_sync=cb)
            stop.set()
            t.join(timeout=3)
        CW.assert_called_once_with(check_interval=1.0, on_sync=cb)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
