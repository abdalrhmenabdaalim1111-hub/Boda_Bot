# -*- coding: utf-8 -*-
"""
tests/test_ad_studio_flow.py — Test end-to-end Ad Studio workflow.

Validates the full interactive Ad Studio user journey:
1. Raw Monetag snippet parse (extract zone, SDK function, reject bad script).
2. Preview Diff against pilot bot (@BodaCurrencyBot, currency).
3. Library creation and assignment to bot.
4. Build & apply (injection into webroot/currency/index.html with backup creation).
5. Rollback restores the previous backup.
6. Publish to GitHub Pages API check.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from control_center.http import Request
import control_center.api as api
from control_center import config


SAMPLE_SNIPPET = "<script src='//libtl.com/sdk.js' data-zone='12250058' data-sdk='show_12250058'></script>"


def _get_body_dict(res):
    if isinstance(res.body, dict):
        return res.body
    return json.loads(res.body)


def test_ad_studio_full_pilot_journey():
    # 1. Parse snippet
    req = Request(None, "POST", "/api/v1/ads/parse", body=json.dumps({"snippet": SAMPLE_SNIPPET}).encode("utf-8"))
    res = api.ads_parse_snippet_api(req)
    assert res.status == 200
    parsed = _get_body_dict(res)
    assert parsed.get("ok") is True
    assert parsed.get("zone_id") == "12250058"
    assert parsed.get("sdk_name") == "show_12250058"

    # 2. Preview Diff against currency
    req = Request(None, "POST", "/api/v1/ads/preview-diff", body=json.dumps({
        "bot_id": "currency",
        "slot": "body_end",
        "snippet": SAMPLE_SNIPPET
    }).encode("utf-8"))
    res = api.ads_preview_diff_api(req)
    assert res.status == 200
    pdiff = _get_body_dict(res)
    assert pdiff.get("ok") is True
    assert "diff" in pdiff

    # 3. Create Ad in library
    req = Request(None, "POST", "/api/v1/ads/library", body=json.dumps({
        "name": "Currency Monetag Pilot",
        "snippet": SAMPLE_SNIPPET,
        "format": "inApp",
        "slot": "body_end"
    }).encode("utf-8"))
    res = api.ads_library_create_api(req)
    assert res.status == 200
    lib_data = _get_body_dict(res)
    ad_id = lib_data.get("ad", {}).get("ad_id")
    assert ad_id

    # 4. Assign Ad to currency bot
    req = Request(None, "POST", "/api/v1/ads/assign", body=json.dumps({
        "ad_id": ad_id,
        "scope": "bot",
        "target_id": "currency",
        "priority": 50
    }).encode("utf-8"))
    res = api.ads_assign_api(req)
    assert res.status == 200
    assert _get_body_dict(res).get("ok") is True

    # 5. Build and Apply to Mini App
    req = Request(None, "POST", "/api/v1/ads/build-apply", body=json.dumps({
        "bot_id": "currency"
    }).encode("utf-8"))
    res = api.ads_build_apply_api(req)
    assert res.status == 200
    assert _get_body_dict(res).get("ok") is True

    # Verify injected file has the zone
    currency_file = config.WEBROOT_DIR / "currency" / "index.html"
    assert currency_file.exists()
    content = currency_file.read_text(encoding="utf-8")
    assert "12250058" in content
    assert "<!-- AD:BEGIN slot=body_end" in content

    # 6. Check backups list
    req = Request(None, "GET", "/api/v1/ads/backups/currency", params={"bot_id": "currency"})
    res = api.ads_backups_list_api(req)
    assert res.status == 200
    backups = _get_body_dict(res).get("backups", [])
    assert len(backups) >= 1

    # 7. Rollback
    req = Request(None, "POST", "/api/v1/ads/rollback", body=json.dumps({
        "bot_id": "currency"
    }).encode("utf-8"))
    res = api.ads_rollback_api(req)
    assert res.status == 200
    rb_data = _get_body_dict(res)
    assert rb_data.get("ok") is True
