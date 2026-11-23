# -*- coding: utf-8 -*-
"""detect.py — الكشف التلقائي عن منطقة الكتابة في قوالب البطاقات.

خوارزمية محلية بالكامل (Pillow + NumPy + OpenCV):
  1. تصغير الصورة لعرض 400px + تدرج رمادي.
  2. خريطة التفاصيل = Canny + تباين محلي + بُعد اللون عن الخلفية السائدة (k-means k=3).
  3. عتبة Otsu + تنظيف مورفولوجي (close/open).
  4. أكبر مستطيل فارغ (histogram method) مع قيود وتفضيل للثلث الأوسط/السفلي.
  5. مستطيل العبارة أسفل الاسم.
  6. لون نص بتباين >= 4.5 + درجة ثقة.

لا توجد أي خدمة خارجية أو مفتاح API. الإحداثيات الناتجة نسبية (0..1).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

TARGET_W = 400


def _load_image(path) -> Image.Image:
    img = Image.open(path)
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(rgba)
        img = bg.convert("RGB")
    else:
        img = img.convert("RGB")
    return img


def _relative_ratio(a: float, b: float) -> float:
    """نسبة تباين WCAG بين قيمتين 0..255."""
    def lin(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    l1, l2 = lin(a), lin(b)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def _choose_text_color(region_rgb: np.ndarray) -> Tuple[str, float]:
    mean = region_rgb.reshape(-1, 3).mean(axis=0)
    lum = 0.299 * mean[0] + 0.587 * mean[1] + 0.114 * mean[2]
    black_ratio = _relative_ratio(lum, 0)
    white_ratio = _relative_ratio(lum, 255)
    if black_ratio >= white_ratio:
        return "#0A0A0A", black_ratio
    return "#FFFFFF", white_ratio


def _detail_map(small_rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape

    # الخلفية السائدة بـ k-means (k=3)
    pix = small_rgb.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
    try:
        _, labels, centers = cv2.kmeans(pix, 3, None, criteria, 3,
                                        cv2.KMEANS_PP_CENTERS)
        counts = np.bincount(labels.ravel(), minlength=3)
        bg = centers[int(np.argmax(counts))]
    except Exception:
        bg = np.median(pix, axis=0)

    edges = cv2.Canny(gray, 55, 155).astype(np.float32) / 255.0

    g = gray.astype(np.float32)
    mean = cv2.blur(g, (9, 9))
    sq = cv2.blur(g * g, (9, 9))
    local_std = np.sqrt(np.maximum(sq - mean * mean, 0)) / 45.0

    dist = np.linalg.norm(small_rgb.astype(np.float32) - bg, axis=2) / 70.0

    score = np.maximum.reduce([edges, local_std, dist])
    score8 = np.clip(score * 255, 0, 255).astype(np.uint8)
    if float(score8.std()) < 4:
        # صورة شبه موحّدة: إما فارغة تماماً أو مزدحمة تماماً
        detail = np.full_like(score8, 255 if float(score8.mean()) > 100 else 0)
    else:
        th, _ = cv2.threshold(score8, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        th = int(min(max(float(th), 1), 235))
        detail = np.where(score8 > th, 255, 0).astype(np.uint8)
    empty = (detail == 0).astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    empty = cv2.morphologyEx(empty, cv2.MORPH_CLOSE, kernel)
    empty = cv2.morphologyEx(empty, cv2.MORPH_OPEN, kernel)
    return empty, detail


def _largest_rects(empty: np.ndarray, min_w: float, min_h: float,
                   y_min: float = 0.0) -> list:
    """كل المستطيلات القصوى في المصفوفة الثنائية مع قيود نسبية."""
    h, w = empty.shape
    # احذف هامش 4% من الحواف قبل البحث — أي مستطيل الناتج داخل الهامش تلقائياً
    mx, my = int(w * 0.04), int(h * 0.04)
    if mx and my:
        empty = empty.copy()
        empty[:my, :] = 0
        empty[-my:, :] = 0
        empty[:, :mx] = 0
        empty[:, -mx:] = 0
    heights = np.zeros(w, dtype=np.int32)
    out = []
    for r in range(h):
        heights = np.where(empty[r] > 0, heights + 1, 0)
        stack = []
        for c in range(w + 1):
            cur = heights[c] if c < w else 0
            while stack and heights[stack[-1]] > cur:
                idx = stack.pop()
                rh = int(heights[idx])
                left = stack[-1] if stack else -1
                rw = c - left - 1
                x = left + 1
                y = r - rh + 1
                if rw < min_w * w or rh < min_h * h:
                    continue
                ny = y / h
                if ny < y_min:
                    continue
                cx = (x + rw / 2) / w
                cy = (y + rh / 2) / h
                center_x = 1.0 - min(1.0, abs(cx - 0.5) * 2)
                vertical = 1.0 if 0.35 <= cy <= 0.78 else max(
                    0.25, 1.0 - abs(cy - 0.56) * 1.6)
                area = (rw * rh) / (w * h)
                score = area * (0.45 + 0.55 * vertical) * (0.6 + 0.4 * center_x)
                out.append((score, x, y, rw, rh, area))
            stack.append(c)
    out.sort(reverse=True)
    return out


def _to_rel(rect, shape) -> Dict[str, float]:
    h, w = shape[:2]
    x, y, rw, rh = rect
    return {"x": round(x / w, 4), "y": round(y / h, 4),
            "w": round(rw / w, 4), "h": round(rh / h, 4)}


def _abs_from_rel(rel, shape) -> Tuple[int, int, int, int]:
    h, w = shape[:2]
    x = int(rel["x"] * w); y = int(rel["y"] * h)
    rw = int(rel["w"] * w); rh = int(rel["h"] * h)
    return x, y, rw, rh


def suggest_slots(image_path) -> dict:
    """يرجع اقتراح المناطق بإحداثيات نسبية + لون نص + ثقة."""
    img = _load_image(image_path)
    W, H = img.size
    scale = TARGET_W / float(W)
    small = img.resize((TARGET_W, max(1, int(H * scale))), Image.Resampling.LANCZOS)
    small_rgb = np.array(small)
    # حماية من الصور المزدحمة عشوائياً: قياس نسيج الصورة قبل أي شيء
    gray = cv2.cvtColor(small_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gm = cv2.blur(gray, (9, 9))
    gs = cv2.blur(gray * gray, (9, 9))
    texture = float(np.sqrt(np.maximum(gs - gm * gm, 0)).mean())
    if texture > 18:
        return {"name": None, "quote": None, "text_color": "#111111",
                "confidence": float(round(max(0.05, 0.45 - texture / 100.0), 3)),
                "warning": "الصورة مزدحمة جداً — حدّد مكان الاسم يدوياً"}
    empty, detail = _detail_map(small_rgb)

    rects = _largest_rects(empty, min_w=0.40, min_h=0.08)
    if not rects:
        return {"name": None, "quote": None, "text_color": "#111111",
                "confidence": 0.1,
                "warning": "لم أجد منطقة واضحة — حدّد مكان الاسم يدوياً"}

    best = rects[0]
    _, nx, ny, nw, nh, name_area = best
    name_rel = _to_rel((nx, ny, nw, nh), empty.shape)

    # امسح منطقة الاسم ثم ابحث عن العبارة تحتها
    empty2 = empty.copy()
    empty2[ny:ny + nh, nx:nx + nw] = 0
    quote_rel = None
    for cand in _largest_rects(empty2, min_w=0.28, min_h=0.05,
                               y_min=(ny + nh * 0.6) / empty.shape[0]):
        qx, qy, qw, qh = cand[1:5]
        if qy >= ny + nh * 0.7:
            quote_rel = _to_rel((qx, qy, qw, qh), empty2.shape)
            break

    # لون النص من المنطقة المختارة على الصورة الأصلية المصغّرة
    x, y, rw, rh = _abs_from_rel(name_rel, small_rgb.shape)
    region = small_rgb[y:y + rh, x:x + rw]
    if region.size == 0:
        region = small_rgb
    color, contrast = _choose_text_color(region)

    # الثقة: مساحة المنطقة + نقاء التفاصيل + التباين
    around = detail[y:y + rh, x:x + rw]
    cleanliness = 1.0 - float((around > 0).mean()) if around.size else 0.5
    confidence = max(0.0, min(1.0,
        0.42 * min(1.0, name_area / 0.12) +
        0.38 * cleanliness +
        0.20 * min(1.0, max(0.0, (contrast - 3.0) / 3.0))))
    result = {
        "name": name_rel,
        "quote": quote_rel,
        "text_color": color,
        "confidence": float(round(confidence, 3)),
        "contrast": float(round(float(contrast), 2)),
    }
    if confidence < 0.5:
        result["warning"] = "الثقة منخفضة — راجع المستطيل يدوياً"
    return result


def apply_to_meta(meta: dict, suggestion: dict, image_size: Tuple[int, int]) -> dict:
    """ coping آمنة للاقتراح إلى صيغة القالب الحالية (بكسلات مطلقة)."""
    W, H = image_size
    out = dict(meta)
    if suggestion.get("name"):
        x, y, w, h = _abs_from_rel(suggestion["name"], (H, W))
        out["name_box"] = [x, y, w, h]
    if suggestion.get("quote"):
        x, y, w, h = _abs_from_rel(suggestion["quote"], (H, W))
        out["name2_box"] = [x, y, w, h]
        out["two_names"] = True
    if suggestion.get("text_color"):
        out["color"] = suggestion["text_color"]
    out["active"] = bool(meta.get("active", True))
    return out
