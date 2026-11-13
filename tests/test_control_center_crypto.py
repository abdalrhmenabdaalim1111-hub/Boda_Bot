"""
tests/test_control_center_crypto.py — اختبارات تشفير التوكنات والقناع

تغطي:
• تشفير/فك التشفير (عند توفر مكتبة cryptography)
• السلوك الاحتياطي عند غياب المكتبة أو المفتاح
• قناع التوكن (masking)
• كشف صيغة توكن تيليجرام
• عدم ظهور التوكن الكامل في أي استجابة
"""

import pytest

from tests.cc_fixtures import ROOT, BOTS_DIR  # noqa: F401  (path bootstrap)

from control_center import crypto

SAMPLE_TOKEN = "1234567890:AAF-fakeTokenValue_1234567890abcdefGHI"


def test_mask_token_hides_the_secret():
    """القناع يخفي الجزء الأوسط من التوكن"""
    masked = crypto.mask_token(SAMPLE_TOKEN)
    assert SAMPLE_TOKEN not in masked
    assert masked.startswith("1234")
    assert masked.endswith("fGHI")
    assert "•" in masked
    assert "fakeTokenValue" not in masked


def test_mask_token_handles_edge_cases():
    """القناع يتعامل مع القيم الفارغة والقصيرة"""
    assert crypto.mask_token("") == ""
    assert crypto.mask_token("abc") == "•" * 8
    assert "aaaa" in crypto.mask_token("aaaaaaaaaaaaaaaaaaaa")


def test_token_hint_is_short():
    """التلميح قصير ولا يكشف التوكن"""
    assert crypto.token_hint(SAMPLE_TOKEN) == "fGHI"
    assert crypto.token_hint("") == ""


def test_looks_like_token():
    """كشف صيغة توكن تيليجرام"""
    assert crypto.looks_like_token(SAMPLE_TOKEN) is True
    assert crypto.looks_like_token("nope") is False
    assert crypto.looks_like_token("") is False
    assert crypto.looks_like_token("12345:short") is False


def test_env_var_name_and_read():
    """اسم متغير البيئة يتبع الاصطلاح BOT_<ID>_TOKEN"""
    assert crypto.env_var_name("currency") == "BOT_CURRENCY_TOKEN"
    assert crypto.env_var_name("bot_currency") == "BOT_CURRENCY_TOKEN"


def test_secret_box_roundtrip():
    """التشفير ثم فك التشفير يعيد النص الأصلي"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")

    box = crypto.SecretBox(Fernet.generate_key().decode("ascii"))
    assert box.available is True

    blob = box.encrypt(SAMPLE_TOKEN)
    assert SAMPLE_TOKEN not in blob
    assert blob.startswith("enc:v1:")
    assert box.decrypt(blob) == SAMPLE_TOKEN


def test_secret_box_without_key_is_unavailable():
    """بدون مفتاح لا تكون التشفير متاحاً"""
    box = crypto.SecretBox("")
    assert box.available is False
    with pytest.raises(RuntimeError):
        box.encrypt(SAMPLE_TOKEN)
    assert box.encrypt_or_none(SAMPLE_TOKEN) is None


def test_secret_box_auto_generates_and_persists_a_key(tmp_path, monkeypatch):
    """عند غياب المفتاح يُولَّد مفتاح جديد ويُحفظ خارج المستودع"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")

    from control_center import config
    key_file = tmp_path / ".secret_key"
    monkeypatch.setattr(config, "SECRET_KEY_FILE", key_file)
    monkeypatch.delenv("BODA_SECRET_KEY", raising=False)
    crypto.reset_secret_box()
    try:
        box = crypto.SecretBox()
        assert box.available is True
        assert key_file.exists()
        blob = box.encrypt(SAMPLE_TOKEN)
        assert box.decrypt(blob) == SAMPLE_TOKEN

        # A second instance must reuse the persisted key.
        other = crypto.SecretBox()
        assert other.decrypt(blob) == SAMPLE_TOKEN
    finally:
        crypto.reset_secret_box()


def test_secret_box_rejects_plain_values():
    """فك التشفير يرفض القيم غير المشفّرة"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")

    box = crypto.SecretBox(Fernet.generate_key().decode("ascii"))
    with pytest.raises(ValueError):
        box.decrypt("not-an-encrypted-blob")


def test_encrypt_or_none_never_leaks_plaintext():
    """encrypt_or_none لا تُعيد النص الصريح أبداً"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")

    box = crypto.SecretBox(Fernet.generate_key().decode("ascii"))
    blob = box.encrypt_or_none(SAMPLE_TOKEN)
    assert blob is not None
    assert SAMPLE_TOKEN not in blob
