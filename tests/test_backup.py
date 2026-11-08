"""
tests/test_backup.py — اختبارات نظام النسخ الاحتياطي والضغط والاستعادة
"""
import pytest
import zipfile
import shutil
from pathlib import Path
import backup_manager

@pytest.fixture
def temp_backup_env(tmp_path, monkeypatch):
    """إعداد بيئة عمل وهمية لاختبار النسخ الاحتياطي بدون المساس بالملفات الحقيقية"""
    fake_base = tmp_path / "project"
    fake_base.mkdir()

    fake_backups = fake_base / "Backups"
    fake_data = fake_base / "Data"
    fake_data.mkdir()
    (fake_data / "test_db.sqlite").write_text("dummy database content", encoding="utf-8")

    fake_logs = fake_base / "Logs"
    fake_logs.mkdir()
    (fake_logs / "bot.log").write_text("log line 1\nlog line 2", encoding="utf-8")

    fake_registry = fake_base / "bots_registry.json"
    fake_registry.write_text('{"bots": []}', encoding="utf-8")

    fake_config = fake_base / "manager_config.json"
    fake_config.write_text('{"auto_restart": true}', encoding="utf-8")

    # تغيير المسارات في backup_manager
    monkeypatch.setattr(backup_manager, "BASE_DIR", fake_base)
    monkeypatch.setattr(backup_manager, "BACKUP_DIR", fake_backups)
    monkeypatch.setattr(backup_manager, "DATA_DIR", fake_data)
    monkeypatch.setattr(backup_manager, "LOGS_DIR", fake_logs)
    monkeypatch.setattr(backup_manager, "REGISTRY", fake_registry)
    monkeypatch.setattr(backup_manager, "CONFIG", fake_config)

    return {
        "base": fake_base,
        "backups": fake_backups,
        "data": fake_data,
        "logs": fake_logs,
        "registry": fake_registry,
        "config": fake_config
    }


def test_create_compressed_backup(temp_backup_env):
    """اختبار إنشاء نسخة احتياطية مضغوطة zip"""
    res = backup_manager.create_backup(compress=True)
    assert res.exists()
    assert res.suffix == ".zip"
    assert zipfile.is_zipfile(res)

    with zipfile.ZipFile(res, "r") as zf:
        names = zf.namelist()
        assert "bots_registry.json" in names
        assert "manager_config.json" in names
        assert any("Data/test_db.sqlite" in n for n in names)
        assert any("Logs/bot.log" in n for n in names)


def test_create_uncompressed_backup(temp_backup_env):
    """اختبار إنشاء نسخة احتياطية كمجلد عادي"""
    res = backup_manager.create_backup(compress=False)
    assert res.exists()
    assert res.is_dir()
    assert (res / "bots_registry.json").exists()
    assert (res / "manager_config.json").exists()
    assert (res / "Data" / "test_db.sqlite").exists()


def test_list_backups(temp_backup_env):
    """اختبار استعراض النسخ المتوفرة"""
    assert len(backup_manager.list_backups()) == 0
    b1 = backup_manager.create_backup(compress=True)
    b2 = backup_manager.create_backup(compress=False)

    backups = backup_manager.list_backups()
    assert len(backups) == 2
    assert b2 in backups
    assert b1 in backups


def test_cleanup_max_backups(temp_backup_env, monkeypatch):
    """اختبار حذف النسخ القديمة بعد تجاوز الحد الأقصى"""
    monkeypatch.setattr(backup_manager, "MAX_BACKUPS", 2)
    b1 = backup_manager.create_backup(compress=True)
    b2 = backup_manager.create_backup(compress=True)
    b3 = backup_manager.create_backup(compress=True)

    backups = backup_manager.list_backups()
    assert len(backups) == 2
    assert not b1.exists()
    assert b3.exists()


def test_restore_zip_backup(temp_backup_env):
    """اختبار استعادة نسخة احتياطية من ملف zip"""
    # إنشاء نسخة أولاً
    zip_path = backup_manager.create_backup(compress=True)

    # تعديل الملفات الأصلية
    temp_backup_env["registry"].write_text('{"modified": true}', encoding="utf-8")
    (temp_backup_env["data"] / "test_db.sqlite").write_text("corrupted", encoding="utf-8")

    # استعادة
    success = backup_manager.restore_backup(zip_path)
    assert success is True
    assert temp_backup_env["registry"].read_text(encoding="utf-8") == '{"bots": []}'
    assert (temp_backup_env["data"] / "test_db.sqlite").read_text(encoding="utf-8") == "dummy database content"


def test_restore_dir_backup(temp_backup_env):
    """اختبار استعادة نسخة احتياطية من مجلد عادي"""
    dir_path = backup_manager.create_backup(compress=False)

    # تعديل الملفات
    temp_backup_env["config"].write_text('{"auto_restart": false}', encoding="utf-8")

    # استعادة
    success = backup_manager.restore_backup(dir_path)
    assert success is True
    assert temp_backup_env["config"].read_text(encoding="utf-8") == '{"auto_restart": true}'


def test_restore_nonexistent_backup(temp_backup_env):
    """اختبار محاولة استعادة ملف غير موجود"""
    fake_path = temp_backup_env["backups"] / "backup_not_found.zip"
    assert backup_manager.restore_backup(fake_path) is False

