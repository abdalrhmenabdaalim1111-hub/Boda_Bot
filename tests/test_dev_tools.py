"""
tests/test_dev_tools.py — اختبارات أداة المطور dev_tools.py
"""
import pytest
import sys
import json
from pathlib import Path
import dev_tools

def test_dev_tools_status(capsys):
    """اختبار أمر status"""
    res = dev_tools.cmd_status()
    captured = capsys.readouterr().out
    assert "BODA BOT SYSTEM" in captured
    assert res["env_exists"] is True
    assert res["total_bots"] >= 30


def test_dev_tools_lint(capsys):
    """اختبار أمر lint للتأكد من خلو المشروع من أخطاء الـ syntax"""
    code = dev_tools.cmd_lint()
    captured = capsys.readouterr().out
    assert code == 0
    assert "فحص سليم" in captured


def test_dev_tools_health(capsys):
    """اختبار أمر health للتأكد من تكامل ملفات البوتات مع السجل"""
    code = dev_tools.cmd_health()
    captured = capsys.readouterr().out
    assert code == 0
    assert "جميع ملفات البوتات المسجلة متوفرة" in captured


def test_dev_tools_clean(tmp_path, monkeypatch, capsys):
    """اختبار أمر clean لحذف الكاش والملفات المؤقتة"""
    fake_dir = tmp_path / "fake_clean_env"
    fake_dir.mkdir()
    pycache = fake_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "dummy.pyc").write_text("test", encoding="utf-8")
    (fake_dir / "temp.tmp").write_text("test", encoding="utf-8")

    monkeypatch.setattr(dev_tools, "BASE_DIR", fake_dir)
    code = dev_tools.cmd_clean()
    assert code == 0
    assert not pycache.exists()
    assert not (fake_dir / "temp.tmp").exists()


def test_dev_tools_new_bot(tmp_path, monkeypatch, capsys):
    """اختبار توليد بوت جديد وتسجيله"""
    fake_bots_dir = tmp_path / "Bots_Folder"
    fake_bots_dir.mkdir()
    fake_reg = tmp_path / "bots_registry.json"
    fake_reg.write_text("[]", encoding="utf-8")
    fake_env = tmp_path / ".env"
    fake_env.write_text("", encoding="utf-8")

    monkeypatch.setattr(dev_tools, "BOTS_DIR", fake_bots_dir)
    monkeypatch.setattr(dev_tools, "REGISTRY", fake_reg)
    monkeypatch.setattr(dev_tools, "ENV_FILE", fake_env)

    success = dev_tools.cmd_new_bot("testdemo", "بوت تجريبي", "تجربة")
    assert success is True
    assert (fake_bots_dir / "bot_testdemo.py").exists()

    with open(fake_reg, "r", encoding="utf-8") as f:
        bots = json.load(f)
    assert len(bots) == 1
    assert bots[0]["id"] == "testdemo"
    assert bots[0]["file"] == "bot_testdemo.py"

    env_content = fake_env.read_text(encoding="utf-8")
    assert "BOT_TESTDEMO_TOKEN=" in env_content

