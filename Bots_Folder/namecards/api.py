# -*- coding: utf-8 -*-
"""api.py — راوتر /api/cards مُدمج في api_server.py (نمط http.server).

التوقيع: dispatch(method, subpath, qs, body, headers) -> (status, payload, content_type)
 - payload قد يكون dict (يُرسل JSON) أو bytes (صورة).
"""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Tuple, Dict, Any

from . import security, store, renderer

TOKEN = (os.getenv("NAMECARDS_BOT_TOKEN") or os.getenv("BOT_NAMECARDS_TOKEN") or "").strip()
try:
    from control_center.botconfig import resolve_token as _resolve_token
    TOKEN = _resolve_token("namecards") or TOKEN
except Exception:
    pass
BOT_USERNAME = (os.getenv("NAMECARDS_BOT_USERNAME") or "NameOnPicBot").strip().lstrip("@")
ADMIN_KEY = (os.getenv("API_SERVER_KEY") or "").strip()

_bot = None


def _telegram():
    global _bot
    if _bot is None and TOKEN:
        import telebot
        _bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
    return _bot


def _bot_username() -> str:
    global BOT_USERNAME
    bot = _telegram()
    if bot:
        try:
            BOT_USERNAME = bot.get_me().username or BOT_USERNAME
        except Exception:
            pass
    return BOT_USERNAME


def _auth_user(body: Dict[str, Any]):
    init_data = str(body.get("init_data") or "")
    user = security.validate_init_data(init_data, TOKEN)
    if not user:
        return None, (403, {"ok": False, "error": "بيانات الدخول غير صالحة — افتح البوت أولاً"}, "application/json")
    if not security.limiter.allow(user["hash"]):
        return None, (429, {"ok": False, "error": "محاولات كثيرة — انتظر قليلاً"}, "application/json")
    return user, None


def _admin_ok(headers) -> bool:
    if not ADMIN_KEY:
        return False
    supplied = (headers.get("X-API-Key") or headers.get("x-api-key") or "").strip()
    return supplied == ADMIN_KEY


def _json(status: int, payload: Dict) -> Tuple[int, Any, str]:
    return status, payload, "application/json; charset=utf-8"


