"""
control_center/store.py — Store Manager (Phase 2).

CRUD for store_items table, catalog generation, publish pipeline.
"""

import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import config
from .db import get_db

# ─────────────────────────────────────────────────────────────────────────────
# Sanitization & Validation
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_URL_SCHEMES = ("https://", "tg://", "mailto:")
MAX_TITLE_LENGTH = 100
MAX_DESC_LENGTH = 2000

# Script/HTML injection patterns to block/strip
SCRIPT_PATTERN = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
IFRAME_PATTERN = re.compile(r"<iframe[^>]*>.*?</iframe>", re.IGNORECASE | re.DOTALL)
ON_EVENT_PATTERN = re.compile(r"\bon\w+\s*=\s*[\"'][^\"']*[\"']", re.IGNORECASE)
JAVASCRIPT_URL_PATTERN = re.compile(r"javascript:", re.IGNORECASE)
DATA_URL_PATTERN = re.compile(r"data:", re.IGNORECASE)


def _sanitize_text(text: str) -> str:
    """Sanitize text fields: escape HTML, remove script tags and dangerous patterns."""
    if not text:
        return text
    # First escape HTML entities
    text = html.escape(text)
    # Remove script tags
    text = SCRIPT_PATTERN.sub("", text)
    # Remove iframe tags
    text = IFRAME_PATTERN.sub("", text)
    # Remove on* event handlers
    text = ON_EVENT_PATTERN.sub("", text)
    # Remove javascript: URLs
    text = JAVASCRIPT_URL_PATTERN.sub("blocked:", text)
    # Remove data: URLs
    text = DATA_URL_PATTERN.sub("blocked:", text)
    return text


def _validate_url(url: str) -> bool:
    """Validate URL scheme is in allowlist."""
    if not url:
        return True  # Empty URLs are allowed (will use defaults)
    url_lower = url.strip().lower()
    return any(url_lower.startswith(scheme) for scheme in ALLOWED_URL_SCHEMES)


def _truncate_field(text: str, max_len: int) -> str:
    """Truncate field to max length."""
    if not text:
        return text
    if len(text) > max_len:
        return text[:max_len].rstrip()
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Store Items CRUD
# ─────────────────────────────────────────────────────────────────────────────

STORE_FIELDS = (
    "id", "bot_id", "title_ar", "title_en", "short_desc_ar", "short_desc_en",
    "long_desc_ar", "long_desc_en", "icon_url", "cover_url", "category",
    "tags", "badges", "display_order", "status", "deep_link", "miniapp_url",
    "views", "opens", "clicks", "created_at", "updated_at"
)

STORE_FIELDS_NO_ID = STORE_FIELDS[1:]  # without id (auto)


def _now() -> str:
    return datetime.now().isoformat()


def _row_to_item(row) -> dict:
    """Convert sqlite row to store item dict."""
    if row is None:
        return {}
    item = dict(row)
    # Ensure CSV fields are lists for API
    for field in ("tags", "badges"):
        val = item.get(field)
        if val:
            item[field] = [s.strip() for s in val.split(",") if s.strip()]
        else:
            item[field] = []
    return item


def list_store_items(status_filter: str = "") -> list:
    """List all store items, optionally filtered by status."""
    db = get_db()
    if db is None:
        return []
    try:
        with db._get_conn() as conn:
            if status_filter:
                rows = conn.execute(
                    f"SELECT {', '.join(STORE_FIELDS)} FROM store_items WHERE status=? ORDER BY display_order, id",
                    (status_filter,)
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {', '.join(STORE_FIELDS)} FROM store_items ORDER BY display_order, id"
                ).fetchall()
            return [_row_to_item(r) for r in rows]
    except Exception:
        return []


def get_store_item(item_id: int) -> dict:
    """Get a single store item by ID."""
    db = get_db()
    if db is None:
        return {}
    try:
        with db._get_conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(STORE_FIELDS)} FROM store_items WHERE id=?",
                (item_id,)
            ).fetchone()
            return _row_to_item(row)
    except Exception:
        return {}


