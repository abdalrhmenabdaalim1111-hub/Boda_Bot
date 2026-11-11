# -*- coding: utf-8 -*-
"""
tools/design_system.py — نقطة الدخول الموحدة لنظام تصميم Boda

الاستخدام:
    from design_system import build_css, SDK_JS, brand

    css = build_css(tag="أدوات 🛠️", bot_id="currency")

كل تطبيق مصغّر يستورد هذه الوحدة عبر ``app_template.py``؛ لا تكرّر
الألوان أو الخطوط أو الحركات داخل التطبيقات نفسها.
"""
from ds_tokens import group_palette, group_key, build_tokens_css, TOKENS_CSS, FONT_CSS
from ds_components import COMPONENTS_CSS, MOTION_CSS
from ds_sdk import SDK_JS

# للتوافق مع الاستيرادات القديمة من app_template
COMMON_CSS = build_tokens_css() + COMPONENTS_CSS + MOTION_CSS
COMMON_JS = SDK_JS


def build_css(tag: str = "", bot_id: str = "") -> str:
    """بناء CSS كامل بهوية المجموعة الصحيحة."""
    return build_tokens_css(tag=tag, bot_id=bot_id) + COMPONENTS_CSS + MOTION_CSS


def brand(tag: str = "", bot_id: str = "") -> dict:
    """ألوان وإيموجي المجموعة — للاستخدام في القوالب واللوحات."""
    return group_palette(tag=tag, bot_id=bot_id)


__all__ = [
    "COMMON_CSS", "COMMON_JS", "SDK_JS", "build_css", "brand",
    "group_key", "group_palette", "TOKENS_CSS", "FONT_CSS",
    "COMPONENTS_CSS", "MOTION_CSS",
]
