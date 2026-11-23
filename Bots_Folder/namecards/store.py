# -*- coding: utf-8 -*-
"""store.py — جداول البطاقات داخل نفس SQLite (WAL) + عدّاد استخدام القوالب."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Dict, Any

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = ROOT / "Data" / "namecards" / "templates"
FONTS_DIR = ROOT / "Data" / "namecards" / "fonts"


def _db():
    from Bots_Folder.database import get_db
    return get_db()


def ensure_tables() -> None:
    """تُنشأ الجداول مرة أخرى هنا حمايةً إذا قُدّم ملف database أقدم."""
    db = _db()
    with db._conn_lock:
        with db._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS card_renders (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts          TEXT NOT NULL,
                    user_hash   TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    ok          INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS card_template_usage (
                    template_id TEXT PRIMARY KEY,
                    uses        INTEGER DEFAULT 0,
                    last_used   TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_card_renders_user ON card_renders(user_hash)")


def record_render(user_hash: str, template_id: str, ok: bool = True) -> None:
    ensure_tables()
    db = _db()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with db._conn_lock:
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO card_renders (ts,user_hash,template_id,ok) VALUES (?,?,?,?)",
                (now, user_hash, template_id, 1 if ok else 0))
            conn.execute("""
                INSERT INTO card_template_usage (template_id,uses,last_used)
                VALUES (?,1,?)
                ON CONFLICT(template_id) DO UPDATE SET
                    uses = uses + 1, last_used = excluded.last_used
            """, (template_id, now))


def recent_cards(user_hash: str, limit: int = 5) -> List[Dict[str, Any]]:
    ensure_tables()
    db = _db()
    with db._get_conn() as conn:
        rows = conn.execute("""
            SELECT template_id, ts, ok FROM card_renders
            WHERE user_hash = ? ORDER BY id DESC LIMIT ?
        """, (user_hash, limit)).fetchall()
    return [{"template_id": r["template_id"], "ts": r["ts"], "ok": bool(r["ok"])} for r in rows]


def recent_all(limit: int = 20) -> List[Dict[str, Any]]:
    ensure_tables()
    db = _db()
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT ts,user_hash,template_id,ok FROM card_renders ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def usage_map() -> Dict[str, int]:
    ensure_tables()
    db = _db()
    with db._get_conn() as conn:
        rows = conn.execute("SELECT template_id,uses FROM card_template_usage").fetchall()
    return {r["template_id"]: int(r["uses"] or 0) for r in rows}


def record_referral(referrer_hash: str, referred_id: int) -> bool:
    """تسجيل الإحالة في جدول referrals الموجود (بمعرّف عددى مشتق من الهاش)."""
    db = _db()
    from .security import hash_to_int
    try:
        with db._conn_lock:
            with db._get_conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO referrals
                        (referrer_id, referred_id, bot_name, created_at)
                    VALUES (?,?,?,?)
                """, (hash_to_int(referrer_hash), int(referred_id), "namecards",
                      time.strftime("%Y-%m-%dT%H:%M:%S")))
        return True
    except Exception:
        return False


# ── إدارة القوالب (ملفات + wish JSON) ──────────────────────────────────────
def templates_dir() -> Path:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return TEMPLATES_DIR


def fonts_dir() -> Path:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    return FONTS_DIR


def list_fonts() -> List[Dict[str, Any]]:
    out = []
    for f in sorted(fonts_dir().iterdir()):
        if f.suffix.lower() not in (".ttf", ".otf"):
            continue
        out.append({"id": f.stem, "name": f.stem, "file": f.name,
                    "size": f.stat().st_size})
    return out


def get_font_path(font_id: str) -> Path | None:
    fid = "".join(ch for ch in str(font_id) if ch.isalnum() or ch in "-_")[:64]
    if not fid:
        return None
    for ext in (".ttf", ".otf"):
        p = fonts_dir() / f"{fid}{ext}"
        if p.exists():
            return p
    return None


def save_font(font_id: str, raw: bytes) -> Path:
    fid = "".join(ch for ch in str(font_id) if ch.isalnum() or ch in "-_")[:64]
    if not fid:
        raise ValueError("معرّف الخط مطلوب")
    # احتفظ بالامتداد الأصلي
    ext = ".ttf"
    p = fonts_dir() / f"{fid}{ext}"
    p.write_bytes(raw)
    # احذف الامتداد الآخر إن وُجد
    other = fonts_dir() / f"{fid}{'.otf' if ext == '.ttf' else '.ttf'}"
    if other.exists():
        other.unlink()
    return p


def list_templates(admin: bool = False) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for meta_path in sorted(templates_dir().glob("*.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not admin and not meta.get("active", True):
            continue
        image = templates_dir() / (meta.get("image") or (meta_path.stem + ".png"))
        out.append({
            "id": meta_path.stem,
            "name": meta.get("name", meta_path.stem),
            "active": bool(meta.get("active", True)),
            "two_names": bool(meta.get("two_names", False)),
            "watermark": bool(meta.get("watermark", False)),
            "thumb": f"/api/cards/thumb/{meta_path.stem}",
            "has_image": image.exists(),
            "uses": usage_map().get(meta_path.stem, 0),
        })
    return out


def get_template(template_id: str) -> Dict[str, Any]:
    """قراءة آمنة منع path traversal."""
    tid = "".join(ch for ch in str(template_id) if ch.isalnum() or ch in "-_")[:64]
    meta_path = templates_dir() / f"{tid}.json"
    if not meta_path.exists():
        return {}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    meta["id"] = tid
    meta["image_path"] = templates_dir() / (meta.get("image") or f"{tid}.png")
    return meta
