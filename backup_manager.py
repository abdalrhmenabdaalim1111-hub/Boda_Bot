"""
backup_manager.py — إدارة النسخ الاحتياطي المحسّنة مع دعم الضغط التلقائي
ينسخ احتياطياً: bots_registry.json + Data/ + manager_config.json + Logs/ (آخر 7 أيام)
الاستخدام:
    python backup_manager.py              ← إنشاء نسخة احتياطية مضغوطة فوراً (.zip)
    python backup_manager.py --no-zip     ← إنشاء نسخة كمجلد عادي بدون ضغط
    python backup_manager.py --list       ← عرض النسخ الاحتياطية المتوفرة
    python backup_manager.py --restore    ← استعادة أحدث نسخة احتياطية
    python backup_manager.py --auto       ← تشغيل دوري تلقائي كل 24 ساعة
"""
import os
import sys
import json
import shutil
import zipfile
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

# ── المسارات الأساسية ──────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.resolve()
BACKUP_DIR  = BASE_DIR / "Backups"
DATA_DIR    = BASE_DIR / "Data"
LOGS_DIR    = BASE_DIR / "Logs"
REGISTRY    = BASE_DIR / "bots_registry.json"
CONFIG      = BASE_DIR / "manager_config.json"

MAX_BACKUPS = 7          # الاحتفاظ بآخر 7 نسخ فقط
INTERVAL_H  = 24        # النسخ الدوري كل 24 ساعة


def _log(msg: str):
    print(f"[Backup] {datetime.now().strftime('%H:%M:%S')} {msg}")


def should_exclude(file_path: Path) -> bool:
    """التحقق من الملفات المؤقتة لتجاهلها أثناء النسخ"""
    parts = file_path.parts
    if "__pycache__" in parts or ".pytest_cache" in parts:
        return True
    if file_path.name.endswith((".pyc", ".pyo", ".pyd", ".tmp", "-journal")):
        return True
    return False


