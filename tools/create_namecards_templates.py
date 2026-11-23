# -*- coding: utf-8 -*-
"""توليد قوالب جاهزة لبوت البطاقات (خلفيات زخرفية بدون نص) — Pillow فقط."""
from __future__ import annotations

import json
import math
import random
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Data" / "namecards" / "templates"
ASSETS = ROOT / "assets" / "namecards_templates"

VARIANTS = [
    {"id": "sand_gold", "name": "رملي ذهبي", "accent": (70, 50, 40), "flower": (220, 150, 40)},
    {"id": "sand_rose", "name": "رملي وردي", "accent": (90, 45, 55), "flower": (210, 110, 140)},
    {"id": "sand_blue", "name": "رملي أزرق", "accent": (45, 70, 95), "flower": (120, 150, 190)},
    {"id": "sand_green", "name": "رملي أخضر", "accent": (50, 80, 55), "flower": (130, 165, 110)},
]


def textured_base(size: int, tint=(214, 198, 180)) -> Image.Image:
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 9, (size, size, 1))
    arr = np.zeros((size, size, 3), dtype=np.float32)
    for i, c in enumerate(tint):
        arr[:, :, i] = np.clip(c + noise[:, :, 0], 0, 255)
    img = Image.fromarray(arr.astype("uint8"), "RGB")
    return img.filter(ImageFilter.GaussianBlur(0.4))


def draw_vine(dr: ImageDraw.ImageDraw, size: int, color):
    # ساق رئيسي منخفض مع تفرعات
    points = []
    for i in range(0, 101):
        t = i / 100
        x = 30 + t * (size * 0.33)
        y = size * 0.74 - 55 * math.sin(t * math.pi) - 12 * math.sin(t * 5 * math.pi)
        points.append((int(x), int(y)))
    dr.line(points, fill=color, width=5, joint="curve")
    for i in range(8, 96, 10):
        x, y = points[i]
        a = (i / 100) * math.pi
        for s in (-1, 1):
            ex = x + 34 * math.cos(a + s * 0.9)
            ey = y - 30 * math.sin(a + s * 0.9)
            dr.ellipse([min(x, ex), min(y, ey), max(x, ex), max(y, ey)],
                       outline=color, width=3)
            dr.line([x, y, ex, ey], fill=color, width=2)


def draw_butterfly(dr: ImageDraw.ImageDraw, x, y, s, color):
    # أجنحة علوية/سفلية + جسم + قرون
    dr.ellipse([x - 16*s, y - 22*s, x - 2*s, y - 2*s], outline=color, width=max(1, int(3*s)))
    dr.ellipse([x + 2*s, y - 22*s, x + 16*s, y - 2*s], outline=color, width=max(1, int(3*s)))
    dr.ellipse([x - 12*s, y, x - 2*s, y + 15*s], outline=color, width=max(1, int(2*s)))
    dr.ellipse([x + 2*s, y, x + 12*s, y + 15*s], outline=color, width=max(1, int(2*s)))
    dr.line([x, y - 12*s, x, y + 15*s], fill=color, width=max(1, int(3*s)))
    dr.arc([x - 2*s, y - 24*s, x + 2*s, y - 14*s], 180, 360, fill=color, width=1)


def draw_flowers(dr: ImageDraw.ImageDraw, size, color, flower):
    # أزهار صغيرة حول الحافة العليا
    for cx, cy, r in [(size*0.62, size*0.34, 26), (size*0.70, size*0.29, 18),
                      (size*0.66, size*0.40, 14)]:
        for k in range(8):
            a = 2 * math.pi * k / 8
            px, py = cx + r*0.75*math.cos(a), cy + r*0.75*math.sin(a)
            dr.ellipse([px-r*0.45, py-r*0.45, px+r*0.45, py+r*0.45],
                       outline=flower, width=3)
        dr.ellipse([cx-8, cy-8, cx+8, cy+8], fill=color)


def make(variant: dict) -> Image.Image:
    size = 1024
    img = textured_base(size)
    dr = ImageDraw.Draw(img)
    color = variant["accent"]

    # إطار خفيف
    dr.rectangle([18, 18, size-18, size-18], outline=(*color, 90), width=2)

    # زخرفة جانبية + فراشات + أزهار
    draw_vine(dr, size, color)
    draw_flowers(dr, size, color, variant["flower"])
    for x, y, s in [(size*0.55, size*0.14, 1.5), (size*0.70, size*0.12, 2.0),
                    (size*0.78, size*0.23, 1.1), (size*0.48, size*0.22, 0.9)]:
        draw_butterfly(dr, int(x), int(y), s, color)

    # نقاط زخرفية صغيرة
    for _ in range(40):
        x = random.randint(80, size-80)
        y = random.randint(80, size-80)
        if size*0.30 < y < size*0.78 and size*0.10 < x < size*0.90:
            continue  # اترك مساحة الاسم نظيفة
        r = random.randint(2, 5)
        dr.ellipse([x-r, y-r, x+r, y+r], fill=(*color, 60))

    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    for v in VARIANTS:
        img = make(v)
        img.save(OUT / f"{v['id']}.png", "PNG")
        shutil.copy2(OUT / f"{v['id']}.png", ASSETS / f"{v['id']}.png")
        meta = {
            "id": v["id"],
            "name": v["name"],
            "image": f"{v['id']}.png",
            "active": True,
            "two_names": False,
            "watermark": False,
            "style": "classic",
            "font_id": "",
            "font_size": 240,
            "color": "#151515",
            "align": "center",
            "shadow_color": "#000000",
            "shadow_x": 2,
            "shadow_y": 4,
            "shadow_blur": 2,
            "stroke_width": 0,
            "stroke_color": "#ffffff",
            "name_box": [60, 470, 904, 380],
            "name2_box": [90, 760, 844, 160],
        }
        (OUT / f"{v['id']}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("template", v["id"])


if __name__ == "__main__":
    main()
