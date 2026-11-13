# =============================================================================
#  tests/test_monitor.py — اختبارات نظام المراقبة المتقدم
# =============================================================================
import sys
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

import psutil
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

from monitor import Monitor, BotMetrics, PerformanceMetrics


@pytest.fixture
def mon():
    return Monitor(check_interval=0.05)


def _fake_process(cpu=10.0, mem_mb=50, mem_pct=20.0):
    p = MagicMock()
    p.cpu_percent.return_value = cpu
    p.memory_info.return_value = MagicMock(rss=mem_mb * 1024 * 1024)
    p.memory_percent.return_value = mem_pct
    return p


class TestRegistration:
    def test_register_new_bot(self, mon):
        m = mon.register_bot("store")
        assert isinstance(m, BotMetrics)
        assert m.name == "store"
        assert m.total_requests == 0

    def test_register_twice_returns_same(self, mon):
        m1 = mon.register_bot("store")
        m2 = mon.register_bot("store")
        assert m1 is m2
        assert len(mon.bots_metrics) == 1


class TestRecordRequest:
    def test_records_success_and_failure(self, mon):
        mon.record_request("b", success=True, response_time=0.1)
        mon.record_request("b", success=False, response_time=0.3)
        m = mon.get_metrics("b")
        assert m.total_requests == 2
        assert m.successful_requests == 1
        assert m.failed_requests == 1
        assert m.avg_response_time == pytest.approx(0.2)
        assert m.last_activity is not None

    def test_unknown_bot_autoregisters(self, mon):
        mon.record_request("newbot", success=True, response_time=0.1)
        assert mon.get_metrics("newbot") is not None

    def test_avg_over_sliding_window(self, mon):
        """المتوسط يُحسب على آخر 100 طلب (حد الـ deque)"""
        for i in range(150):
            mon.record_request("b", success=True, response_time=float(i) / 1000)
        m = mon.get_metrics("b")
        assert len(m.response_times) == 100
        assert m.avg_response_time == pytest.approx(
            sum(t / 1000 for t in range(50, 150)) / 100)


class TestRecordError:
    def test_records_error_entry(self, mon):
        mon.record_error("b", "boom")
        err = mon.get_metrics("b").errors[0]
        assert err["error"] == "boom"
        assert err["timestamp"]

    def test_errors_capped_at_50(self, mon):
        for i in range(60):
            mon.record_error("b", f"e{i}")
        errors = mon.get_metrics("b").errors
        assert len(errors) == 50
        assert errors[-1]["error"] == "e59"


class TestUpdatePerformance:
    def test_updates_from_process(self, mon):
        mon.record_request("b", success=False, response_time=0.1)
        mon.record_request("b", success=True, response_time=0.1)
        with patch("monitor.psutil.Process", return_value=_fake_process(cpu=25.0, mem_mb=64, mem_pct=30.0)):
            mon.update_performance("b", process_id=4242)
        perf = mon.get_metrics("b").performance
        assert perf.cpu_percent == 25.0
        assert perf.memory_mb == pytest.approx(64.0)
        assert perf.memory_percent == 30.0
        assert perf.error_rate == pytest.approx(50.0)  # 1 فشل من 2

    def test_error_rate_zero_without_requests(self, mon):
        mon.register_bot("b")  # update_performance لا يسجل تلقائياً
        with patch("monitor.psutil.Process", return_value=_fake_process()):
            mon.update_performance("b", 1)
        assert mon.get_metrics("b").performance.error_rate == 0.0

    def test_no_such_process_warns_only(self, mon):
        mon.register_bot("b")
        with patch("monitor.psutil.Process", side_effect=psutil.NoSuchProcess(1)):
            mon.update_performance("b", 1)  # لا يرفع
        assert mon.get_metrics("b").performance.cpu_percent == 0.0

    def test_unknown_bot_raises_keyerror_swallowed(self, mon):
        """بوت غير مسجّل → KeyError يُلتقط في الجسم ولا يرفع"""
        with patch("monitor.psutil.Process", return_value=_fake_process()):
            mon.update_performance("ghost", 1)  # لا يرفع
        assert mon.get_metrics("ghost") is None

    def test_generic_exception_swallowed(self, mon):
        mon.register_bot("b")
        with patch("monitor.psutil.Process", side_effect=RuntimeError("x")):
            mon.update_performance("b", 1)  # لا يرفع