def create_backup(compress: bool = True) -> Path:
    """
    إنشاء نسخة احتياطية كاملة مع خيار الضغط التلقائي.

    Args:
        compress: إذا كان True، يتم حفظ النسخة كملف .zip مضغوط
    Returns:
        المسار النهائي للنسخة الاحتياطية
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sub_ms = f"{int(time.time() * 1000) % 1000:03d}"
    backup_name = f"backup_{ts}_{sub_ms}"

    if compress:
        zip_path = BACKUP_DIR / f"{backup_name}.zip"
        _log(f"📦 جاري إنشاء نسخة احتياطية مضغوطة: {zip_path.name}")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. bots_registry.json
            if REGISTRY.exists():
                zf.write(REGISTRY, arcname="bots_registry.json")
                _log("  ✅ bots_registry.json")

            # 2. manager_config.json
            if CONFIG.exists():
                zf.write(CONFIG, arcname="manager_config.json")
                _log("  ✅ manager_config.json")

            # 3. Data/ folder
            if DATA_DIR.exists():
                data_count = 0
                for item in DATA_DIR.rglob("*"):
                    if item.is_file() and not should_exclude(item):
                        rel_path = item.relative_to(BASE_DIR)
                        zf.write(item, arcname=str(rel_path).replace("\\", "/"))
                        data_count += 1
                _log(f"  ✅ Data/ ({data_count} ملفات)")

            # 4. Logs/ (آخر 7 أيام)
            if LOGS_DIR.exists():
                cutoff = datetime.now() - timedelta(days=7)
                log_count = 0
                for log_file in LOGS_DIR.glob("*.log*"):
                    if log_file.is_file() and log_file.stat().st_mtime > cutoff.timestamp():
                        rel_path = log_file.relative_to(BASE_DIR)
                        zf.write(log_file, arcname=str(rel_path).replace("\\", "/"))
                        log_count += 1
                if log_count:
                    _log(f"  ✅ Logs/ ({log_count} ملفات)")

        _log(f"🎉 تم إنشاء النسخة المضغوطة بنجاح ({zip_path.stat().st_size / 1024:.1f} KB)")
        _cleanup_old_backups()
        return zip_path

    # وضع المجلد غير المضغوط
    dest = BACKUP_DIR / backup_name
    dest.mkdir(parents=True, exist_ok=True)

    if REGISTRY.exists():
        shutil.copy2(REGISTRY, dest / "bots_registry.json")
        _log("  ✅ bots_registry.json")

    if CONFIG.exists():
        shutil.copy2(CONFIG, dest / "manager_config.json")
        _log("  ✅ manager_config.json")

    if DATA_DIR.exists():
        shutil.copytree(
            DATA_DIR,
            dest / "Data",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*-journal")
        )
        _log(f"  ✅ Data/")

    if LOGS_DIR.exists():
        logs_dest = dest / "Logs"
        logs_dest.mkdir(exist_ok=True)
        cutoff = datetime.now() - timedelta(days=7)
        log_count = 0
        for log_file in LOGS_DIR.glob("*.log*"):
            if log_file.is_file() and log_file.stat().st_mtime > cutoff.timestamp():
                shutil.copy2(log_file, logs_dest / log_file.name)
                log_count += 1
        if log_count:
            _log(f"  ✅ Logs/ ({log_count} ملفات)")

    _log(f"🎉 تم إنشاء النسخة الاحتياطية بنجاح: {dest.name}")
    _cleanup_old_backups()
    return dest


def list_backups() -> List[Path]:
    """قائمة بجميع النسخ الاحتياطية المتاحة مرتبة من الأحدث للأقدم"""
    if not BACKUP_DIR.exists():
        return []

    items = []
    for item in BACKUP_DIR.iterdir():
        if item.name.startswith("backup_") and (item.is_dir() or item.suffix == ".zip"):
            items.append(item)

    # الترتيب بالاسم هو تساوي زمنياً موثوق (الاسم يحوي طوق أيضاً بملي ثانية)
    return sorted(items, key=lambda d: d.name, reverse=True)


def _cleanup_old_backups():
    """حذف النسخ القديمة والإبقاء على آخر MAX_BACKUPS فقط"""
    backups = list_backups()
    for old in backups[MAX_BACKUPS:]:
        try:
            if old.is_dir():
                shutil.rmtree(old, ignore_errors=True)
            elif old.is_file():
                old.unlink(missing_ok=True)
            _log(f"🗑️ حُذفت نسخة قديمة: {old.name}")
        except Exception as e:
            _log(f"⚠️ تعذر حذف النسخة {old.name}: {e}")


def restore_backup(backup_path: Path) -> bool:
    """
    استعادة نسخة احتياطية من ملف ZIP أو مجلد عادي.

    Args:
        backup_path: مسار النسخة المراد استعادتها
    Returns:
        True إذا نجحت الاستعادة، False عند الفشل
    """
    if not backup_path.exists():
        _log(f"❌ مسار النسخة غير موجود: {backup_path}")
        return False

    _log(f"🔄 جاري استعادة النسخة من: {backup_path.name}")

    try:
        if backup_path.suffix == ".zip":
            with zipfile.ZipFile(backup_path, "r") as zf:
                for member in zf.namelist():
                    dest_file = BASE_DIR / member
                    # تأمين عدم الخروج من مجلد المشروع (متوافق مع Python 3.8+)
                    try:
                        dest_file.resolve().relative_to(BASE_DIR.resolve())
                    except ValueError:
                        continue

                    if member.endswith("/"):
                        dest_file.mkdir(parents=True, exist_ok=True)
                    else:
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as source, open(dest_file, "wb") as target:
                            shutil.copyfileobj(source, target)
            _log("✅ اكتملت الاستعادة بنجاح من الأرشيف المضغوط.")
            return True

        if backup_path.is_dir():
            reg_backup = backup_path / "bots_registry.json"
            if reg_backup.exists():
                shutil.copy2(reg_backup, REGISTRY)
                _log("  ✅ bots_registry.json")

            cfg_backup = backup_path / "manager_config.json"
            if cfg_backup.exists():
                shutil.copy2(cfg_backup, CONFIG)
                _log("  ✅ manager_config.json")

            data_backup = backup_path / "Data"
            if data_backup.exists():
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copytree(data_backup, DATA_DIR, dirs_exist_ok=True)
                _log("  ✅ Data/")

            _log("✅ اكتملت الاستعادة بنجاح من المجلد.")
            return True

    except Exception as e:
        _log(f"❌ خطأ أثناء الاستعادة: {e}")
        return False

    return False


def auto_backup_loop():
    """حلقة النسخ الاحتياطي التلقائي الدوري"""
    _log(f"🔄 تفعيل النسخ الاحتياطي التلقائي كل {INTERVAL_H} ساعة")
    while True:
        try:
            create_backup(compress=True)
        except Exception as e:
            _log(f"⚠️ خطأ أثناء النسخ التلقائي: {e}")
        time.sleep(INTERVAL_H * 3600)


def start_auto_backup_thread() -> threading.Thread:
    """بدء مهمة النسخ التلقائي في Thread منفصل خلفي"""
    t = threading.Thread(target=auto_backup_loop, daemon=True, name="AutoBackupThread")
    t.start()
    return t


if __name__ == "__main__":
    if "--auto" in sys.argv:
        auto_backup_loop()
    elif "--list" in sys.argv:
        backups = list_backups()
        if backups:
            print(f"\n📦 النسخ الاحتياطية المتاحة ({len(backups)}):")
            for b in backups:
                if b.is_file():
                    size_kb = b.stat().st_size / 1024
                    print(f"  • [ZIP]  {b.name:<30} ({size_kb:.1f} KB)")
                else:
                    size_kb = sum(f.stat().st_size for f in b.rglob('*') if f.is_file()) / 1024
                    print(f"  • [DIR]  {b.name:<30} ({size_kb:.1f} KB)")
        else:
            print("ℹ️ لا توجد نسخ احتياطية مسجلة حتى الآن.")
    elif "--restore" in sys.argv:
        backups = list_backups()
        if not backups:
            print("❌ لا توجد نسخ احتياطية للاستعادة.")
        else:
            target = backups[0]
            print(f"🔄 جاري استعادة أحدث نسخة: {target.name}")
            if restore_backup(target):
                print("🎉 تمت الاستعادة بنجاح.")
            else:
                print("❌ فشلت عملية الاستعادة.")
    else:
        compress_mode = "--no-zip" not in sys.argv
        created = create_backup(compress=compress_mode)
        print(f"\n✅ تمت عملية النسخ الاحتياطي: {created.name}")
