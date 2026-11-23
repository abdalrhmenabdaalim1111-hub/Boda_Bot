# -*- coding: utf-8 -*-
"""اختبارات الكشف التلقائي عن منطقة الكتابة."""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).parent.parent
for _p in (str(ROOT), str(ROOT / "Bots_Folder")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from Bots_Folder.namecards import detect, store, api  # noqa: E402


def make_clean(path, size=(800, 1000)):
    im = Image.new("RGB", size, (235, 225, 210))
    d = ImageDraw.Draw(im)
    # تفاصيل في الثلث الأعلى فقط
    for i in range(300):
        x = i % size[0]
        y = (i * 7) % int(size[1] * 0.32)
        d.rectangle([x, y, x + 6, y + 6], fill=(30, 30, 30))
    im.save(path)
    return im


def make_crowded(path, size=(800, 1000)):
    rng = np.random.default_rng(3)
    arr = rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(arr).save(path)


@pytest.mark.parametrize("size", [(800, 1000), (1080, 1350), (1080, 1920), (800, 800)])
def test_empty_area_detected(tmp_path, size):
    p = tmp_path / "clean.png"
    make_clean(p, size)
    r = detect.suggest_slots(p)
    assert r["name"] is not None
    assert r["confidence"] >= 0.5
    assert 0 <= r["name"]["x"] <= 1 and 0 <= r["name"]["w"] <= 1
    # المنطقة المقترحة تحت الثلث الأعلى المزدحم
    assert r["name"]["y"] >= 0.25
    assert r["text_color"].startswith("#")


def test_crowded_low_confidence(tmp_path):
    p = tmp_path / "crowded.png"
    make_crowded(p)
    r = detect.suggest_slots(p)
    assert r["confidence"] < 0.5
    assert "warning" in r


def test_sizes_and_transparency(tmp_path):
    p = tmp_path / "alpha.png"
    im = Image.new("RGBA", (720, 960), (235, 225, 210, 255))
    im.save(p)
    r = detect.suggest_slots(p)
    assert r["name"] is not None


def test_apply_to_meta_keeps_format(tmp_path):
    p = tmp_path / "clean.png"
    make_clean(p)
    r = detect.suggest_slots(p)
    meta = detect.apply_to_meta({"id": "x", "image": "clean.png", "active": True,
                                 "name_box": [0, 0, 10, 10]}, r, (800, 1000))
    assert isinstance(meta["name_box"], list) and len(meta["name_box"]) == 4
    assert meta["name_box"][2] > 0


def test_api_rejects_non_image_and_bad_name(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TEMPLATES_DIR", tmp_path)
    monkeypatch.setattr(api, "ADMIN_KEY", "testkey")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    headers = {"X-API-Key": "testkey"}
    status, payload, _ = api.dispatch("POST", "/admin/detect", {},
                                      {"filename": "bad.png"}, headers)
    assert status == 400
    status, payload, _ = api.dispatch("POST", "/admin/detect", {},
                                      {"filename": "../../etc/passwd"}, headers)
    assert status == 400


def test_api_detect_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TEMPLATES_DIR", tmp_path)
    monkeypatch.setattr(api, "ADMIN_KEY", "testkey")
    p = tmp_path / "ok.png"
    make_clean(p)
    status, payload, _ = api.dispatch("POST", "/admin/detect", {},
                                      {"filename": "ok.png"},
                                      {"X-API-Key": "testkey"})
    assert status == 200
    assert payload["ok"] is True
    assert payload["suggestion"]["name"] is not None
