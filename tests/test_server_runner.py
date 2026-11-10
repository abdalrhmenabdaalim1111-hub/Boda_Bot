"""
tests/test_server_runner.py — اختبارات المشغّل الإنتاجي (بلا تشغيل بوتات حقيقية)
"""
import json
from pathlib import Path

import server_runner

REGISTRY = [
    {"id": "currency"},
    {"id": "qrgen"},
    {"id": "store"},
    {"id": "fun_name"},
]


# ── تحليل فلتر البوتات ───────────────────────────────────────────────────────
def test_parse_empty_means_all():
    assert server_runner.parse_bots_arg("") == []


def test_parse_all_keyword():
    assert server_runner.parse_bots_arg("all") == []
    assert server_runner.parse_bots_arg("*") == []


def test_parse_comma_space_semicolon():
    raw = "Currency, bot_qrgen;fun_name  store"
    assert server_runner.parse_bots_arg(raw) == [
        "currency", "qrgen", "fun_name", "store"]


def test_select_all_preserves_registry_order():
    selected, unknown = server_runner.select_bot_ids(REGISTRY, "")
    assert selected == ["currency", "qrgen", "store", "fun_name"]
    assert unknown == []


def test_select_subset_preserves_registry_order():
    selected, unknown = server_runner.select_bot_ids(
        REGISTRY, "fun_name,currency")
    assert selected == ["currency", "fun_name"]
    assert unknown == []


def test_select_reports_unknown_ids():
    selected, unknown = server_runner.select_bot_ids(
        REGISTRY, "currency,does_not_exist")
    assert selected == ["currency"]
    assert unknown == ["does_not_exist"]


# ── فحص التوكنات ─────────────────────────────────────────────────────────────
def test_token_env_key():
    assert server_runner.token_env_key("currency") == "BOT_CURRENCY_TOKEN"
    assert server_runner.token_env_key("fun_name") == "BOT_FUN_NAME_TOKEN"


def test_has_valid_token(monkeypatch):
    monkeypatch.setenv("BOT_CURRENCY_TOKEN",
                       "1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    assert server_runner.has_valid_token("currency") is True

    monkeypatch.setenv("BOT_QRGEN_TOKEN", "not-a-token")
    assert server_runner.has_valid_token("qrgen") is False

    monkeypatch.delenv("BOT_STORE_TOKEN", raising=False)
    assert server_runner.has_valid_token("store") is False


# ── قراءة السجل ──────────────────────────────────────────────────────────────
def test_load_registry_list(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    assert server_runner.load_registry(path) == REGISTRY


def test_load_registry_dict(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text(json.dumps({"bots": REGISTRY}), encoding="utf-8")
    assert server_runner.load_registry(path) == REGISTRY


def test_load_registry_invalid(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text("{broken", encoding="utf-8")
    assert server_runner.load_registry(path) == []


# ── إعدادات CLI ──────────────────────────────────────────────────────────────
def test_arg_parser_defaults():
    parser = server_runner.build_arg_parser()
    args = parser.parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port == int(server_runner.os.getenv("WEBHOOK_PORT", "8443"))
    assert args.polling is False
    assert args.webhook is False
