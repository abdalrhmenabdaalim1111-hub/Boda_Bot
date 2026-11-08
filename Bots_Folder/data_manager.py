"""
data_manager.py — نظام إدارة البيانات الموحد
يوفر نظاماً متكاملاً لإدارة البيانات المشتركة بين البوتات
"""
import logging
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
import threading

logging.basicConfig(
    level=logging.INFO,
    format="[DataManager] %(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DataManager")

@dataclass
class DataEntry:
    """فئة إدخال البيانات"""
    key: str
    value: Any
    timestamp: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)

class DataManager:
    """مدير البيانات الرئيسي"""

    def __init__(self, storage_path: str = "bot_data.json"):
        """
        تهيئة مدير البيانات

        Args:
            storage_path: مسار ملف التخزين
        """
        self.storage_path = storage_path
        self.data: Dict[str, DataEntry] = {}
        self.lock = threading.Lock()
        self._load_data()

    def _load_data(self):
        """تحميل البيانات من الملف"""
        try:
            abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), self.storage_path))
            if os.path.exists(abs_path):
                with open(abs_path, 'r', encoding='utf-8') as f:
                    data_dict = json.load(f)
                    for key, entry_data in data_dict.items():
                        entry = DataEntry(
                            key=key,
                            value=entry_data['value'],
                            timestamp=datetime.fromisoformat(entry_data['timestamp']),
                            expires_at=datetime.fromisoformat(entry_data['expires_at']) if entry_data.get('expires_at') else None,
                            metadata=entry_data.get('metadata', {})
                        )
                        # التحقق من عدم انتهاء صلاحية البيانات
                        if entry.expires_at is None or entry.expires_at > datetime.now():
                            self.data[key] = entry
                logger.info(f"تم تحميل {len(self.data)} إدخال بيانات")
        except Exception as e:
            logger.error(f"خطأ في تحميل البيانات: {e}")

    def _save_data(self):
        """حفظ البيانات في الملف"""
        try:
            abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), self.storage_path))
            data_dict = {}
            for key, entry in self.data.items():
                entry_data = {
                    'value': entry.value,
                    'timestamp': entry.timestamp.isoformat(),
                    'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
                    'metadata': entry.metadata
                }
                data_dict[key] = entry_data

            with open(abs_path, 'w', encoding='utf-8') as f:
                json.dump(data_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"خطأ في حفظ البيانات: {e}")

    def set(
        self,
        key: str,
        value: Any,
        expires_in: Optional[int] = None,
        metadata: Optional[Dict] = None
    ):
        """
        تعيين قيمة لمفتاح

        Args:
            key: المفتاح
            value: القيمة
            expires_in: مدة الصلاحية بالثواني
            metadata: بيانات إضافية
        """
        with self.lock:
            expires_at = None
            if expires_in is not None:
                from datetime import timedelta
                expires_at = datetime.now() + timedelta(seconds=expires_in)

            entry = DataEntry(
                key=key,
                value=value,
                expires_at=expires_at,
                metadata=metadata or {}
            )

            self.data[key] = entry
            self._save_data()
            logger.debug(f"تم تعيين المفتاح: {key}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        الحصول على قيمة مفتاح

        Args:
            key: المفتاح
            default: القيمة الافتراضية

        Returns:
            القيمة أو القيمة الافتراضية
        """
        with self.lock:
            entry = self.data.get(key)
            if entry is None:
                return default

            # التحقق من انتهاء الصلاحية
            if entry.expires_at and entry.expires_at < datetime.now():
                del self.data[key]
                self._save_data()
                return default

            return entry.value

    def delete(self, key: str) -> bool:
        """
        حذف مفتاح

        Args:
            key: المفتاح

        Returns:
            True إذا تم الحذف بنجاح
        """
        with self.lock:
            if key in self.data:
                del self.data[key]
                self._save_data()
                logger.debug(f"تم حذف المفتاح: {key}")
                return True
            return False

    def exists(self, key: str) -> bool:
        """
        التحقق من وجود مفتاح

        Args:
            key: المفتاح

        Returns:
            True إذا كان المفتاح موجوداً
        """
        with self.lock:
            entry = self.data.get(key)
            if entry is None:
                return False

            # التحقق من انتهاء الصلاحية
            if entry.expires_at and entry.expires_at < datetime.now():
                del self.data[key]
                self._save_data()
                return False

            return True

    def get_all(self) -> Dict[str, Any]:
        """
        الحصول على جميع البيانات

        Returns:
            قاموس بجميع البيانات
        """
        with self.lock:
            # تنظيف البيانات المنتهية
            expired_keys = [
                key for key, entry in self.data.items()
                if entry.expires_at and entry.expires_at < datetime.now()
            ]
            for key in expired_keys:
                del self.data[key]
            if expired_keys:
                self._save_data()

            return {key: entry.value for key, entry in self.data.items()}

    def clear(self):
        """مسح جميع البيانات"""
        with self.lock:
            self.data.clear()
            self._save_data()
            logger.info("تم مسح جميع البيانات")

    def get_metadata(self, key: str) -> Optional[Dict]:
        """
        الحصول على بيانات إضافية لمفتاح

        Args:
            key: المفتاح

        Returns:
            البيانات الإضافية أو None
        """
        with self.lock:
            entry = self.data.get(key)
            if entry:
                return entry.metadata
            return None

    def update_metadata(self, key: str, metadata: Dict):
        """
        تحديث البيانات الإضافية لمفتاح

        Args:
            key: المفتاح
            metadata: البيانات الإضافية الجديدة
        """
        with self.lock:
            if key in self.data:
                self.data[key].metadata.update(metadata)
                self._save_data()

    def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """
        الحصول على المفاتيح حسب النمط

        Args:
            pattern: نمط البحث

        Returns:
            قائمة المفاتيح المطابقة
        """
        with self.lock:
            import fnmatch
            return [key for key in self.data.keys() if fnmatch.fnmatch(key, pattern)]

    def get_summary(self) -> Dict:
        """
        الحصول على ملخص البيانات

        Returns:
            قاموس يحتوي على ملخص البيانات
        """
        with self.lock:
            total = len(self.data)
            expired = len([
                key for key, entry in self.data.items()
                if entry.expires_at and entry.expires_at < datetime.now()
            ])

            # حساب حجم البيانات
            size = len(json.dumps({k: v.value for k, v in self.data.items()}))

            return {
                "total_entries": total,
                "expired_entries": expired,
                "active_entries": total - expired,
                "size_bytes": size,
                "size_mb": size / (1024 * 1024)
            }
