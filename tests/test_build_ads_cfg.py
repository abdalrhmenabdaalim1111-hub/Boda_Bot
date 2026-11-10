"""
tests/test_build_ads_cfg.py — اختبارات حقن إعلانات Monetag في صفحات التطبيقات
تتحقق من: التخصيص لكل بوت + الـ fallback العام + Zone ID + غياب الإعلانات.
"""
import json
import sys
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_mini_apps", ROOT / "tools" / "build_mini_apps.py")
build_mini_apps = importlib.util.module_from_spec(_spec)
sys.modules["build_mini_apps"] = build_mini_apps
_spec.loader.exec_module(build_mini_apps)


def _setup(tmp_path, monkeypatch, ads: dict, monetag: dict):
    data = tmp_path / "Data"
    data.mkdir(exist_ok=True)
    (data / "ads_config.json").write_text(json.dumps(ads), encoding="utf-8")
    (data / "monetag_config.json").write_text(json.dumps(monetag), encoding="utf-8")
    monkeypatch.setattr(build_mini_apps, "DATA", data)
    monkeypatch.setattr(build_mini_apps, "ADS", data / "ads_config.json")
    return data


def test_custom_monetag_beats_global(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch,
           ads={"footer_ad": {"enabled": True, "frequency": 4, "text": "<b>AD</b>"}},
           monetag={
               "global_default": {"enabled": True, "direct_link": "https://m/global",
                                  "frequency": 5},
               "bots": {"alpha": {"has_custom_ads": True, "active": True,
                                   "direct_link": "https://m/alpha", "frequency": 2}},
           })
    cfg = build_mini_apps.build_ads_cfg("alpha")
    assert cfg["sponsor"]["url"] == "https://m/alpha"      # الشفرة الخاصة تتفوق
    assert cfg["has_monetag"] is True
    assert cfg["banner"]["html"] == "<b>AD</b>"
    assert cfg["every"] == 4                               # تردد الفوتر الأعلى


def test_global_fallback_for_other_bots(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch,
           ads={"footer_ad": {"enabled": False}},
           monetag={
               "global_default": {"enabled": True, "direct_link": "https://m/global",
                                  "frequency": 5},
               "bots": {},
           })
    cfg = build_mini_apps.build_ads_cfg("beta")
    assert cfg["sponsor"]["url"] == "https://m/global"
    assert cfg["every"] == 5
    assert cfg["banner"] is None


def test_zone_id_generates_script_url(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch,
           ads={},
           monetag={
               "global_default": {"enabled": True, "zone_id": "123456",
                                  "direct_link": "", "frequency": 3},
               "bots": {},
           })
    cfg = build_mini_apps.build_ads_cfg("gamma")
    assert cfg["monetag_script"] == "https://thubanoa.com/1?z=123456"
    assert cfg["monetag_zone"] == "123456"
    assert cfg["has_monetag"] is True
    assert cfg["sponsor"] is None       # لا يوجد direct link


def test_store_button_fallback_sponsor(tmp_path, monkeypatch):
    """عند غياب Monetag: زر المتجر يعمل كراعٍ احتياطي"""
    _setup(tmp_path, monkeypatch,
           ads={"button_ad": {"enabled": True, "button_text": "🏪 المتجر",
                              "url": "https://t.me/BodaStoreeBot"}},
           monetag={"global_default": {"enabled": False}, "bots": {}})
    cfg = build_mini_apps.build_ads_cfg("delta")
    assert cfg["sponsor"]["url"] == "https://t.me/BodaStoreeBot"
    assert cfg["has_monetag"] is False


def test_no_ads_at_all(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, ads={},
           monetag={"global_default": {"enabled": True}, "bots": {}})
    cfg = build_mini_apps.build_ads_cfg("epsilon")
    assert cfg["sponsor"] is None
    assert cfg["banner"] is None
    assert cfg["every"] == 3
    assert cfg["monetag_script"] == ""
    assert cfg["has_monetag"] is False
