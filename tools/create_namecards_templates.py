# -*- coding: utf-8 -*-
"""توليد حزمة قوالب احترافية جاهزة — كل شيء مضبوط، المستخدم يكتب الاسم فقط."""
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

W, H = 1080, 1350

VARIANTS = [
    {"id": "royal_gold", "name": "ملكي ذهبي", "accent": (70, 45, 35), "flower": (225, 150, 40),
     "quote": "أنتِ كقطعة سكر وسط مرارة هذا العالم"},
    {"id": "rose_garden", "name": "حديقة الورد", "accent": (95, 45, 60), "flower": (215, 105, 140),
     "quote": "كل شيء جميل بطريقة ما، إلا أنتِ جميلة بكل الطرق"},
    {"id": "ocean_blue", "name": "أزرق المحيط", "accent": (40, 70, 100), "flower": (120, 160, 200),
     "quote": "جميلة كأنها مقتبسة من السماء"},
    {"id": "emerald", "name": "زمرد هادئ", "accent": (45, 80, 55), "flower": (130, 170, 110),
     "quote": "في حضورك يهدأ كل شيء"},
    {"id": "sunset", "name": "غروب دافئ", "accent": (110, 60, 40), "flower": (230, 130, 70),
     "quote": "أنتِ الضوء الذي لا يغيب"},
    {"id": "lavender", "name": "لافندر ناعم", "accent": (80, 60, 110), "flower": (170, 130, 200),
     "quote": "كأنكِ خُلقتِ من لطف"},
]


def textured_base(tint):
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 7, (H, W, 1))
    arr = np.zeros((H, W, 3), dtype=np.float32)
    for i, c in enumerate(tint):
        arr[:, :, i] = np.clip(c + noise[:, :, 0], 0, 255)
    img = Image.fromarray(arr.astype("uint8"), "RGB")
    # vignette ناعم
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W/2) / (W/2))**2 + ((yy - H/2) / (H/2))**2)
    vig = np.clip(1.0 - 0.16 * np.maximum(d - 0.55, 0), 0.75, 1.0)
    arr = (arr * vig[:, :, None]).astype("uint8")
    return Image.fromarray(arr, "RGB").filter(ImageFilter.GaussianBlur(0.35))


def petal_flower(dr, cx, cy, r, petal, center, n=8):
    for k in range(n):
        a = 2 * math.pi * k / n
        px, py = cx + r * 0.72 * math.cos(a), cy + r * 0.72 * math.sin(a)
        dr.ellipse([px - r*0.42, py - r*0.42, px + r*0.42, py + r*0.42],
                   fill=petal, outline=center, width=2)
    dr.ellipse([cx - r*0.3, cy - r*0.3, cx + r*0.3, cy + r*0.3], fill=center)


def _box(a, b, c, d):
    return [min(a, c), min(b, d), max(a, c), max(b, d)]


def butterfly(dr, x, y, s, color):
    # أجنحة ممتلئة + تفاصيل
    for sgn in (-1, 1):
        dr.ellipse(_box(x + sgn*3*s, y - 26*s, x + sgn*26*s, y - 4*s), fill=color)
        dr.ellipse(_box(x + sgn*3*s, y, x + sgn*20*s, y + 18*s), fill=color)
        dr.ellipse(_box(x + sgn*8*s, y - 20*s, x + sgn*18*s, y - 10*s),
                   fill=tuple(min(255, c + 60) for c in color))
    dr.line([x, y - 16*s, x, y + 18*s], fill=color, width=max(2, int(3*s)))
    dr.arc([x - 4*s, y - 30*s, x + 4*s, y - 16*s], 180, 360, fill=color, width=2)


def vine(dr, color):
    pts = []
    for i in range(0, 121):
        t = i / 120
        x = 40 + t * (W * 0.30)
        y = H * 0.72 - 70 * math.sin(t * math.pi) - 16 * math.sin(t * 5 * math.pi)
        pts.append((int(x), int(y)))
    dr.line(pts, fill=color, width=6, joint="curve")
    for i in range(6, 116, 9):
        x, y = pts[i]
        a = (i / 120) * math.pi
        for s in (-1, 1):
            ex = x + 44 * math.cos(a + s * 0.85)
            ey = y - 38 * math.sin(a + s * 0.85)
            dr.ellipse([min(x, ex), min(y, ey), max(x, ex), max(y, ey)],
                       outline=color, width=3)
            dr.line([x, y, ex, ey], fill=color, width=2)
            # ورقة صغيرة
            dr.ellipse([min(x, ex)-6, min(y, ey)-6, min(x, ex)+6, min(y, ey)+6], fill=color)


def hearts(dr, color):
    for cx, cy, s in [(W*0.16, H*0.80, 14), (W*0.20, H*0.76, 9)]:
        dr.polygon([(cx, cy+s), (cx-s, cy), (cx-s*0.5, cy-s*0.8),
                    (cx, cy-s*0.2), (cx+s*0.5, cy-s*0.8), (cx+s, cy)], outline=color, width=3)


def make(v):
    img = textured_base((216, 200, 182))
    dr = ImageDraw.Draw(img, "RGBA")
    color = (*v["accent"], 255)

    # إطار مزدوج خفيف
    dr.rectangle([26, 26, W-26, H-26], outline=(*v["accent"], 70), width=2)
    dr.rectangle([38, 38, W-38, H-38], outline=(*v["accent"], 40), width=1)

    # زهور في الربع الأعلى
    petal_flower(dr, W*0.66, H*0.30, 46, v["flower"], v["accent"], 9)
    petal_flower(dr, W*0.74, H*0.25, 30, v["flower"], v["accent"], 7)
    petal_flower(dr, W*0.70, H*0.37, 22, v["flower"], v["accent"], 6)
    # ساق
    dr.line([W*0.66, H*0.34, W*0.63, H*0.46], fill=color, width=5)

    # فراشات
    butterfly(dr, int(W*0.55), int(H*0.14), 2.0, v["accent"])
    butterfly(dr, int(W*0.72), int(H*0.11), 2.6, v["accent"])
    butterfly(dr, int(W*0.82), int(H*0.24), 1.4, v["accent"])
    butterfly(dr, int(W*0.47), int(H*0.23), 1.1, v["accent"])

    vine(dr, color)
    hearts(dr, v["accent"])

    # نقاط خفيفة خارج منطقة الاسم
    rng = random.Random(5)
    for _ in range(70):
        x = rng.randint(70, W-70); y = rng.randint(70, H-70)
        if H*0.34 < y < H*0.86 and W*0.08 < x < W*0.92:
            continue
        r = rng.randint(2, 5)
        dr.ellipse([x-r, y-r, x+r, y+r], fill=(*v["accent"], 70))

    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    for v in VARIANTS:
        img = make(v)
        img.save(OUT / f"{v['id']}.png", "PNG")
        shutil.copy2(OUT / f"{v['id']}.png", ASSETS / f"{v['id']}.png")
        meta = {
            "id": v["id"], "name": v["name"], "image": f"{v['id']}.png",
            "active": True, "two_names": False, "watermark": False,
            "style": "classic", "font_id": "", "font_size": 230,
            "color": "#151515", "align": "center",
            "shadow_color": "#000000", "shadow_x": 2, "shadow_y": 5, "shadow_blur": 2,
            "stroke_width": 0, "stroke_color": "#ffffff",
            "name_box": [70, 610, 940, 360],
            "name2_box": [120, 1010, 840, 150],
            "quote_text": v["quote"],
            "quote_font_size": 44,
        }
        (OUT / f"{v['id']}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("template", v["id"])


if __name__ == "__main__":
    main()