def dispatch(method: str, subpath: str, qs: Dict, body: Dict, headers) -> Tuple[int, Any, str]:
    """نقطة الدخول الواحدة من api_server.py."""
    p = "/" + subpath.strip("/")

    # ── قراءة عامة (تعتمد على initData) ──────────────────────────────────
    if method == "GET" and p == "/templates":
        init_data = (qs.get("init_data") or [""])[0]
        user = security.validate_init_data(init_data, TOKEN)
        if not user:
            return _json(403, {"ok": False, "error": "افتح البوت أولاً ثم جرّب مجدداً"})
        return _json(200, {"ok": True, "templates": store.list_templates()})

    if method == "GET" and p.startswith("/thumb/"):
        tid = p.rsplit("/", 1)[-1]
        tpl = store.get_template(tid)
        image = Path(tpl.get("image_path") or "")
        if not tpl or not tpl.get("image_path") or not image.exists():
            return _json(404, {"ok": False, "error": "القالب غير موجود"})
        return 200, image.read_bytes(), "image/png"

    if method == "GET" and p == "/promo":
        try:
            from control_center.promo import get_promo_for_user
            uid = int((qs.get("user_id") or ["0"])[0] or 0)
            data = get_promo_for_user("namecards", uid)
            return _json(200, data if isinstance(data, dict) else {})
        except Exception:
            return _json(200, {})

    # ── إنشاء البطاقة وإرسالها في المحادثة ───────────────────────────────
    if method == "POST" and p == "/render":
        user, err = _auth_user(body)
        if err:
            return err
        tpl = store.get_template(str(body.get("template_id") or ""))
        if not tpl:
            return _json(404, {"ok": False, "error": "هذا القالب غير موجود"})
        if not tpl.get("active", True):
            return _json(410, {"ok": False, "error": "هذا القالب معطّل حالياً"})
        name = security.sanitize_name(body.get("name"))
        name2 = security.sanitize_name(body.get("name2"))
        if not name:
            return _json(400, {"ok": False, "error": "اكتب اسماً صحيحاً (30 حرفاً كحد أقصى)"})
        if tpl.get("two_names") and not name2:
            return _json(400, {"ok": False, "error": "هذا القالب يحتاج اسمين"})

        remove_watermark = bool(body.get("remove_watermark"))
        draw_wm = bool(tpl.get("watermark", False)) and not remove_watermark
        try:
            png = renderer.render_card(tpl, name, name2,
                                       watermark_text="@" + _bot_username(),
                                       draw_watermark=draw_wm)
        except Exception as e:
            store.record_render(user["hash"], tpl["id"], False)
            return _json(500, {"ok": False, "error": "تعذر رسم البطاقة: " + str(e)[:120]})

        username = _bot_username()
        deep_link = f"https://t.me/{username}?start=ref_{user['hash']}"
        caption = (f"🃏 بطاقتك جاهزة!\n"
                   f"القالب: {tpl.get('name', tpl['id'])}\n"
                   f"جرّب البوت: {deep_link}")
        sent = False
        bot = _telegram()
        if bot:
            try:
                from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(
                    "📤 شارك البطاقة",
                    url=f"https://t.me/share/url?url={deep_link}&text=جرّب بوت بطاقات بالاسم 🃏"))
                bot.send_photo(user["id"], photo=io.BytesIO(png),
                               caption=caption, reply_markup=kb)
                sent = True
            except Exception:
                sent = False
        store.record_render(user["hash"], tpl["id"], sent)
        if not sent:
            return _json(502, {"ok": False, "error": "تعذر إرسال الصورة — تأكد أنك ضغطت /start للبوت"})
        return _json(200, {"ok": True, "share_url": deep_link,
                           "message": "تم إرسال البطاقة إليك في المحادثة ✅"})

    # ── الأدمن (X-API-Key فقط) ───────────────────────────────────────────
    if p.startswith("/admin") and not _admin_ok(headers):
        return _json(403, {"ok": False, "error": "مفتاح الأدمن غير صالح"})

    if method == "GET" and p == "/admin/templates":
        return _json(200, {"ok": True,
                           "templates": store.list_templates(admin=True),
                           "fonts": store.list_fonts()})

    if method == "GET" and p == "/admin/fonts":
        return _json(200, {"ok": True, "fonts": store.list_fonts()})

    if method == "POST" and p == "/admin/fonts/upload":
        fid = "".join(ch for ch in str(body.get("id") or "") if ch.isalnum() or ch in "-_")[:64]
        b64 = str(body.get("font_base64") or "")
        if not fid:
            return _json(400, {"ok": False, "error": "معرّف الخط مطلوب"})
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception:
            return _json(400, {"ok": False, "error": "ملف الخط غير صالح"})
        if len(raw) > 10 * 1024 * 1024:
            return _json(413, {"ok": False, "error": "حجم الخط يتجاوز 10MB"})
        signature = raw[:4]
        if not (signature in (b"\x00\x01\x00\x00", b"true", b"OTTO", b"typ1") or
                str(signature).startswith("b'\\x00\\x01")):
            return _json(400, {"ok": False, "error": "الملف ليس خط TTF/OTF صالحاً"})
        try:
            path = store.save_font(fid, raw)
            from PIL import ImageFont
            ImageFont.truetype(str(path), 24)  # تأكد أن Pillow يستطيع قراءته
        except Exception as e:
            return _json(400, {"ok": False, "error": "تعذر قراءة الخط: " + str(e)[:100]})
        return _json(200, {"ok": True, "font": {"id": fid, "name": fid}})

    if method == "POST" and p == "/admin/fonts/delete":
        fid = "".join(ch for ch in str(body.get("id") or "") if ch.isalnum() or ch in "-_")[:64]
        fp = store.get_font_path(fid)
        if fp:
            fp.unlink(missing_ok=True)
            return _json(200, {"ok": True})
        return _json(404, {"ok": False, "error": "الخط غير موجود"})

    if method == "POST" and p == "/admin/upload":
        tid = "".join(ch for ch in str(body.get("id") or "") if ch.isalnum() or ch in "-_")[:64]
        if not tid:
            return _json(400, {"ok": False, "error": "معرّف القالب مطلوب"})
        b64 = str(body.get("image_base64") or "")
        directory = store.templates_dir()
        ext = ""
        if not b64:
            # تحديث إعدادات قالب موجود بدون رفع الصورة مجدداً
            existing = store.get_template(tid)
            if not existing:
                return _json(404, {"ok": False, "error": "القالب غير موجود"})
            image_name = str(existing.get("image") or "")
            if not (directory / image_name).exists():
                return _json(404, {"ok": False, "error": "صورة القالب غير موجودة"})
            ext = image_name.rsplit(".", 1)[-1] if "." in image_name else "png"
        else:
            try:
                raw = base64.b64decode(b64, validate=True)
            except Exception:
                return _json(400, {"ok": False, "error": "صورة القالب غير صالحة"})
            if len(raw) > 10 * 1024 * 1024:
                return _json(413, {"ok": False, "error": "حجم الصورة يتجاوز 10MB"})
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(raw))
                im.verify()
                fmt = (im.format or "PNG").lower()
                ext = "jpg" if fmt in ("jpeg", "jpg") else "png" if fmt == "png" else "webp"
            except Exception:
                return _json(400, {"ok": False, "error": "نوع الصورة غير مدعوم (PNG/JPG/WebP فقط)"})
            image_path = directory / f"{tid}.{ext}"
            image_path.write_bytes(raw)

        image_path = directory / f"{tid}.{ext}"
        meta = {
            "id": tid,
            "name": security.sanitize_name(body.get("name") or tid, 60) or tid,
            "image": image_path.name,
            "active": bool(body.get("active", True)),
            "two_names": bool(body.get("two_names", False)),
            "watermark": bool(body.get("watermark", False)),
            "font": str(body.get("font") or ""),
            "font_id": str(body.get("font_id") or ""),
            "font_size": int(body.get("font_size") or 56),
            "color": body.get("color") or "#141414",
            "align": str(body.get("align") or "center"),
            "shadow_color": body.get("shadow_color") or "#000000",
            "shadow_x": int(body.get("shadow_x") or 0),
            "shadow_y": int(body.get("shadow_y") or 0),
            "shadow_blur": int(body.get("shadow_blur") or 0),
            "stroke_width": int(body.get("stroke_width") or 0),
            "stroke_color": body.get("stroke_color") or "#ffffff",
            "name_box": body.get("name_box") or [20, 90, 460, 100],
            "name2_box": body.get("name2_box") or [20, 220, 460, 90],
        }
        (directory / f"{tid}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = dict(store.get_template(tid))
        meta.pop("image_path", None)
        return _json(200, {"ok": True, "template": meta})

    if method == "POST" and p == "/admin/delete":
        tid = "".join(ch for ch in str(body.get("id") or "") if ch.isalnum() or ch in "-_")[:64]
        if not tid:
            return _json(400, {"ok": False, "error": "معرّف القالب مطلوب"})
        directory = store.templates_dir()
        removed = False
        for f in directory.glob(f"{tid}.*"):
            f.unlink(missing_ok=True)
            removed = True
        return _json(200, {"ok": removed, "error": None if removed else "القالب غير موجود"})

    return _json(404, {"ok": False, "error": "مسار غير معروف"})
