# -*- coding: utf-8 -*-
"""renderer.py — رسم الاسم على القالب بجودة عالية (Pillow + تشكيل عربي).

الاعتماديات: pillow + arabic-reshaper + python-bidi (كلها حرة ومثبتة).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_ARABIC = True
except Exception:  # fallback آمن
    _HAS_ARABIC = False

ROOT = Path(__file__).resolve().parents[2]


def _font_path(preferred: str = "") -> str:
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates += [
        str(ROOT / "assets" / "fonts" / "Cairo.ttf"),
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise RuntimeError("لا توجد خطوط TTF متاحة للرسم")


def _shape(text: str) -> str:
    """تشكيل عربي + ترتيب RTL، والإنجليزي يبقى كما هو."""
    if not _HAS_ARABIC:
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def _fit_font(draw: ImageDraw.ImageDraw, text: str, box: Tuple[int, int, int, int],
              font_path: str, start_size: int, color, min_size: int = 10) -> ImageFont.FreeTypeFont:
    x, y, w, h = box
    size = int(start_size)
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        bb = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        if tw <= max(1, w - 6) and th <= max(1, h - 6):
            return font
        size -= 1
    return ImageFont.truetype(font_path, min_size)


def _hex_color(value, default=(0, 0, 0)) -> Tuple[int, int, int]:
    """قبل '#RRGGBB' أو [r,g,b]."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(x) for x in value)
    s = str(value or "").lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return default


def render_card(template: Dict, name: str, name2: str = "",
                watermark_text: str = "@BodaNameCardsBot",
                draw_watermark: bool = True) -> bytes:
    """يرجع صورة PNG جاهزة للإرسال."""
    image_path = Path(template.get("image_path") or "")
    if not image_path.exists():
        raise FileNotFoundError("صورة القالب غير موجودة")

    img = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    font_path = _font_path(str(template.get("font") or ""))
    color = _hex_color(template.get("color"), (20, 20, 20))

    def place(text: str, box_key: str, default_box):
        if not text:
            return
        box = template.get(box_key) or default_box
        try:
            box = tuple(int(v) for v in box)
        except Exception:
            box = default_box
        if len(box) != 4:
            box = default_box
        shaped = _shape(text)
        font = _fit_font(draw, shaped, box, font_path,
                         int(template.get("font_size", 56)), color)
        bb = draw.textbbox((0, 0), shaped, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        x, y, w, h = box
        align = str(template.get("align", "center"))
        if align == "right":
            tx = x + w - tw - 3
        elif align == "left":
            tx = x + 3
        else:
            tx = x + (w - tw) / 2
        ty = y + (h - th) / 2 - bb[1]
        draw.text((tx, ty), shaped, font=font, fill=color)

    w, h = img.size
    place(name, "name_box", (int(w*0.1), int(h*0.35), int(w*0.8), int(h*0.2)))
    if name2 and template.get("two_names"):
        place(name2, "name2_box", (int(w*0.1), int(h*0.58), int(w*0.8), int(h*0.16)))

    if draw_watermark:
        wm = _shape(watermark_text)
        wm_font = ImageFont.truetype(font_path, max(12, int(w * 0.022)))
        wm_bb = draw.textbbox((0, 0), wm, font=wm_font)
        draw.text((w - (wm_bb[2]-wm_bb[0]) - 12, h - (wm_bb[3]-wm_bb[1]) - 16),
                  wm, font=wm_font, fill=(120, 120, 120, 255))

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
