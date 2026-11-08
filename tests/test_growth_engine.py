"""
tests/test_growth_engine.py — اختبارات محرك النمو وشبكة الـ 5 بوتات ونظام الإحالة
"""
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

from growth_engine import GrowthEngine, get_growth_engine


@pytest.fixture
def temp_growth_engine(tmp_path):
    cfg_file = tmp_path / "test_network_config.json"
    cfg = {
        "enabled": True,
        "require_5_bots_activation": True,
        "store_bot_username": "@BodaStoreeBot",
        "store_bot_url": "https://t.me/BodaStoreeBot",
        "required_network_bots": [
            {"id": "store", "name": "متجر بودا", "username": "@BodaStoreeBot", "url": "https://t.me/BodaStoreeBot"},
            {"id": "vidload", "name": "تحميل الفيديوهات", "username": "@VidLoadXBot", "url": "https://t.me/VidLoadXBot"},
            {"id": "stickerx", "name": "صانع الملصقات", "username": "@StickerXMakerBot", "url": "https://t.me/StickerXMakerBot"},
            {"id": "cleantok", "name": "تيك توك", "username": "@CleanTokVidBot", "url": "https://t.me/CleanTokVidBot"},
            {"id": "transbot", "name": "المترجم", "username": "@TransXNowBot", "url": "https://t.me/TransXNowBot"}
        ],
        "viral_rewards": {
            "required_invites_for_vip": 3
        }
    }
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return GrowthEngine(config_file=cfg_file)


def test_network_activation_gate(temp_growth_engine):
    """اختبار ظهور بوابة التفعيل للمستخدم الجديد"""
    mock_bot = MagicMock()
    allowed, text, markup = temp_growth_engine.check_network_activation(mock_bot, user_id=999999)

    # المستخدم غير مفعّل بعد
    assert allowed is False
    assert "تفعيل الحساب" in text
    assert "متجر بودا" in text
    assert markup is not None


def test_verify_activation(temp_growth_engine):
    """اختبار نجاح التفعيل للمستخدم"""
    user_id = 888777
    assert temp_growth_engine.verify_and_activate_user(user_id) is True

    # بعد التفعيل، يجب أن يُسمح له بالدخول
    mock_bot = MagicMock()
    allowed, text, markup = temp_growth_engine.check_network_activation(mock_bot, user_id=user_id)
    assert allowed is True
    assert text is None


def test_referral_link_generation(temp_growth_engine):
    """اختبار إنشاء روابط الإحالة والمشاركة الفيروسية"""
    link = temp_growth_engine.get_referral_link("@VidLoadXBot", 12345)
    assert link == "https://t.me/VidLoadXBot?start=ref_12345"

    share_url = temp_growth_engine.get_share_url("@VidLoadXBot", 12345, "تحميل الفيديوهات")
    assert "t.me/share/url" in share_url
    assert "ref_12345" in share_url


def test_store_button_and_card(temp_growth_engine):
    """اختبار بطاقة وزر المتجر الموحد"""
    btn = temp_growth_engine.get_store_button()
    assert btn is not None
    assert "متجر التطبيقات" in btn.text
    assert "https://t.me/BodaStoreeBot" in btn.url

    card = temp_growth_engine.get_store_card_text()
    assert "Boda Apps Store" in card
    assert "35+" in card