def get_store_item_by_bot(bot_id: str) -> dict:
    """Get store item by bot_id."""
    db = get_db()
    if db is None:
        return {}
    try:
        with db._get_conn() as conn:
            row = conn.execute(
                f"SELECT {', '.join(STORE_FIELDS)} FROM store_items WHERE bot_id=?",
                (bot_id,)
            ).fetchone()
            return _row_to_item(row)
    except Exception:
        return {}


def create_store_item(**fields) -> dict:
    """Create a new store item."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    # bot_id is required
    bot_id = fields.get("bot_id", "").strip()
    if not bot_id:
        return {"ok": False, "error": "bot_id is required"}

    # Check if bot exists in registry
    import json
    registry_path = config.ROOT_DIR / "bots_registry.json"
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    bot_reg = next((b for b in registry if b["id"] == bot_id), None)
    if not bot_reg:
        return {"ok": False, "error": f"Bot '{bot_id}' not found in registry"}

    # Check if already exists
    existing = get_store_item_by_bot(bot_id)
    if existing:
        return {"ok": False, "error": f"Store item for bot '{bot_id}' already exists"}

    now = _now()
    # Default values from registry
    defaults = {
        "bot_id": bot_id,
        "title_ar": bot_reg.get("name", ""),
        "title_en": "",
        "short_desc_ar": bot_reg.get("short_desc", ""),
        "short_desc_en": "",
        "long_desc_ar": bot_reg.get("description", ""),
        "long_desc_en": "",
        "icon_url": "",
        "cover_url": "",
        "category": bot_reg.get("category", "أخرى"),
        "tags": "",
        "badges": "",
        "display_order": 0,
        "status": "live",
        "deep_link": bot_reg.get("url", ""),
        "miniapp_url": "",
        "views": 0,
        "opens": 0,
        "clicks": 0,
    }

    # Merge provided fields
    for k, v in defaults.items():
        if k in fields:
            val = fields[k]
            if k in ("tags", "badges") and isinstance(val, list):
                defaults[k] = ", ".join(val)
            else:
                defaults[k] = val

    # Validate and sanitize fields
    # URL validation
    for url_field in ("deep_link", "miniapp_url", "icon_url", "cover_url"):
        if url_field in defaults and defaults[url_field]:
            if not _validate_url(defaults[url_field]):
                return {"ok": False, "error": f"Invalid URL scheme for {url_field}. Allowed: https://, tg://, mailto:"}
    
    # Sanitize text fields
    for field in ("title_ar", "title_en", "short_desc_ar", "short_desc_en", 
                   "long_desc_ar", "long_desc_en", "category", "tags", "badges"):
        if field in defaults and defaults[field]:
            defaults[field] = _sanitize_text(defaults[field])
    
    # Truncate fields
    for field in ("title_ar", "title_en"):
        if field in defaults and defaults[field]:
            defaults[field] = _truncate_field(defaults[field], MAX_TITLE_LENGTH)
    for field in ("short_desc_ar", "short_desc_en", "long_desc_ar", "long_desc_en"):
        if field in defaults and defaults[field]:
            defaults[field] = _truncate_field(defaults[field], MAX_DESC_LENGTH)

    # Ensure list fields are CSV strings
    for field in ("tags", "badges"):
        val = defaults.get(field)
        if isinstance(val, list):
            defaults[field] = ", ".join(val)
        elif val is None:
            defaults[field] = ""

    # Insert columns (exclude created_at, updated_at - added in SQL)
    insert_cols = [f for f in STORE_FIELDS_NO_ID if f not in ("created_at", "updated_at")]
    cols = ", ".join(insert_cols)
    placeholders = ", ".join(["?"] * len(insert_cols))
    values = tuple(defaults[f] for f in insert_cols)

    try:
        with db._get_conn() as conn:
            cur = conn.execute(
                f"INSERT INTO store_items ({cols}, created_at, updated_at) VALUES ({placeholders}, ?, ?)",
                values + (now, now)
            )
            item_id = cur.lastrowid
        return {"ok": True, "item": get_store_item(item_id)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def update_store_item(item_id: int, **fields) -> dict:
    """Update a store item."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    existing = get_store_item(item_id)
    if not existing:
        return {"ok": False, "error": "Store item not found"}

    # Convert list fields to CSV
    for field in ("tags", "badges"):
        if field in fields and isinstance(fields[field], list):
            fields[field] = ", ".join(fields[field])

    # Validate and sanitize fields
    # URL validation
    for url_field in ("deep_link", "miniapp_url", "icon_url", "cover_url"):
        if url_field in fields and fields[url_field]:
            if not _validate_url(fields[url_field]):
                return {"ok": False, "error": f"Invalid URL scheme for {url_field}. Allowed: https://, tg://, mailto:"}
    
    # Sanitize text fields
    for field in ("title_ar", "title_en", "short_desc_ar", "short_desc_en", 
                   "long_desc_ar", "long_desc_en", "category", "tags", "badges"):
        if field in fields and fields[field]:
            fields[field] = _sanitize_text(fields[field])
    
    # Truncate fields
    for field in ("title_ar", "title_en"):
        if field in fields and fields[field]:
            fields[field] = _truncate_field(fields[field], MAX_TITLE_LENGTH)
    for field in ("short_desc_ar", "short_desc_en", "long_desc_ar", "long_desc_en"):
        if field in fields and fields[field]:
            fields[field] = _truncate_field(fields[field], MAX_DESC_LENGTH)

    allowed = {f for f in STORE_FIELDS if f not in ("id", "bot_id", "created_at", "views", "opens", "clicks")}
    assignments, params = [], []

    for field in allowed:
        if field in fields:
            assignments.append(f"{field}=?")
            params.append(fields[field])

    if not assignments:
        return {"ok": True, "updated": False, "item": existing}

    assignments.append("updated_at=?")
    params.append(_now())
    params.append(item_id)

    try:
        with db._get_conn() as conn:
            conn.execute(
                f"UPDATE store_items SET {', '.join(assignments)} WHERE id=?",
                params
            )
        return {"ok": True, "updated": True, "item": get_store_item(item_id)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def delete_store_item(item_id: int) -> dict:
    """Delete a store item with automatic backup."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    existing = get_store_item(item_id)
    if not existing:
        return {"ok": False, "error": "Store item not found"}

    # Create backup in ads_pre directory (or store_backups)
    backup_dir = config.ROOT_DIR / "Backups" / "store_items"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    import json
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_file = backup_dir / f"store_item_{item_id}_{timestamp}.json"
    
    try:
        backup_file.write_text(
            json.dumps({"deleted_item": existing, "deleted_at": _now()}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as exc:
        # Don't fail delete if backup fails, just log it
        print(f"Warning: Failed to create backup: {exc}")

    try:
        with db._get_conn() as conn:
            conn.execute("DELETE FROM store_items WHERE id=?", (item_id,))
        return {"ok": True, "deleted": existing, "backup": str(backup_file)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def reorder_store_items(item_ids: list) -> dict:
    """Update display_order for multiple items."""
    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    try:
        with db._get_conn() as conn:
            for order, item_id in enumerate(item_ids):
                conn.execute(
                    "UPDATE store_items SET display_order=?, updated_at=? WHERE id=?",
                    (order, _now(), item_id)
                )
        return {"ok": True, "reordered": len(item_ids)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def increment_stat(item_id: int, stat: str) -> dict:
    """Increment views/opens/clicks for a store item."""
    if stat not in ("views", "opens", "clicks"):
        return {"ok": False, "error": "Invalid stat"}

    db = get_db()
    if db is None:
        return {"ok": False, "error": "database unavailable"}

    try:
        with db._get_conn() as conn:
            conn.execute(f"UPDATE store_items SET {stat} = {stat} + 1 WHERE id=?", (item_id,))
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Catalog Generation (for Mini App)
# ─────────────────────────────────────────────────────────────────────────────

STORE_URL = "https://t.me/BodaStoreeBot"


def generate_catalog() -> list:
    """Generate catalog.json from store_items (live + hidden for admin preview)."""
    items = list_store_items()  # All statuses
    catalog = []
    for item in items:
        bot_reg = None
        import json
        registry_path = config.ROOT_DIR / "bots_registry.json"
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
        bot_reg = next((b for b in registry if b["id"] == item["bot_id"]), None)

        catalog.append({
            "id": item["bot_id"],
            "emoji": bot_reg.get("emoji", "🤖") if bot_reg else "🤖",
            "name": item["title_ar"],
            "short_desc": item["short_desc_ar"],
            "tag": item["category"],
            "description": item["long_desc_ar"],
            "username": bot_reg.get("username", "") if bot_reg else "",
            "url": item["deep_link"] or (bot_reg.get("url", STORE_URL) if bot_reg else STORE_URL),
            "web": f"{item['bot_id']}/",
            "added_date": item["created_at"][:10] if item["created_at"] else "",
            "hidden": item["status"] != "live",
            "badges": item["badges"],
            "cover_url": item["cover_url"],
            "icon_url": item["icon_url"],
        })
    return catalog


def write_catalog(catalog: list, output_dir: Path = None) -> str:
    """Write catalog.json to webroot/data/."""
    if output_dir is None:
        output_dir = config.ROOT_DIR / "webroot" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(catalog_path)


# ─────────────────────────────────────────────────────────────────────────────
# Build & Publish Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def build_store_pages() -> dict:
    """Run tools/build_mini_apps.py to regenerate all Mini App pages."""
    try:
        result = subprocess.run(
            ["python", "tools/build_mini_apps.py"],
            cwd=str(config.ROOT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr, "stdout": result.stdout}
        return {"ok": True, "stdout": result.stdout}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Build timed out after 5 minutes"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def publish_to_github_pages(commit_message: str = None) -> dict:
    """
    Commit changed files in webroot/ and push to origin (GitHub Pages).
    Never force-pushes. Returns git commands if manual fallback needed.
    """
    if commit_message is None:
        commit_message = f"chore: publish store update {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    webroot = config.ROOT_DIR / "webroot"
    if not (webroot / ".git").exists() and not (config.ROOT_DIR / ".git").exists():
        return {"ok": False, "error": "Not a git repository"}

    try:
        # Check status
        status_result = subprocess.run(
            ["git", "status", "--porcelain", "webroot/"],
            cwd=str(config.ROOT_DIR),
            capture_output=True, text=True, encoding="utf-8"
        )
        if not status_result.stdout.strip():
            return {"ok": True, "message": "No changes to publish", "changed_files": []}

        # Get list of changed files
        changed = [line.strip()[3:] for line in status_result.stdout.strip().split("\n") if line.strip()]

        # Add and commit
        subprocess.run(["git", "add", "webroot/"], cwd=str(config.ROOT_DIR), check=True)
        subprocess.run(["git", "commit", "-m", commit_message], cwd=str(config.ROOT_DIR), check=True)

        # Push (no force)
        push_result = subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=str(config.ROOT_DIR),
            capture_output=True, text=True, encoding="utf-8"
        )

        if push_result.returncode != 0:
            # Provide manual fallback commands
            return {
                "ok": False,
                "error": push_result.stderr,
                "manual_fallback": [
                    f"cd {config.ROOT_DIR}",
                    "git add webroot/",
                    f'git commit -m "{commit_message}"',
                    "git push origin HEAD"
                ],
                "changed_files": changed
            }

        return {"ok": True, "message": "Published to GitHub Pages", "changed_files": changed}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "error": str(exc), "manual_fallback": [
            f"cd {config.ROOT_DIR}",
            "git add webroot/",
            f'git commit -m "{commit_message}"',
            "git push origin HEAD"
        ]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def full_publish_preview() -> dict:
    """
    Full publish preview: generate catalog, build pages, show diff of changed files
    WITHOUT actually committing or pushing.
    """
    import tempfile
    import subprocess
    import os
    from pathlib import Path
    
    # 1. Generate catalog
    catalog = generate_catalog()
    write_catalog(catalog)
    
    # 2. Build Mini App pages
    build_result = build_store_pages()
    if not build_result.get("ok"):
        return {"ok": False, "stage": "build", "error": build_result.get("error")}
    
    # 3. Get git diff of webroot changes (without committing)
    webroot = config.ROOT_DIR / "webroot"
    try:
        # Get status (--untracked-files=all so new files are listed
        # individually instead of a single "webroot/" directory entry)
        status_result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "webroot/"],
            cwd=str(config.ROOT_DIR),
            capture_output=True, text=True, encoding="utf-8"
        )
        changed = [line.strip()[3:] for line in status_result.stdout.strip().split("\n") if line.strip()]
        
        if not changed:
            return {"ok": True, "message": "No changes to publish", "changed_files": [], "diff": ""}
        
        # Get detailed diff for each changed file
        diff_result = subprocess.run(
            ["git", "diff", "webroot/"],
            cwd=str(config.ROOT_DIR),
            capture_output=True, text=True, encoding="utf-8"
        )
        
        return {
            "ok": True,
            "message": "Preview of changes that would be published",
            "changed_files": changed,
            "diff": diff_result.stdout,
            "catalog_items": len(catalog)
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def full_publish() -> dict:
    """Full pipeline: generate catalog -> build pages -> commit & push."""
    # 1. Generate catalog
    catalog = generate_catalog()
    write_catalog(catalog)

    # 2. Build Mini App pages
    build_result = build_store_pages()
    if not build_result.get("ok"):
        return {"ok": False, "stage": "build", "error": build_result.get("error")}

    # 3. Publish to GitHub Pages
    publish_result = publish_to_github_pages()
    if not publish_result.get("ok"):
        return {"ok": False, "stage": "publish", "error": publish_result.get("error"),
                "manual_fallback": publish_result.get("manual_fallback")}

    return {"ok": True, "catalog_items": len(catalog), "changed_files": publish_result.get("changed_files", [])}


# ─────────────────────────────────────────────────────────────────────────────
# Categories Management
# ─────────────────────────────────────────────────────────────────────────────

def get_categories() -> list:
    """Get distinct categories from store_items."""
    db = get_db()
    if db is None:
        return []
    try:
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM store_items ORDER BY category"
            ).fetchall()
        return [r["category"] for r in rows if r["category"]]
    except Exception:
        return []


def get_store_stats() -> dict:
    """Aggregate stats across all store items."""
    db = get_db()
    if db is None:
        return {"total_views": 0, "total_opens": 0, "total_clicks": 0, "total": 0, "live_count": 0, "hidden_count": 0, "coming_soon_count": 0}
    try:
        with db._get_conn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(views), 0) as total_views,
                    COALESCE(SUM(opens), 0) as total_opens,
                    COALESCE(SUM(clicks), 0) as total_clicks,
                    SUM(CASE WHEN status='live' THEN 1 ELSE 0 END) as live_count,
                    SUM(CASE WHEN status='hidden' THEN 1 ELSE 0 END) as hidden_count,
                    SUM(CASE WHEN status='coming_soon' THEN 1 ELSE 0 END) as coming_soon_count
                FROM store_items
            """).fetchone()
        return dict(row) if row else {"total_views": 0, "total_opens": 0, "total_clicks": 0, "total": 0, "live_count": 0, "hidden_count": 0, "coming_soon_count": 0}
    except Exception:
        return {"total_views": 0, "total_opens": 0, "total_clicks": 0, "total": 0, "live_count": 0, "hidden_count": 0, "coming_soon_count": 0}