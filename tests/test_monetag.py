import os
import sys
import json
import pytest
from pathlib import Path

bots_dir = Path(__file__).parent.parent / "Bots_Folder"
if str(bots_dir) not in sys.path:
    sys.path.insert(0, str(bots_dir))

from ad_manager import AdManager
from database import BodaDatabase


@pytest.fixture
def ad_mgr(tmp_path):
    ads_file = tmp_path / "ads_config.json"
    monetag_file = tmp_path / "monetag_config.json"
    mgr = AdManager(config_file=ads_file, monetag_file=monetag_file)
    return mgr


def test_monetag_default_config(ad_mgr):
    assert ad_mgr.monetag_config is not None
    assert "global_default" in ad_mgr.monetag_config
    assert "bots" in ad_mgr.monetag_config


def test_set_and_get_custom_monetag_config(ad_mgr):
    ad_mgr.set_monetag_config(
        bot_id="currency",
        direct_link="https://alwingulla.com/test_currency",
        zone_id="1234567",
        format_type="direct_link",
        frequency=2,
        active=True
    )
    cfg = ad_mgr.get_monetag_config("currency")
    assert cfg["direct_link"] == "https://alwingulla.com/test_currency"
    assert cfg["zone_id"] == "1234567"
    assert cfg["frequency"] == 2
    assert ad_mgr.has_custom_monetag_ad("currency") is True
    assert ad_mgr.has_monetag_ad("currency") is True


def test_monetag_global_fallback(ad_mgr):
    ad_mgr.set_global_monetag_default(
        direct_link="https://alwingulla.com/global_fallback",
        zone_id="9999999",
        format_type="in_page_push",
        frequency=4,
        enabled=True
    )
    # bot without custom ads falls back to global
    cfg = ad_mgr.get_monetag_config("unknown_bot")
    assert cfg["direct_link"] == "https://alwingulla.com/global_fallback"
    assert cfg["zone_id"] == "9999999"
    assert cfg.get("is_global_fallback") is True
    assert ad_mgr.has_custom_monetag_ad("unknown_bot") is False
    assert ad_mgr.has_monetag_ad("unknown_bot") is True


def test_monetag_impression_and_clicks(tmp_path, ad_mgr):
    db_file = str(tmp_path / "test_ad_stats.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    db.record_ad_impression("fitcheck", "direct_link")
    db.record_ad_impression("fitcheck", "direct_link")
    db.record_ad_click("fitcheck", "direct_link")

    stats = db.get_ad_stats("fitcheck")
    assert len(stats) >= 1
    assert stats[0]["impressions"] == 2
    assert stats[0]["clicks"] == 1
    assert stats[0]["ctr_percent"] == 50.0

    summary = db.get_ad_summary()
    assert summary["total_impressions"] == 2
    assert summary["total_clicks"] == 1
    assert summary["overall_ctr"] == 50.0


# ── تتبع نقرات Monetag عبر رابط بوت المتجر ──────────────────────────────────

def test_build_ad_click_url(ad_mgr):
    from ad_manager import STORE_BOT_USERNAME, AD_CLICK_PREFIX
    ad_mgr.set_monetag_config("currency", direct_link="https://alwingulla.com/x")
    assert ad_mgr.build_ad_click_url("currency") == \
        f"https://t.me/{STORE_BOT_USERNAME}?start={AD_CLICK_PREFIX}currency"
    # بوت بلا شفرة (ولا عامة) → لا رابط
    assert ad_mgr.build_ad_click_url("no_such_bot") == ""


def test_parse_ad_click_payload():
    from ad_manager import parse_ad_click_payload
    assert parse_ad_click_payload("/start adclick_currency") == "currency"
    assert parse_ad_click_payload("/start adclick_fit_check") == "fit_check"
    assert parse_ad_click_payload("/start") == ""
    assert parse_ad_click_payload("/start hello") == ""
    assert parse_ad_click_payload("/start adclick_BAD!!") == ""
    assert parse_ad_click_payload("") == ""


def test_resolve_ad_click_records_click(tmp_path, ad_mgr):
    db_file = str(tmp_path / "click_stats.db")
    db = BodaDatabase(db_file)
    BodaDatabase._instance = db

    ad_mgr.set_monetag_config("qrgen", direct_link="https://alwingulla.com/qr")
    info = ad_mgr.resolve_ad_click("qrgen")
    assert info is not None
    assert info["direct_link"] == "https://alwingulla.com/qr"
    assert info["bot_id"] == "qrgen"

    stats = db.get_ad_stats("qrgen")
    assert len(stats) == 1
    assert stats[0]["clicks"] == 1


def test_resolve_ad_click_unknown_returns_none(ad_mgr):
    assert ad_mgr.resolve_ad_click("no_such_bot") is None
