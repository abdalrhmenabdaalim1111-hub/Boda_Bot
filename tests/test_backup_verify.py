"""
tests/test_backup_verify.py — اختبارات الاستعادة الفعلية واللقطات المتسقة
"""
import shutil
import sqlite3
import zipfile
from pathlib import Path

import backup_manager


def _make_real_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, bot_name TEXT)")
        conn.execute("CREATE TABLE error_events (id INTEGER PRIMARY KEY, bot_name TEXT)")
        conn.execute("INSERT INTO users (user_id, bot_name) VALUES (1, 'currency')")
        conn.execute("INSERT INTO users (user_id, bot_name) VALUES (2, 'qrgen')")
        conn.execute("INSERT INTO error_events (bot_name) VALUES ('currency')")
        conn.commit()
    finally:
        conn.close()


def _make_zip(tmp_path: Path, members: dict) -> Path:
    zip_path = tmp_path / "backup_test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for arcname, content in members.items():
            if isinstance(content, Path):
                zf.write(content, arcname)
            else:
                zf.writestr(arcname, content)
    return zip_path


def test_verify_valid_zip(tmp_path):
    db = tmp_path / "Data" / "boda_bot.db"
    _make_real_db(db)
    zip_path = _make_zip(tmp_path, {"Data/boda_bot.db": db})

    report = backup_manager.verify_backup(zip_path)
    assert report["ok"] is True
    assert report["integrity"] == "ok"
    assert report["tables"]["users"] == 2
    assert report["tables"]["error_events"] == 1
    assert report["db_size_kb"] > 0


def test_verify_valid_directory(tmp_path):
    backup_dir = tmp_path / "backup_dir"
    db = backup_dir / "Data" / "boda_bot.db"
    _make_real_db(db)

    report = backup_manager.verify_backup(backup_dir)
    assert report["ok"] is True
    assert report["tables"]["users"] == 2


def test_verify_corrupt_database(tmp_path):
    zip_path = _make_zip(tmp_path, {"Data/boda_bot.db": b"this is not sqlite"})
    report = backup_manager.verify_backup(zip_path)
    assert report["ok"] is False
    assert report["error"]


def test_verify_zip_without_database(tmp_path):
    zip_path = _make_zip(tmp_path, {"bots_registry.json": "[]"})
    report = backup_manager.verify_backup(zip_path)
    assert report["ok"] is False
    assert "غير موجودة" in report["error"]


def test_verify_missing_file(tmp_path):
    report = backup_manager.verify_backup(tmp_path / "missing.zip")
    assert report["ok"] is False
    assert report["error"] == "النسخة غير موجودة"


def test_verify_unsupported_format(tmp_path):
    weird = tmp_path / "backup.txt"
    weird.write_text("x", encoding="utf-8")
    report = backup_manager.verify_backup(weird)
    assert report["ok"] is False


def test_verify_without_path_and_no_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_manager, "BACKUP_DIR", tmp_path / "empty_backups")
    report = backup_manager.verify_backup()
    assert report["ok"] is False
    assert "لا توجد" in report["error"]


def test_create_backup_uses_consistent_snapshot(tmp_path, monkeypatch):
    fake_base = tmp_path / "project"
    fake_data = fake_base / "Data"
    fake_data.mkdir(parents=True)
    _make_real_db(fake_data / "boda_bot.db")
    # ملفات WAL وهمية يجب ألا تدخل النسخة
    (fake_data / "boda_bot.db-wal").write_text("wal", encoding="utf-8")
    (fake_data / "boda_bot.db-shm").write_text("shm", encoding="utf-8")

    backups = fake_base / "Backups"
    logs = fake_base / "Logs"
    logs.mkdir()
    registry = fake_base / "bots_registry.json"
    registry.write_text("[]", encoding="utf-8")
    config = fake_base / "manager_config.json"
    config.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(backup_manager, "BASE_DIR", fake_base)
    monkeypatch.setattr(backup_manager, "BACKUP_DIR", backups)
    monkeypatch.setattr(backup_manager, "DATA_DIR", fake_data)
    monkeypatch.setattr(backup_manager, "LOGS_DIR", logs)
    monkeypatch.setattr(backup_manager, "REGISTRY", registry)
    monkeypatch.setattr(backup_manager, "CONFIG", config)

    zip_path = backup_manager.create_backup(compress=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "Data/boda_bot.db" in names
        assert not any(n.endswith(("-wal", "-shm")) for n in names)

    report = backup_manager.verify_backup(zip_path)
    assert report["ok"] is True
    assert report["tables"]["users"] == 2
