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


class TestParseTokenEntries:
    """اختبارات دالة تحليل أسطر التوكنات بالجملة"""

    KNOWN = {"cryptorate", "currency", "qrgen"}
    UMAP = {"cryptoratexbot": "cryptorate", "bodacurrencybot": "currency"}

    def _parse(self, text):
        return dev_tools.parse_token_entries(text, self.KNOWN, self.UMAP)

    def test_username_token_format(self):
        entries = self._parse("@CryptoRateXBot 123456789:AAHabcdefghijk12345")
        assert entries[0][0] == "cryptorate"
        assert entries[0][1] == "123456789:AAHabcdefghijk12345"

    def test_env_key_format(self):
        entries = self._parse("BOT_CURRENCY_TOKEN=123456789:AAHabcdefghijk12345")
        assert entries[0][0] == "currency"

    def test_plain_bot_id_format(self):
        entries = self._parse("qrgen=123456789:AAHabcdefghijk12345")
        assert entries[0][0] == "qrgen"

    def test_bare_token_has_no_id(self):
        entries = self._parse("123456789:AAHabcdefghijk12345")
        assert entries[0][0] is None
        assert entries[0][1] == "123456789:AAHabcdefghijk12345"

    def test_skips_comments_and_blank_lines(self):
        entries = self._parse("# تعليق\n\n@CryptoRateXBot 123456789:AAHabcdefghijk12345")
        assert len(entries) == 1

    def test_invalid_line_flagged_without_token(self):
        entries = self._parse("سطر ملوش توكن")
        assert entries[0] == (None, None, "سطر ملوش توكن")

    def test_unknown_username_maps_to_none(self):
        entries = self._parse("@SomeOtherBot 123456789:AAHabcdefghijk12345")
        assert entries[0][0] is None


class TestTokenHelpers:
    """اختبارات دوال التوكنات المساعدة"""

    def test_is_token_format_valid(self):
        assert dev_tools._is_token_format("1234567890:AAHabcdefghijk123456") is True

    def test_is_token_format_rejects_placeholder(self):
        assert dev_tools._is_token_format("ضع_التوكن_هنا") is False

    def test_is_token_format_rejects_short_or_empty(self):
        assert dev_tools._is_token_format("") is False
        assert dev_tools._is_token_format("12345:short") is False

    def test_read_env_tokens_filters_placeholders(self, tmp_path, monkeypatch):
        fake_env = tmp_path / ".env"
        fake_env.write_text(
            "# تعليق\n"
            "BOT_GOOD_TOKEN=111111111:AAHabcdefghijk12345\n"
            "BOT_BAD_TOKEN=ضع_التوكن_هنا\n"
            "OTHER_KEY=قيمة\n",
            encoding="utf-8")
        monkeypatch.setattr(dev_tools, "ENV_FILE", fake_env)

        tokens = dev_tools._read_env_tokens()
        assert "BOT_GOOD_TOKEN" in tokens
        assert "BOT_BAD_TOKEN" not in tokens
        assert len(tokens) == 1

    def test_cmd_tokens_prints_summary(self, capsys):
        code = dev_tools.cmd_tokens()
        captured = capsys.readouterr().out
        assert code == 0
        assert "الإجمالي" in captured
        assert "ينتظر توكن" in captured