class TestAlerts:
    def test_high_error_rate_alert(self, mon):
        """معدل أخطاء > 10% يُطلق تنبيهاً للمشتركين"""
        alerts = []
        mon.add_alert_callback(lambda b, kind, msg: alerts.append((b, kind)))
        for _ in range(2):
            mon.record_request("b", success=False, response_time=0.1)
        with patch("monitor.psutil.Process", return_value=_fake_process()):
            mon.update_performance("b", 1)
        mon._check_alerts()
        kinds = [k for _, k in alerts]
        assert "high_error_rate" in kinds

    def test_memory_and_cpu_alerts(self, mon):
        alerts = []
        mon.add_alert_callback(lambda b, kind, msg: alerts.append(kind))
        mon.register_bot("b")
        with patch("monitor.psutil.Process",
                   return_value=_fake_process(cpu=90.0, mem_pct=85.0)):
            mon.update_performance("b", 1)
        mon._check_alerts()
        assert "high_memory" in alerts
        assert "high_cpu" in alerts

    def test_no_alerts_below_threshold(self, mon):
        alerts = []
        mon.add_alert_callback(lambda b, kind, msg: alerts.append(kind))
        with patch("monitor.psutil.Process",
                   return_value=_fake_process(cpu=5.0, mem_pct=10.0)):
            mon.update_performance("b", 1)
        mon._check_alerts()
        assert alerts == []

    def test_bad_callback_raises_from_direct_check(self, mon):
        """رد اتصال فاشل يرفع من _check_alerts المباشرة — لكن حلقة المراقبة
        تلتهمه (test_loop_survives_check_failure يغطي بقاء الحلقة)"""
        bad = MagicMock(side_effect=RuntimeError("cb"))
        mon.add_alert_callback(bad)
        mon.record_request("b", success=False, response_time=0.1)
        with patch("monitor.psutil.Process", return_value=_fake_process()):
            mon.update_performance("b", 1)
        with pytest.raises(RuntimeError):
            mon._check_alerts()


class TestLifecycle:
    def test_start_stop(self, mon):
        """بدء وإيقاف خيط المراقبة ينجح وينهي الحلقة"""
        mon.start()
        assert mon.is_monitoring is True
        assert mon.monitor_thread is not None
        assert mon.monitor_thread.is_alive()
        mon.stop()
        assert mon.is_monitoring is False
        assert not mon.monitor_thread.is_alive()
        # join ضمن مهلة 5ث
        mon.monitor_thread.join(timeout=5)

    def test_double_start_is_noop(self, mon):
        mon.start()
        t1 = mon.monitor_thread
        mon.start()  # لا خيط ثانٍ
        assert mon.monitor_thread is t1
        mon.stop()

    def test_stop_when_not_started_is_noop(self, mon):
        mon.stop()  # لا يرفع

    def test_loop_survives_check_failure(self):
        """استثناء داخل الحلقة يُلتقط وتُواصل العمل"""
        mon = Monitor(check_interval=0.01)
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("check fail")

        with patch.object(mon, "_check_alerts", side_effect=boom):
            mon.is_monitoring = True
            import threading
            th = threading.Thread(target=mon._monitor_loop, daemon=True)
            th.start()
            time.sleep(0.2)
            mon.is_monitoring = False
            th.join(timeout=2)
        assert calls["n"] >= 3


class TestSummary:
    def test_empty_summary(self, mon):
        s = mon.get_summary()
        assert s["total_bots"] == 0
        assert s["total_requests"] == 0
        assert s["avg_response_time"] == 0

    def test_summary_aggregates(self, mon):
        mon.record_request("a", success=True, response_time=0.1)
        mon.record_request("a", success=False, response_time=0.3)
        mon.record_request("b", success=True, response_time=0.5)
        s = mon.get_summary()
        assert s["total_bots"] == 2
        assert s["total_requests"] == 3
        assert s["successful_requests"] == 2
        assert s["failed_requests"] == 1
        assert s["avg_response_time"] == pytest.approx((0.2 + 0.5) / 2)
        bot_a = s["bots"]["a"]
        assert bot_a["success_rate"] == pytest.approx(50.0)
        assert bot_a["avg_response_time"] == pytest.approx(0.2)

    def test_get_all_metrics(self, mon):
        mon.register_bot("x")
        mon.register_bot("y")
        assert set(mon.get_all_metrics().keys()) == {"x", "y"}


class TestDataclasses:
    def test_performance_defaults(self):
        p = PerformanceMetrics()
        assert p.cpu_percent == 0.0
        assert p.last_update is not None

    def test_bot_metrics_defaults(self):
        m = BotMetrics(name="t")
        assert m.total_requests == 0
        assert m.last_activity is None
        assert m.response_times.maxlen == 100
        assert m.errors.maxlen == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
