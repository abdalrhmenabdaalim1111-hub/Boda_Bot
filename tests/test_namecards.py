# -*- coding: utf-8 -*-
"""اختبارات بوت بطاقات بالاسم."""
import base64
import hashlib
import hmac
import io
import json
import sys
import time
import urllib.parse
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).parent.parent
for _p in (str(ROOT), str(ROOT / "Bots_Folder")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from Bots_Folder.namecards import renderer, security, store  # noqa: E402

TOKEN = "123456789:TEST_TOKEN_FOR_NAMECARDS"


def make_init_data(user_id=12345, first="Test"):
    user = json.dumps({"id": user_id, "first_name": first}, separators=(",", ":"))
    data = {"user": user, "auth_date": str(int(time.time())), "query_id": "AA-test"}
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(data)


@pytest.fixture()
def template(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TEMPLATES_DIR", tmp_path / "templates")
    d = store.templates_dir()
    img = Image.new("RGBA", (500, 300), (250, 240, 220, 255))
    img.save(d / "t1.png")
    meta = {
        "id": "t1", "name": "قالب اختبار", "image": "t1.png", "active": True,
        "two_names": False, "watermark": True, "font_size": 56, "color": "#141414",
        "align": "center", "name_box": [20, 90, 460, 100],
        "name2_box": [20, 200, 460, 80],
    }
    (d / "t1.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return store.get_template("t1")


# ── الرسم ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,name2", [
    ("أحمد", ""),
    ("محمد عبد الرحمن بن سلطان القحطاني العتيبي", ""),   # اسم عربي طويل
    ("Ahmed Mohamed", ""),                                  # إنجليزي
    ("أحمد", "سارة"),                                        # اسمان
])
def test_render_works(template, name, name2):
    tpl = dict(template)
    tpl["two_names"] = bool(name2)
    png = renderer.render_card(tpl, name, name2)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    im = Image.open(io.BytesIO(png))
    assert im.size == (500, 300)


# ── initData ─────────────────────────────────────────────────────────────────
def test_valid_init_data():
    data = make_init_data()
    assert security.validate_init_data(data, TOKEN)["id"] == 12345


def test_forged_init_data():
    data = make_init_data()
    forged = data.replace("hash=", "hash=x")
    assert security.validate_init_data(forged, TOKEN) is None
    assert security.validate_init_data(data, "WRONG_TOKEN") is None


def test_rate_limit():
    limiter = security.RateLimiter(limit=2, window=60)
    assert limiter.allow("u") is True
    assert limiter.allow("u") is True
    assert limiter.allow("u") is False


def test_sanitize_name():
    assert security.sanitize_name("أح\u200bمد\x00!") == "أحمد!"
    assert len(security.sanitize_name("أ" * 60)) == 30


# ── حفظ/حذف القالب ──────────────────────────────────────────────────────────
def test_template_save_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TEMPLATES_DIR", tmp_path / "tpl")
    d = store.templates_dir()
    im = Image.new("RGB", (100, 100), (255, 0, 0))
    im.save(d / "x.png")
    (d / "x.json").write_text(json.dumps({"id": "x", "name": "X", "image": "x.png"}),
                              encoding="utf-8")
    assert store.get_template("x")["name"] == "X"
    assert any(t["id"] == "x" for t in store.list_templates())
    (d / "x.png").unlink()
    (d / "x.json").unlink()
    assert store.get_template("x") == {}
