"""
tests/conftest.py — عزل الحالة المشتركة بين الاختبارات (Singleton Hygiene)

لماذا؟
    بعض الوحدات تستخدم نمط Singleton عبر مستوى الوحدة، وأبرزها مدير
    الإعلانات في ``ad_manager._ad_manager_instance``. اختبارات
    ``test_ad_manager.py`` تستبدل النسخة المشتركة عمداً بنسخ مؤقتة
    (مجلدات tmp) للعزل — لكن بدون إعادة تعيين تبقى النسخة المؤقتة
    عالقة بعد انتهاء الملف وتُلوّث اختبارات لاحقة.

    عرَض حقيقي مرصود: بعد تشغيل ``test_ad_manager.py`` كان
    ``test_webhook_server_ad_endpoints`` يفشل لأن خادم الويب يكتب إعلان
    Monetag في نسخة tmp لا يقرؤها ``sync_mini_apps`` عند حقن HTML
    في ``webroot/currency/index.html``.

الإصلاح:
    إعادة تعيين النسخة المشتركة قبل وبعد كل اختبار (auto-use)، بأمان تام:
    لو لم تكن الوحدة مستوردة أو تغيّرت بنيتها لاحقاً لا ينكسر أي شيء.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BOTS_DIR = ROOT / "Bots_Folder"
for _p in (str(ROOT), str(BOTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _reset_shared_singletons() -> None:
    """إعادة كل النسخ المشتركة القابلة للتلوث إلى الحالة الطبيعية."""
    try:
        import ad_manager
        ad_manager._ad_manager_instance = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _singleton_isolation():
    """عزل الحالة المشتركة: قبل الاختبار وبعده."""
    _reset_shared_singletons()
    yield
    _reset_shared_singletons()
