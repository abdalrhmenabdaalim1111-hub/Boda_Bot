"""
monitor.py — نظام المراقبة المتقدم
يوفر أدوات متقدمة لمراقبة أداء البوتات
"""
import time
import psutil
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from collections import deque
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[Monitor] %(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Monitor")

@dataclass
class PerformanceMetrics:
    """مقاييس الأداء"""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    response_time: float = 0.0
    error_rate: float = 0.0
    uptime: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)

@dataclass
class BotMetrics:
    """مقاييس البوت"""
    name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    last_activity: Optional[datetime] = None
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    errors: deque = field(default_factory=lambda: deque(maxlen=50))

class Monitor:
    """نظام المراقبة الرئيسي"""

    def __init__(self, check_interval: int = 60):
        """
        تهيئة نظام المراقبة

        Args:
            check_interval: الفاصل الزمني للفحص بالثواني
        """
        self.check_interval = check_interval
        self.bots_metrics: Dict[str, BotMetrics] = {}
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.alert_callbacks: List[Callable] = []

    def register_bot(self, bot_name: str) -> BotMetrics:
        """
        تسجيل بوت للمراقبة

        Args:
            bot_name: اسم البوت

        Returns:
            مقاييس البوت
        """
        if bot_name not in self.bots_metrics:
            self.bots_metrics[bot_name] = BotMetrics(name=bot_name)
            logger.info(f"تم تسجيل البوت {bot_name} للمراقبة")
        return self.bots_metrics[bot_name]

    def record_request(self, bot_name: str, success: bool, response_time: float):
        """
        تسجيل طلب للبوت

        Args:
            bot_name: اسم البوت
            success: هل نجح الطلب
            response_time: وقت الاستجابة
        """
        if bot_name not in self.bots_metrics:
            self.register_bot(bot_name)

        metrics = self.bots_metrics[bot_name]
        metrics.total_requests += 1
        metrics.last_activity = datetime.now()
        metrics.response_times.append(response_time)

        if success:
            metrics.successful_requests += 1
        else:
            metrics.failed_requests += 1

        # تحديث متوسط وقت الاستجابة
        metrics.avg_response_time = sum(metrics.response_times) / len(metrics.response_times)

    def record_error(self, bot_name: str, error: str):
        """
        تسجيل خطأ للبوت

        Args:
            bot_name: اسم البوت
            error: رسالة الخطأ
        """
        if bot_name not in self.bots_metrics:
            self.register_bot(bot_name)

        metrics = self.bots_metrics[bot_name]
        metrics.errors.append({
            "timestamp": datetime.now().isoformat(),
            "error": error
        })

    def update_performance(self, bot_name: str, process_id: int):
        """
        تحديث مقاييس الأداء للبوت

        Args:
            bot_name: اسم البوت
            process_id: معرف العملية
        """
        try:
            process = psutil.Process(process_id)
            perf = self.bots_metrics[bot_name].performance

            perf.cpu_percent = process.cpu_percent()
            memory_info = process.memory_info()
            perf.memory_mb = memory_info.rss / (1024 * 1024)
            perf.memory_percent = process.memory_percent()
            perf.last_update = datetime.now()

            # حساب معدل الأخطاء
            metrics = self.bots_metrics[bot_name]
            if metrics.total_requests > 0:
                perf.error_rate = (metrics.failed_requests / metrics.total_requests) * 100

        except psutil.NoSuchProcess:
            logger.warning(f"العملية {process_id} غير موجودة")
        except Exception as e:
            logger.error(f"خطأ في تحديث الأداء: {e}")

    def get_metrics(self, bot_name: str) -> Optional[BotMetrics]:
        """
        الحصول على مقاييس البوت

        Args:
            bot_name: اسم البوت

        Returns:
            مقاييس البوت أو None إذا لم يتم العثور عليه
        """
        return self.bots_metrics.get(bot_name)

    def get_all_metrics(self) -> Dict[str, BotMetrics]:
        """
        الحصول على مقاييس جميع البوتات

        Returns:
            قاموس بمقاييس جميع البوتات
        """
        return self.bots_metrics

    def add_alert_callback(self, callback: Callable):
        """
        إضافة دالة تنبيه

        Args:
            callback: دالة التنبيه
        """
        self.alert_callbacks.append(callback)

    def _check_alerts(self):
        """فحص التنبيهات"""
        for bot_name, metrics in self.bots_metrics.items():
            # تنبيه عند ارتفاع معدل الأخطاء
            if metrics.performance.error_rate > 10:
                alert_msg = f"⚠️ معدل أخطاء مرتفع لـ {bot_name}: {metrics.performance.error_rate:.2f}%"
                logger.warning(alert_msg)
                for callback in self.alert_callbacks:
                    callback(bot_name, "high_error_rate", alert_msg)

            # تنبيه عند ارتفاع استهلاك الذاكرة
            if metrics.performance.memory_percent > 80:
                alert_msg = f"⚠️ استهلاك ذاكرة مرتفع لـ {bot_name}: {metrics.performance.memory_percent:.2f}%"
                logger.warning(alert_msg)
                for callback in self.alert_callbacks:
                    callback(bot_name, "high_memory", alert_msg)

            # تنبيه عند ارتفاع استهلاك المعالج
            if metrics.performance.cpu_percent > 80:
                alert_msg = f"⚠️ استهلاك معالج مرتفع لـ {bot_name}: {metrics.performance.cpu_percent:.2f}%"
                logger.warning(alert_msg)
                for callback in self.alert_callbacks:
                    callback(bot_name, "high_cpu", alert_msg)

    def _monitor_loop(self):
        """حلقة المراقبة الرئيسية"""
        while self.is_monitoring:
            try:
                self._check_alerts()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"خطأ في حلقة المراقبة: {e}")
                time.sleep(self.check_interval)

    def start(self):
        """بدء المراقبة"""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("تم بدء المراقبة")

    def stop(self):
        """إيقاف المراقبة"""
        if self.is_monitoring:
            self.is_monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)
            logger.info("تم إيقاف المراقبة")

    def get_summary(self) -> dict:
        """
        الحصول على ملخص المراقبة

        Returns:
            قاموس يحتوي على ملخص المراقبة
        """
        summary = {
            "total_bots": len(self.bots_metrics),
            "total_requests": sum(m.total_requests for m in self.bots_metrics.values()),
            "successful_requests": sum(m.successful_requests for m in self.bots_metrics.values()),
            "failed_requests": sum(m.failed_requests for m in self.bots_metrics.values()),
            "avg_response_time": sum(m.avg_response_time for m in self.bots_metrics.values()) / len(self.bots_metrics) if self.bots_metrics else 0,
            "bots": {}
        }

        for bot_name, metrics in self.bots_metrics.items():
            summary["bots"][bot_name] = {
                "total_requests": metrics.total_requests,
                "success_rate": (metrics.successful_requests / metrics.total_requests * 100) if metrics.total_requests > 0 else 0,
                "avg_response_time": metrics.avg_response_time,
                "cpu_percent": metrics.performance.cpu_percent,
                "memory_percent": metrics.performance.memory_percent,
                "error_rate": metrics.performance.error_rate
            }

        return summary
