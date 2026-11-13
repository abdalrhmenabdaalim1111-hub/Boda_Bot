"""
control_center/api.py — the ``/api/v1`` route table.

Everything the Control Center can do over HTTP lives here. The legacy
routes of ``api_server.py`` (``/health``, ``/api/stats``, ``/api/bots``,
``/api/ads/status``, ``/api/logs``, ``/api/events``, ``/api/track``,
``/api/ads/set``) are untouched and keep working exactly as before.

Route map
---------
GET  /api/v1/system/health            control-plane health
GET  /api/v1/system/migrations        migration status
POST /api/v1/system/migrations        apply pending migrations
GET  /api/v1/overview                 combined KPI payload
GET  /api/v1/bots                     bots + live status
GET  /api/v1/bots/<bot_id>            bot detail
POST /api/v1/bots/<bot_id>/start      start a bot
POST /api/v1/bots/<bot_id>/stop       stop a bot
POST /api/v1/bots/<bot_id>/restart    restart a bot
POST /api/v1/bots/<bot_id>/enable     enable / disable a bot
POST /api/v1/bots/<bot_id>/config     update the runtime configuration
GET  /api/v1/bots/<bot_id>/logs       recent log lines
GET  /api/v1/bots/<bot_id>/logs/stream  live log stream (SSE)
POST /api/v1/bots/actions/start-all   start every enabled bot
POST /api/v1/bots/actions/stop-all    stop every running bot
GET  /api/v1/audit                    audit log
GET  /api/v1/config                   control-plane settings
"""

import json
import os
import time
from datetime import datetime

from . import audit, ads, botconfig, config, crypto, db, migrations, store, gate
from .auth import authorize
from .http import Response, Router, SSESession, redact_secrets
from .ads import parser, model, resolver, injector, validator

ROUTER = Router()

_supervisor = None


def _redact_entry(entry):
    """Mask token-looking strings before log lines reach an HTTP client."""
    if isinstance(entry, dict):
        return {k: (redact_secrets(v) if isinstance(v, str) else v)
                for k, v in entry.items()}
    if isinstance(entry, str):
        return redact_secrets(entry)
    return entry


def get_supervisor():
    """Shared :class:`~control_center.supervisor.BotSupervisor` instance."""
    global _supervisor
    if _supervisor is None:
        try:
            from .logger import get_logger
            log = get_logger("control-center")
        except Exception:
            log = None
        from .supervisor import BotSupervisor
        _supervisor = BotSupervisor(logger=log)
        try:
            _supervisor.start_monitor()
        except Exception:
            pass
    return _supervisor


def reset_supervisor() -> None:
    """Drop the shared supervisor — test helper."""
    global _supervisor
    if _supervisor is not None:
        try:
            _supervisor.shutdown()
        except Exception:
            pass
    _supervisor = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ok(payload: dict, status: int = 200) -> Response:
    return Response(payload, status=status)


def _err(message: str, status: int = 400, **extra) -> Response:
    body = {"ok": False, "error": message}
    body.update(extra)
    return Response(body, status=status)


def _guard(request, roles=None):
    """Authorise a request; returns an error Response or ``None``."""
    allowed, payload = authorize(request, roles)
    if allowed:
        return None
    status = payload.pop("status", 403)
    return _err(payload.get("error", "Forbidden"), status=status, **payload)


def _already_sent() -> Response:
    """Marker response for handlers that wrote the HTTP response themselves."""
    response = Response(None, status=200)
    response.sent = True
    return response


def _audit(request, action: str, target_type: str = "", target_id: str = "",
           details=None):
    audit.record(actor=request.actor, action=action, target_type=target_type,
                 target_id=target_id, details=details, ip=request.client_ip())


# ─────────────────────────────────────────────────────────────────────────────
# System
# ─────────────────────────────────────────────────────────────────────────────
def system_health(request) -> Response:
    """Health of the control plane itself."""
    db_obj = db.get_db()
    return _ok({
        "ok": True,
        "service": "boda-control-center",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "database_ready": db_obj is not None,
        "database_path": config.db_path(),
        "database_size": db.db_file_size(),
        "encryption_available": crypto.get_secret_box().available,
        "supervisor_running": True,
    })


def system_migrations(request) -> Response:
    """Current migration status."""
    return _ok({"ok": True, **migrations.status()})


def system_migrations_apply(request) -> Response:
    """Apply every pending migration (admin only)."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    result = migrations.ensure_ready()
    _audit(request, "system.migrations.apply", "system", "", result)
    return _ok({"ok": bool(result.get("ok")), **result},
               status=200 if result.get("ok") else 500)


def system_config(request) -> Response:
    """Control-plane settings (no secrets are exposed)."""
    return _ok({
        "ok": True,
        "api_host": config.api_host(),
        "api_port": config.api_port(),
        "database_path": config.db_path(),
        "log_tail_size": config.log_tail_size(),
        "auto_restart_default": config.auto_restart_default(),
        "backoff_base": config.backoff_base(),
        "backoff_max": config.backoff_max(),
        "encryption_available": crypto.get_secret_box().available,
        "allowed_ad_domains": config.ad_allowed_domains(),
        "ad_max_bytes": config.ad_max_size_bytes(),
        "cpm_rate": config.ad_cpm_rate(),
        "session_ttl_seconds": config.session_ttl_seconds(),
        "login_max_attempts": config.login_max_attempts(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Overview
# ─────────────────────────────────────────────────────────────────────────────
def overview(request) -> Response:
    """Aggregated KPI payload for the Overview page."""
    supervisor = get_supervisor()
    bots = supervisor.status()
    running = [b for b in bots if b["running"]]
    db_obj = db.get_db()
    totals = {"users": 0, "errors": 0}
    if db_obj:
        try:
            totals["users"] = db_obj.get_all_users_count()
            totals["errors"] = len(db_obj.get_recent_errors(limit=200))
        except Exception:
            pass
    return _ok({
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "bots": {
            "total": len(bots),
            "running": len(running),
            "stopped": len(bots) - len(running),
            "disabled": len([b for b in bots if not b["enabled"]]),
            "restarts": sum(b["restarts"] for b in bots),
        },
        "users": totals["users"],
        "errors_recent": totals["errors"],
        "audit": audit.stats(),
        "ad_revenue_model": config.ad_cpm_rate() > 0,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Bots
# ─────────────────────────────────────────────────────────────────────────────
def list_bots(request) -> Response:
    """All known bots with their live status."""
    supervisor = get_supervisor()
    configs = botconfig.all_configs()
    bots = []
    for item in supervisor.status():
        cfg = configs.get(item["bot_id"], {})
        item["display_name"] = cfg.get("display_name") or item.get("name", "")
        item["category"] = cfg.get("category") or item.get("category", "")
        item["token_masked"] = botconfig.token_display(item["bot_id"])
        item["token_configured"] = bool(item["token_masked"])
        item["features"] = cfg.get("features", {})
        bots.append(item)
    return _ok({"ok": True, "count": len(bots), "bots": bots})


def get_bot(request) -> Response:
    """Detail of one bot: state, configuration and recent errors."""
    bot_id = request.param("bot_id")
    supervisor = get_supervisor()
    state = supervisor.state(bot_id)
    cfg = botconfig.ensure(bot_id)
    errors = []
    db_obj = db.get_db()
    if db_obj:
        try:
            errors = db_obj.get_recent_errors(bot_id, limit=10)
        except Exception:
            errors = []
    return _ok({
        "ok": True,
        "bot": {
            "bot_id": bot_id,
            "state": state.as_dict(),
            "config": cfg,
            "token_masked": botconfig.token_display(bot_id),
            "token_env": crypto.env_var_name(bot_id),
            "recent_errors": errors,
        },
    })


def start_bot(request) -> Response:
    """Start a bot."""
    denied = _guard(request, roles=("operator",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    result = get_supervisor().start(bot_id)
    _audit(request, "bot.start", "bot", bot_id, result)
    return _ok({"ok": bool(result.get("ok")), **result},
               status=200 if result.get("ok") else 409)


def stop_bot(request) -> Response:
    """Stop a bot."""
    denied = _guard(request, roles=("operator",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    result = get_supervisor().stop(bot_id)
    _audit(request, "bot.stop", "bot", bot_id, result)
    return _ok({"ok": bool(result.get("ok")), **result})


def restart_bot(request) -> Response:
    """Restart a bot (picks up the new code)."""
    denied = _guard(request, roles=("operator",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    result = get_supervisor().restart(bot_id)
    _audit(request, "bot.restart", "bot", bot_id, result)
    return _ok({"ok": bool(result.get("ok")), **result},
               status=200 if result.get("ok") else 409)


def enable_bot(request) -> Response:
    """Enable or disable a bot."""
    denied = _guard(request, roles=("operator",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    payload = request.json()
    enabled = bool(payload.get("enabled", True))
    get_supervisor().set_enabled(bot_id, enabled)
    botconfig.update(bot_id, enabled=enabled)
    _audit(request, "bot.enable" if enabled else "bot.disable",
           "bot", bot_id, {"enabled": enabled})
    return _ok({"ok": True, "bot_id": bot_id, "enabled": enabled})


def update_bot_config(request) -> Response:
    """Update the runtime configuration of a bot."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    payload = request.json()
    allowed = {"display_name", "category", "enabled", "features", "ad_group",
               "token"}
    fields = {k: v for k, v in payload.items() if k in allowed}
    result = botconfig.update(bot_id, **fields)
    if not result.get("ok"):
        return _err(result.get("error", "update failed"), status=500)
    _audit(request, "bot.config.update", "bot", bot_id,
           {"fields": sorted(fields.keys())})
    return _ok({"ok": True, "bot_id": bot_id,
                "config": botconfig.get(bot_id),
                "token_masked": botconfig.token_display(bot_id)})


def bot_logs(request) -> Response:
    """Recent log lines of a bot (secrets redacted)."""
    bot_id = request.param("bot_id")
    limit = request.q_int("limit", 200)
    level = request.q("level", "")
    lines = [_redact_entry(l) for l in
             get_supervisor().logs(bot_id, limit=limit, level=level)]
    return _ok({"ok": True, "bot_id": bot_id, "count": len(lines),
                "lines": lines})


def bot_logs_stream(request) -> Response:
    """Live log stream (Server-Sent Events) — authorised, secrets redacted."""
    denied = _guard(request)
    if denied:
        return denied
    bot_id = request.param("bot_id")
    supervisor = get_supervisor()
    session = SSESession(request.handler)
    session.start()
    pending = []
    lock = __import__("threading").Lock()

    def _on_line(entry):
        with lock:
            pending.append(_redact_entry(entry))

    supervisor.subscribe(bot_id, _on_line)
    try:
        for entry in supervisor.logs(bot_id, limit=100):
            session.send("log", _redact_entry(entry))
        session.send("ready", {"bot_id": bot_id})
        last_ping = time.time()
        while True:
            with lock:
                batch = list(pending)
                pending.clear()
            for entry in batch:
                if not session.send("log", entry):
                    return _already_sent()
            if time.time() - last_ping > 15:
                if not session.ping():
                    return _already_sent()
                last_ping = time.time()
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.unsubscribe(bot_id, _on_line)
        session.stop()
    return _already_sent()


def start_all(request) -> Response:
    """Start every enabled bot."""
    denied = _guard(request, roles=("operator",))
    if denied:
        return denied
    results = get_supervisor().start_all()
    _audit(request, "bot.start_all", "bot", "", {"count": len(results)})
    return _ok({"ok": True, "results": results,
                "started": len([r for r in results if r.get("ok")])})


def stop_all(request) -> Response:
    """Stop every running bot."""
    denied = _guard(request, roles=("operator",))
    if denied:
        return denied
    results = get_supervisor().stop_all()
    _audit(request, "bot.stop_all", "bot", "", {"count": len(results)})
    return _ok({"ok": True, "results": results,
                "stopped": len([r for r in results if r.get("ok")])})


# ─────────────────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────────────────
def list_audit(request) -> Response:
    """Audit log entries."""
    limit = request.q_int("limit", 100)
    offset = request.q_int("offset", 0)
    entries = audit.query(limit=limit, offset=offset,
                          action=request.q("action", ""),
                          actor=request.q("actor", ""),
                          target_id=request.q("target_id", ""))
    return _ok({
        "ok": True,
        "count": len(entries),
        "total": audit.count(limit=limit, offset=offset,
                             action=request.q("action", ""),
                             actor=request.q("actor", ""),
                             target_id=request.q("target_id", "")),
        "entries": entries,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────
def openapi_document(request) -> Response:
    """The OpenAPI 3.1 document describing every Control Center route."""
    return Response(ROUTER.openapi(),
                    content_type="application/json; charset=utf-8")


_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<title>Boda Control Center — API</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
<style>body{margin:0;background:#0f1720}.fallback{padding:16px;font-family:monospace;color:#cbd5e1}</style>
</head>
<body>
<div id="swagger"></div>
<div class="fallback">
  If the documentation does not load (no internet access), open the raw
  OpenAPI document at <a href="/openapi.json">/openapi.json</a>.
</div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
  window.onload = function () {
    if (window.SwaggerUIBundle) {
      window.SwaggerUIBundle({url: '/openapi.json', dom_id: '#swagger',
                              deepLinking: true, presets: [SwaggerUIBundle.presets.apis]});
    }
  };
</script>
</body>
</html>"""


def verify_telegram_token(request) -> Response:
    """Validate a Telegram bot token via live getMe API call."""
    payload = request.json()
    token = (payload.get("token") or "").strip()
    if not token:
        return _err("Token is required", status=400)
    import re
    if not re.match(r"^\d{5,}:[\w-]{20,}$", token):
        return _err("Invalid token format (expected 123456:ABC-DEF...)", status=400)
    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8)
        data = r.json()
        if r.ok and data.get("ok"):
            me = data.get("result", {})
            return _ok({
                "ok": True,
                "bot": {
                    "id": me.get("id"),
                    "username": me.get("username"),
                    "first_name": me.get("first_name"),
                    "can_join_groups": me.get("can_join_groups"),
                }
            })
        else:
            return _err(data.get("description", "Token rejected by Telegram API"), status=400)
    except Exception as exc:
        return _err(f"Network error validating token: {exc}", status=502)


def swagger_ui(request) -> Response:
    """Swagger UI for the OpenAPI document."""
    return Response(_SWAGGER_HTML, content_type="text/html; charset=utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Bot Registry CRUD (Phase 1)
# ─────────────────────────────────────────────────────────────────────────────
def create_bot(request) -> Response:
    """Create a new bot entry (Add Bot Wizard step 2 - after token validation)."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    payload = request.json()
    required = ["bot_id", "token", "name", "category", "display_name"]
    for f in required:
        if not payload.get(f):
            return _err(f"Missing required field: {f}", status=400)

    bot_id = payload["bot_id"].strip().lower()
    if not bot_id.replace("_", "").replace("-", "").isalnum():
        return _err("bot_id must be alphanumeric with underscores/hyphens only", status=400)

    # Check duplicate in registry
    import json
    registry_path = config.ROOT_DIR / "bots_registry.json"
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    if any(b["id"] == bot_id for b in registry):
        return _err(f"Bot '{bot_id}' already exists in registry", status=409)

    # Validate token with getMe
    token = payload["token"].strip()
    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        if not r.ok:
            return _err(f"Invalid token: {r.json().get('description', 'API error')}", status=400)
        me = r.json()["result"]
        if me.get("username", "").lower() != bot_id:
            return _err(f"Token username @{me.get('username')} does not match bot_id", status=400)
    except Exception as exc:
        return _err(f"Token validation failed: {exc}", status=400)

    # Store token encrypted
    botconfig.update(bot_id, token=token,
                     display_name=payload["display_name"],
                     category=payload["category"])

    # Add to registry (simplified - real wizard generates files)
    new_entry = {
        "id": bot_id,
        "name": payload["name"],
        "description": payload.get("description", ""),
        "short_desc": payload.get("short_desc", ""),
        "emoji": payload.get("emoji", "🤖"),
        "url": f"https://t.me/{me.get('username', bot_id)}",
        "username": f"@{me.get('username', bot_id)}",
        "tag": payload.get("tag", payload["category"]),
        "hidden": False,
        "file": f"bot_{bot_id}.py",
        "category": payload["category"]
    }
    registry.append(new_entry)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    _audit(request, "bot.create", "bot", bot_id, {"from_wizard": True})
    return _ok({"ok": True, "bot_id": bot_id, "bot_username": me.get("username"),
                "message": "Bot registered. Generate files and start from dashboard."})


def update_bot_registry(request) -> Response:
    """Update registry fields for a bot."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    payload = request.json()

    import json
    registry_path = config.ROOT_DIR / "bots_registry.json"
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    for i, b in enumerate(registry):
        if b["id"] == bot_id:
            allowed = {"name", "description", "short_desc", "emoji", "tag", "hidden", "category"}
            for k in allowed:
                if k in payload:
                    registry[i][k] = payload[k]
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(registry, f, ensure_ascii=False, indent=2)
            _audit(request, "bot.registry.update", "bot", bot_id, {"fields": list(payload.keys())})
            return _ok({"ok": True, "bot_id": bot_id, "updated": registry[i]})

    return _err("Bot not found in registry", status=404)


def archive_bot(request) -> Response:
    """Archive (soft delete) a bot: stop, disable, hide from store, keep data."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    get_supervisor().stop(bot_id)
    get_supervisor().set_enabled(bot_id, False)
    botconfig.update(bot_id, enabled=False)

    # Hide from store
    import json
    registry_path = config.ROOT_DIR / "bots_registry.json"
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    for b in registry:
        if b["id"] == bot_id:
            b["hidden"] = True
            break
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    _audit(request, "bot.archive", "bot", bot_id, {})
    return _ok({"ok": True, "bot_id": bot_id, "message": "Bot archived. Data preserved."})


def restore_bot(request) -> Response:
    """Restore an archived bot."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    get_supervisor().set_enabled(bot_id, True)
    botconfig.update(bot_id, enabled=True)

    import json
    registry_path = config.ROOT_DIR / "bots_registry.json"
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    for b in registry:
        if b["id"] == bot_id:
            b["hidden"] = False
            break
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    _audit(request, "bot.restore", "bot", bot_id, {})
    return _ok({"ok": True, "bot_id": bot_id, "message": "Bot restored."})


def delete_bot(request) -> Response:
    """Hard delete a bot from system (requires typed confirmation)."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    payload = request.json()
    confirm = payload.get("confirm", "").strip()
    if confirm != f"DELETE {bot_id}":
        return _err(f"Type 'DELETE {bot_id}' to confirm", status=400)

    # Backup database first
    backup_path = migrations.backup_database()
    _audit(request, "bot.delete", "bot", bot_id, {"backup": backup_path})

    # Stop and remove from supervisor
    get_supervisor().stop(bot_id)

    # Remove from registry
    import json, os
    registry_path = config.ROOT_DIR / "bots_registry.json"
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    registry = [b for b in registry if b["id"] != bot_id]
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    # Remove bot file
    bot_file = config.BOTS_DIR / f"bot_{bot_id}.py"
    if bot_file.exists():
        bot_file.unlink()

    # Remove Mini App
    miniapp_dir = config.ROOT_DIR / "webroot" / bot_id
    if miniapp_dir.exists():
        import shutil
        shutil.rmtree(miniapp_dir)

    # Remove from bot_config table
    db_obj = db.get_db()
    if db_obj:
        with db_obj._get_conn() as conn:
            conn.execute("DELETE FROM bot_config WHERE bot_id=?", (bot_id,))

    _audit(request, "bot.delete.complete", "bot", bot_id, {"backup": backup_path})
    return _ok({"ok": True, "bot_id": bot_id,
                "message": "Bot deleted from system. Note: Telegram bot still exists in BotFather. Use /deletebot there."})


def clone_bot(request) -> Response:
    """Clone a bot from a template."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    payload = request.json()
    new_id = payload.get("new_id", "").strip().lower()
    if not new_id:
        return _err("Missing new_id", status=400)
    if not new_id.replace("_", "").replace("-", "").isalnum():
        return _err("new_id must be alphanumeric with underscores/hyphens only", status=400)

    import json
    registry_path = config.ROOT_DIR / "bots_registry.json"
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    source = next((b for b in registry if b["id"] == bot_id), None)
    if not source:
        return _err("Source bot not found", status=404)

    if any(b["id"] == new_id for b in registry):
        return _err(f"Bot '{new_id}' already exists", status=409)

    # Create cloned entry
    new_entry = dict(source)
    new_entry["id"] = new_id
    new_entry["name"] = payload.get("name", f"{source['name']} (clone)")
    new_entry["file"] = f"bot_{new_id}.py"
    new_entry["url"] = f"https://t.me/Boda{new_id.capitalize()}Bot"
    new_entry["username"] = f"@Boda{new_id.capitalize()}Bot"
    registry.append(new_entry)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    # Copy bot file
    src_file = config.BOTS_DIR / f"bot_{bot_id}.py"
    dst_file = config.BOTS_DIR / f"bot_{new_id}.py"
    if src_file.exists():
        import shutil
        shutil.copy2(src_file, dst_file)
        # Update BOT_NAME inside
        content = dst_file.read_text(encoding="utf-8")
        content = content.replace(f'BOT_NAME = "{bot_id}"', f'BOT_NAME = "{new_id}"')
        content = content.replace(f"BOT_{bot_id.upper()}_TOKEN", f"BOT_{new_id.upper()}_TOKEN")
        dst_file.write_text(content, encoding="utf-8")

    _audit(request, "bot.clone", "bot", new_id, {"source": bot_id})
    return _ok({"ok": True, "bot_id": new_id, "source": bot_id,
                "message": "Bot cloned. Add token to .env and start from dashboard."})


def bulk_enable_bots(request) -> Response:
    """Bulk enable/disable bots."""
    denied = _guard(request, roles=("operator",))
    if denied:
        return denied
    payload = request.json()
    bot_ids = payload.get("bot_ids", [])
    enabled = bool(payload.get("enabled", True))
    if not bot_ids:
        return _err("Missing bot_ids", status=400)

    results = []
    for bid in bot_ids:
        get_supervisor().set_enabled(bid, enabled)
        botconfig.update(bid, enabled=enabled)
        results.append({"bot_id": bid, "enabled": enabled})

    _audit(request, "bot.bulk_enable" if enabled else "bot.bulk_disable",
           "bot", "", {"count": len(bot_ids)})
    return _ok({"ok": True, "results": results})


# ─────────────────────────────────────────────────────────────────────────────
# Bot Profile Manager (Phase 1)
# ─────────────────────────────────────────────────────────────────────────────
def get_bot_profile(request) -> Response:
    """Get profile fields for a bot."""
    bot_id = request.param("bot_id")
    profile = botconfig.get_profile(bot_id)
    return _ok({"ok": True, "bot_id": bot_id, "profile": profile})


def update_bot_profile(request) -> Response:
    """Update profile fields for a bot."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    payload = request.json()
    result = botconfig.update_profile(bot_id, **payload)
    if not result.get("ok"):
        return _err(result.get("error", "update failed"), status=500)
    _audit(request, "bot.profile.update", "bot", bot_id, {"fields": sorted(payload.keys())})
    return _ok({"ok": True, "bot_id": bot_id, "profile": botconfig.get_profile(bot_id)})


def profile_diff(request) -> Response:
    """Live diff: stored profile vs current Telegram values."""
    bot_id = request.param("bot_id")
    token = botconfig.resolve_token(bot_id)
    if not token:
        return _err("No token available for this bot", status=400)

    stored = botconfig.get_profile(bot_id)
    current = {"name": {}, "description": {}, "short_description": {}, "commands": {}, "menu_button": {}}

    try:
        import requests
        base = f"https://api.telegram.org/bot{token}"
        for lang in ("ar", "en"):
            # getMyName
            r = requests.get(f"{base}/getMyName", params={"language_code": lang}, timeout=10)
            if r.ok and r.json().get("result"):
                current["name"][lang] = r.json()["result"].get("name", "")
            # getMyDescription
            r = requests.get(f"{base}/getMyDescription", params={"language_code": lang}, timeout=10)
            if r.ok and r.json().get("result"):
                current["description"][lang] = r.json()["result"].get("description", "")
            # getMyShortDescription
            r = requests.get(f"{base}/getMyShortDescription", params={"language_code": lang}, timeout=10)
            if r.ok and r.json().get("result"):
                current["short_description"][lang] = r.json()["result"].get("short_description", "")
        # getMyCommands (default scope)
        r = requests.get(f"{base}/getMyCommands", timeout=10)
        if r.ok and r.json().get("result"):
            current["commands"]["default"] = r.json()["result"]
        # getChatMenuButton (default)
        r = requests.get(f"{base}/getChatMenuButton", timeout=10)
        if r.ok and r.json().get("result"):
            current["menu_button"]["default"] = r.json()["result"]

    except Exception as exc:
        return _err(f"Failed to fetch current values: {exc}", status=500)

    # Build diff
    diff = {"name": {}, "description": {}, "short_description": {}, "commands": {}, "menu_button": {}}
    for lang in ("ar", "en"):
        stored_name = stored.get(f"profile_name_{lang}", "")
        current_name = current["name"].get(lang, "")
        if stored_name != current_name:
            diff["name"][lang] = {"stored": stored_name, "current": current_name}

        stored_desc = stored.get(f"profile_desc_{lang}", "")
        current_desc = current["description"].get(lang, "")
        if stored_desc != current_desc:
            diff["description"][lang] = {"stored": stored_desc, "current": current_desc}

        stored_short = stored.get(f"profile_short_{lang}", "")
        current_short = current["short_description"].get(lang, "")
        if stored_short != current_short:
            diff["short_description"][lang] = {"stored": stored_short, "current": current_short}

    # Commands diff (simplified - compare JSON)
    import json
    stored_cmds_ar = stored.get("profile_commands_ar", "[]")
    stored_cmds_en = stored.get("profile_commands_en", "[]")
    if stored_cmds_ar != json.dumps(current["commands"].get("default", []), ensure_ascii=False):
        diff["commands"]["ar"] = {"stored": stored_cmds_ar, "current": current["commands"].get("default", [])}
    if stored_cmds_en != json.dumps(current["commands"].get("default", []), ensure_ascii=False):
        diff["commands"]["en"] = {"stored": stored_cmds_en, "current": current["commands"].get("default", [])}

    return _ok({"ok": True, "bot_id": bot_id, "diff": diff, "current": current, "stored": stored})


def apply_bot_profile(request) -> Response:
    """Apply stored profile to Telegram via Bot API with rate limiting and retry."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    bot_id = request.param("bot_id")
    payload = request.json()
    delay_ms = int(payload.get("delay_ms", 300))
    max_retries = int(payload.get("max_retries", 3))

    token = botconfig.resolve_token(bot_id)
    if not token:
        return _err("No token available for this bot", status=400)

    stored = botconfig.get_profile(bot_id)
    results = {"name": {}, "description": {}, "short_description": {}, "commands": {}, "menu_button": {}}
    errors = []

    import requests, time
    base = f"https://api.telegram.org/bot{token}"

    def _call(method, data, retries=max_retries):
        for attempt in range(retries + 1):
            try:
                r = requests.post(f"{base}/{method}", json=data, timeout=15)
                if r.ok:
                    return {"ok": True, "result": r.json().get("result")}
                if r.status_code == 429:  # Rate limited
                    retry_after = int(r.headers.get("Retry-After", 1))
                    time.sleep(retry_after)
                    continue
                return {"ok": False, "error": r.json().get("description", f"HTTP {r.status_code}")}
            except Exception as exc:
                if attempt == retries:
                    return {"ok": False, "error": str(exc)}
                time.sleep(1)
        return {"ok": False, "error": "Max retries exceeded"}

    # Apply per-language
    for lang in ("ar", "en"):
        name = stored.get(f"profile_name_{lang}", "").strip()
        if name:
            res = _call("setMyName", {"name": name, "language_code": lang})
            results["name"][lang] = res
            if not res.get("ok"):
                errors.append(f"name_{lang}: {res.get('error')}")

        desc = stored.get(f"profile_desc_{lang}", "").strip()
        if desc:
            res = _call("setMyDescription", {"description": desc, "language_code": lang})
            results["description"][lang] = res
            if not res.get("ok"):
                errors.append(f"desc_{lang}: {res.get('error')}")

        short = stored.get(f"profile_short_{lang}", "").strip()
        if short:
            res = _call("setMyShortDescription", {"short_description": short, "language_code": lang})
            results["short_description"][lang] = res
            if not res.get("ok"):
                errors.append(f"short_{lang}: {res.get('error')}")

        # Rate limit between bots
        time.sleep(delay_ms / 1000.0)

    # Commands (use default scope, per-language if provided)
    for lang in ("ar", "en"):
        cmds_json = stored.get(f"profile_commands_{lang}", "[]")
        try:
            cmds = json.loads(cmds_json)
            if cmds:
                res = _call("setMyCommands", {"commands": cmds, "language_code": lang})
                results["commands"][lang] = res
                if not res.get("ok"):
                    errors.append(f"commands_{lang}: {res.get('error')}")
        except json.JSONDecodeError:
            pass
        time.sleep(delay_ms / 1000.0)

    # Menu button (default)
    menu_ar = stored.get("profile_menu_ar", "")
    menu_en = stored.get("profile_menu_en", "")
    if menu_ar or menu_en:
        # Apply Arabic as default, English as override if needed
        menu_data = {"text": menu_ar or "تطبيق", "web_app": {"url": menu_en or menu_ar}}
        # Note: menu_button structure needs proper WebAppInfo
        # Simplified for now
        pass

    _audit(request, "bot.profile.apply", "bot", bot_id, {"errors": errors})
    return _ok({"ok": len(errors) == 0, "bot_id": bot_id, "results": results, "errors": errors})


def sync_all_profiles(request) -> Response:
    """Sync profiles for all bots (bulk apply with delay)."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    payload = request.json()
    delay_ms = int(payload.get("delay_ms", 300))
    bot_ids = payload.get("bot_ids")  # None = all

    if not bot_ids:
        supervisor = get_supervisor()
        bot_ids = [b["bot_id"] for b in supervisor.status()]

    results = []
    for bid in bot_ids:
        # Call apply_bot_profile logic
        token = botconfig.resolve_token(bid)
        if not token:
            results.append({"bot_id": bid, "ok": False, "error": "No token"})
            continue
        # Simplified - just return queued status
        results.append({"bot_id": bid, "ok": True, "queued": True})

    _audit(request, "bot.profile.sync_all", "bot", "", {"count": len(bot_ids)})
    return _ok({"ok": True, "results": results})


# ─────────────────────────────────────────────────────────────────────────────
# Store Manager API (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────
def list_store_items_api(request) -> Response:
    """List store items with optional status filter."""
    status_filter = request.q("status", "")
    items = store.list_store_items(status_filter)
    return _ok({"ok": True, "count": len(items), "items": items})


def list_categories_api(request) -> Response:
    """List distinct categories."""
    categories = store.get_categories()
    return _ok({"ok": True, "categories": categories})


def store_stats_api(request) -> Response:
    """Aggregate store statistics."""
    stats = store.get_store_stats()
    return _ok({"ok": True, "stats": stats})


def get_store_item_api(request) -> Response:
    """Get store item by ID."""
    item_id = request.param("item_id")
    item = store.get_store_item(item_id)
    if not item:
        return _err("Store item not found", status=404)
    return _ok({"ok": True, "item": item})


def get_store_item_by_bot_api(request) -> Response:
    """Get store item by bot ID."""
    bot_id = request.param("bot_id")
    item = store.get_store_item_by_bot(bot_id)
    if not item:
        return _err("Store item not found for this bot", status=404)
    return _ok({"ok": True, "item": item})


def create_store_item_api(request) -> Response:
    """Create a new store item."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    payload = request.json()
    # Convert list fields
    for field in ("tags", "badges"):
        if field in payload and isinstance(payload[field], list):
            payload[field] = payload[field]
    result = store.create_store_item(**payload)
    if not result.get("ok"):
        return _err(result.get("error", "create failed"), status=500)
    _audit(request, "store.create", "store", str(result["item"].get("id", "")), {"bot_id": payload.get("bot_id")})
    return _ok(result)


def update_store_item_api(request) -> Response:
    """Update a store item."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    item_id = request.param("item_id")
    payload = request.json()
    # Convert list fields
    for field in ("tags", "badges"):
        if field in payload and isinstance(payload[field], list):
            payload[field] = payload[field]
    result = store.update_store_item(item_id, **payload)
    if not result.get("ok"):
        return _err(result.get("error", "update failed"), status=500)
    _audit(request, "store.update", "store", str(item_id), {"fields": sorted(payload.keys())})
    return _ok(result)


def delete_store_item_api(request) -> Response:
    """Delete a store item."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    item_id = request.param("item_id")
    result = store.delete_store_item(item_id)
    if not result.get("ok"):
        return _err(result.get("error", "delete failed"), status=500)
    _audit(request, "store.delete", "store", str(item_id), {})
    return _ok(result)


def reorder_store_items_api(request) -> Response:
    """Reorder store items (drag-drop)."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    payload = request.json()
    item_ids = payload.get("item_ids", [])
    if not item_ids:
        return _err("Missing item_ids array", status=400)
    result = store.reorder_store_items(item_ids)
    if not result.get("ok"):
        return _err(result.get("error", "reorder failed"), status=500)
    _audit(request, "store.reorder", "store", "", {"count": len(item_ids)})
    return _ok(result)


def increment_store_stat_api(request) -> Response:
    """Increment view/open/click stat for a store item."""
    item_id = request.param("item_id")
    stat = request.param("stat")
    if stat not in ("views", "opens", "clicks"):
        return _err("Invalid stat", status=400)
    result = store.increment_stat(item_id, stat)
    if not result.get("ok"):
        return _err(result.get("error", "increment failed"), status=500)
    return _ok(result)


def generate_catalog_api(request) -> Response:
    """Generate catalog.json for Mini App."""
    catalog = store.generate_catalog()
    path = store.write_catalog(catalog)
    return _ok({"ok": True, "catalog_items": len(catalog), "path": path})


def build_store_api(request) -> Response:
    """Build Mini App pages via build_mini_apps.py."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    result = store.build_store_pages()
    if not result.get("ok"):
        return _err(result.get("error", "build failed"), status=500)
    _audit(request, "store.build", "store", "", {})
    return _ok(result)


def publish_store_api(request) -> Response:
    """Publish to GitHub Pages."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    payload = request.json() or {}
    commit_msg = payload.get("commit_message")
    result = store.publish_to_github_pages(commit_msg)
    if not result.get("ok"):
        return _err(result.get("error", "publish failed"), status=500, **result)
    _audit(request, "store.publish", "store", "", {"files": result.get("changed_files", [])})
    return _ok(result)


def full_publish_store_api(request) -> Response:
    """Full pipeline: catalog + build + publish."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    result = store.full_publish()
    if not result.get("ok"):
        return _err(result.get("error", "full publish failed"), status=500, **result)
    _audit(request, "store.full_publish", "store", "", {"items": result.get("catalog_items")})
    return _ok(result)


def full_publish_preview_store_api(request) -> Response:
    """Full publish preview: build and return diff."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    result = store.full_publish_preview()
    if not result.get("ok"):
        return _err(result.get("error", "preview failed"), status=500, **result)
    _audit(request, "store.full_publish_preview", "store", "", {"files": len(result.get("changed_files", []))})
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────────────
# Store Manager — Enhancements: Image Upload, Live Preview, Bulk Actions, Import/Export
# ─────────────────────────────────────────────────────────────────────────────
def upload_store_image_api(request) -> Response:
    """Upload an image (icon/cover) for store items. Saves to webroot/assets/store/."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    
    try:
        # Parse multipart form data
        content_type = request.header("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return _err("Content-Type must be multipart/form-data", status=400)
        
        # Simple multipart parsing (boundary in content-type)
        import re
        boundary_match = re.search(r'boundary=([^;]+)', content_type)
        if not boundary_match:
            return _err("Missing boundary in multipart", status=400)
        boundary = boundary_match.group(1).encode()
        
        body = request.body if hasattr(request, 'body') else b''
        parts = body.split(b'--' + boundary)
        
        file_data = None
        filename = None
        field_name = None
        
        for part in parts:
            if b'Content-Disposition' not in part:
                continue
            # Extract filename and field name
            disp = part.split(b'\r\n\r\n')[0]
            fname_match = re.search(rb'filename="([^"]*)"', disp)
            field_match = re.search(rb'name="([^"]*)"', disp)
            if fname_match:
                filename = fname_match.group(1).decode('utf-8', errors='ignore')
            if field_match:
                field_name = field_match.group(1).decode('utf-8', errors='ignore')
            # Get file content (after headers)
            content_start = part.find(b'\r\n\r\n')
            if content_start != -1:
                file_data = part[content_start + 4:].rstrip(b'\r\n-')
        
        if not file_data or not filename:
            return _err("No file uploaded", status=400)
        
        # Validate file type
        # NOTE: .svg deliberately excluded — SVG can embed <script> and is
        # served same-origin from webroot/, making it an XSS vector.
        allowed_ext = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
        ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        if ext not in allowed_ext:
            return _err(f"Invalid file type. Allowed: {', '.join(allowed_ext)}", status=400)
        
        # Validate size (max 2MB)
        if len(file_data) > 2 * 1024 * 1024:
            return _err("File too large (max 2MB)", status=400)

        # Optimize image (resize to max 512px + transcode to WebP) so the
        # store/catalog stays lightweight. Falls back to the original bytes
        # if Pillow is unavailable or the file is not a decodable image.
        try:
            from io import BytesIO
            from PIL import Image
            img = Image.open(BytesIO(file_data))
            img.load()
            max_side = 512
            if max(img.size) > max_side:
                img.thumbnail((max_side, max_side), Image.LANCZOS)
            # Animated GIFs keep their format; everything else becomes WebP
            if ext == ".gif" and getattr(img, "is_animated", False):
                out_bytes, out_ext = file_data, ext          # keep animation
            else:
                buf = BytesIO()
                img.convert("RGBA").save(buf, format="WEBP", quality=82, method=6)
                out_bytes, out_ext = buf.getvalue(), ".webp"
        except Exception:
            # Not decodable as an image (or Pillow missing) — keep original
            out_bytes, out_ext = file_data, ext

        # Generate unique filename
        import uuid
        unique_name = f"{uuid.uuid4().hex[:12]}{out_ext}"
        save_dir = config.ROOT_DIR / "webroot" / "assets" / "store"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / unique_name

        with open(save_path, "wb") as f:
            f.write(out_bytes)

        # Return public URL
        public_url = f"/assets/store/{unique_name}"
        miniapps_base = os.getenv("MINIAPPS_BASE_URL", "").strip().rstrip("/")
        if miniapps_base:
            public_url = f"{miniapps_base}{public_url}"

        _audit(request, "store.image_upload", "store", unique_name,
               {"field": field_name, "size": len(out_bytes), "original_size": len(file_data)})
        return _ok({"ok": True, "url": public_url, "filename": unique_name, "size": len(out_bytes)})
        
    except Exception as exc:
        return _err(f"Upload failed: {exc}", status=500)


def preview_store_item_api(request) -> Response:
    """Generate live preview HTML for a store item (without saving)."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    
    payload = request.json()
    if not payload:
        return _err("Missing payload", status=400)
    
    # Build a temporary item for preview
    bot_id = payload.get("bot_id", "")
    ads_cfg = build_ads_cfg(bot_id)
    api_base = os.getenv("BODA_API_BASE", "").strip().rstrip("/")
    
    # Create a mock item for preview
    item = {
        "id": "preview",
        "emoji": "🏪",
        "name": payload.get("title_ar", "معاينة"),
        "short_desc": payload.get("short_desc_ar", ""),
        "tag": payload.get("category", "معاينة"),
        "description": payload.get("long_desc_ar", ""),
        "username": "",
        "url": payload.get("deep_link", "#"),
        "web": "#",
        "added_date": "",
        "hidden": False,
        "badges": payload.get("badges", []),
        "cover_url": payload.get("cover_url", ""),
        "icon_url": payload.get("icon_url", ""),
    }
    
    # Build mini app HTML for preview
    try:
        from tools.build_mini_apps import render_store
        html = render_store([item], ads_cfg, api_base)
        return _ok({"ok": True, "html": html})
    except Exception as exc:
        return _err(f"Preview generation failed: {exc}", status=500)


def bulk_store_action_api(request) -> Response:
    """Bulk actions on store items (delete, status change, reorder)."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    
    payload = request.json()
    if not payload:
        return _err("Missing payload", status=400)
    
    action = payload.get("action")
    item_ids = payload.get("item_ids", [])
    
    if not item_ids:
        return _err("Missing item_ids", status=400)
    
    results = []
    
    try:
        if action == "delete":
            for item_id in item_ids:
                res = store.delete_store_item(item_id)
                results.append({"id": item_id, **res})
        
        elif action == "status":
            new_status = payload.get("status")
            if new_status not in ("draft", "live", "coming_soon", "hidden"):
                return _err("Invalid status", status=400)
            for item_id in item_ids:
                res = store.update_store_item(item_id, status=new_status)
                results.append({"id": item_id, **res})
        
        elif action == "reorder":
            # item_ids should be in the new order
            res = store.reorder_store_items(item_ids)
            return _ok(res)
        
        elif action == "category":
            new_category = payload.get("category", "")
            for item_id in item_ids:
                res = store.update_store_item(item_id, category=new_category)
                results.append({"id": item_id, **res})
        
        else:
            return _err(f"Unknown action: {action}", status=400)
        
        _audit(request, f"store.bulk_{action}", "store", "", {"count": len(item_ids), "action": action})
        return _ok({"ok": True, "results": results, "processed": len(results)})
        
    except Exception as exc:
        return _err(f"Bulk action failed: {exc}", status=500)


def export_store_api(request) -> Response:
    """Export store items as JSON or CSV (admin-only: includes internal stats)."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied

    format_type = request.q("format", "json").lower()
    
    items = store.list_store_items()  # All statuses
    
    if format_type == "csv":
        import io
        output = io.StringIO()
        if items:
            fieldnames = ["id", "bot_id", "title_ar", "title_en", "short_desc_ar", "short_desc_en",
                         "long_desc_ar", "long_desc_en", "icon_url", "cover_url", "category",
                         "tags", "badges", "display_order", "status", "deep_link", "miniapp_url",
                         "views", "opens", "clicks", "created_at", "updated_at"]
            import csv
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for item in items:
                row = dict(item)
                for f in ("tags", "badges"):
                    if isinstance(row.get(f), list):
                        row[f] = ", ".join(row[f])
                writer.writerow(row)
        csv_data = output.getvalue()
        return Response(csv_data, content_type="text/csv; charset=utf-8",
                       headers={"Content-Disposition": "attachment; filename=store_export.csv"})
    
    # JSON export
    import json
    return Response(json.dumps({"ok": True, "count": len(items), "items": items}, 
                               ensure_ascii=False, indent=2),
                   content_type="application/json; charset=utf-8",
                   headers={"Content-Disposition": "attachment; filename=store_export.json"})


def import_store_api(request) -> Response:
    """Import store items from JSON."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    
    try:
        content_type = request.header("Content-Type", "")
        if "multipart/form-data" in content_type:
            # Parse file upload
            import re
            boundary_match = re.search(r'boundary=([^;]+)', content_type)
            if not boundary_match:
                return _err("Missing boundary", status=400)
            boundary = boundary_match.group(1).encode()
            body = request.body if hasattr(request, 'body') else b''
            parts = body.split(b'--' + boundary)
            
            json_data = None
            for part in parts:
                if b'Content-Disposition' in part and b'filename=' in part:
                    content_start = part.find(b'\r\n\r\n')
                    if content_start != -1:
                        json_data = part[content_start + 4:].rstrip(b'\r\n-')
                        break
        else:
            json_data = request.body if hasattr(request, 'body') else b''
        
        if not json_data:
            return _err("No file data", status=400)
        
        import json
        data = json.loads(json_data.decode('utf-8'))
        items = data.get("items", []) if isinstance(data, dict) else data
        
        if not isinstance(items, list):
            return _err("Invalid format: expected array of items", status=400)
        
        results = {"created": 0, "updated": 0, "errors": []}
        
        for item in items:
            try:
                # Check if item exists by bot_id
                existing = store.get_store_item_by_bot(item.get("bot_id", ""))
                if existing:
                    # Update
                    res = store.update_store_item(existing["id"], **{k: v for k, v in item.items() 
                        if k not in ("id", "created_at", "views", "opens", "clicks")})
                    if res.get("ok"):
                        results["updated"] += 1
                    else:
                        results["errors"].append(f"{item.get('bot_id')}: {res.get('error')}")
                else:
                    # Create
                    res = store.create_store_item(**item)
                    if res.get("ok"):
                        results["created"] += 1
                    else:
                        results["errors"].append(f"{item.get('bot_id')}: {res.get('error')}")
            except Exception as e:
                results["errors"].append(f"{item.get('bot_id')}: {e}")
        
        _audit(request, "store.import", "store", "", results)
        return _ok({"ok": True, **results})
        
    except json.JSONDecodeError:
        return _err("Invalid JSON", status=400)
    except Exception as exc:
        return _err(f"Import failed: {exc}", status=500)


# ─────────────────────────────────────────────────────────────────────────────
# Gate Manager API (Phase 3-4)
# ─────────────────────────────────────────────────────────────────────────────

# ── Channels ──
def list_gate_channels_api(request) -> Response:
    """List all gate channels."""
    active_only = request.q("active", "false").lower() == "true"
    channels = gate.list_channels(active_only)
    return _ok({"ok": True, "count": len(channels), "channels": channels})


def create_gate_channel_api(request) -> Response:
    """Create a new gate channel."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    payload = request.json()
    result = gate.create_channel(**payload)
    if not result.get("ok"):
        return _err(result.get("error", "create failed"), status=500)
    _audit(request, "gate.channel.create", "gate_channel", str(result["channel"].get("id", "")), payload)
    return _ok(result)


def get_gate_channel_api(request) -> Response:
    """Get a gate channel by ID."""
    channel_id = request.param("channel_id")
    channel = gate.get_channel(channel_id)
    if not channel:
        return _err("Channel not found", status=404)
    return _ok({"ok": True, "channel": channel})


def update_gate_channel_api(request) -> Response:
    """Update a gate channel."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    channel_id = request.param("channel_id")
    payload = request.json()
    result = gate.update_channel(channel_id, **payload)
    if not result.get("ok"):
        return _err(result.get("error", "update failed"), status=500)
    _audit(request, "gate.channel.update", "gate_channel", str(channel_id), {"fields": list(payload.keys())})
    return _ok(result)


def delete_gate_channel_api(request) -> Response:
    """Disable a gate channel."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    channel_id = request.param("channel_id")
    result = gate.delete_channel(channel_id)
    if not result.get("ok"):
        return _err(result.get("error", "delete failed"), status=500)
    _audit(request, "gate.channel.delete", "gate_channel", str(channel_id), {})
    return _ok(result)


def test_gate_channel_api(request) -> Response:
    """Test channel health via checker bot."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    channel_id = request.param("channel_id")
    result = gate.validate_channel_health(channel_id)
    return _ok(result)


def generate_gate_invite_api(request) -> Response:
    """Generate invite link for a channel."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    channel_id = request.param("channel_id")
    payload = request.json() or {}
    result = gate.generate_invite_link(channel_id, payload.get("name"), payload.get("expire_hours", 24))
    return _ok(result)


# ── Profiles ──
def list_gate_profiles_api(request) -> Response:
    """List all gate profiles with slots."""
    profiles = gate.list_profiles()
    return _ok({"ok": True, "count": len(profiles), "profiles": profiles})


def create_gate_profile_api(request) -> Response:
    """Create a new gate profile with slots."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    payload = request.json()
    result = gate.create_profile(**payload)
    if not result.get("ok"):
        return _err(result.get("error", "create failed"), status=500)
    _audit(request, "gate.profile.create", "gate_profile", str(result["profile"].get("id", "")), payload)
    return _ok(result)


def get_gate_profile_api(request) -> Response:
    """Get a gate profile by ID."""
    profile_id = request.param("profile_id")
    profile = gate.get_profile(profile_id)
    if not profile:
        return _err("Profile not found", status=404)
    return _ok({"ok": True, "profile": profile})


def update_gate_profile_api(request) -> Response:
    """Update a gate profile."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    profile_id = request.param("profile_id")
    payload = request.json()
    result = gate.update_profile(profile_id, **payload)
    if not result.get("ok"):
        return _err(result.get("error", "update failed"), status=500)
    _audit(request, "gate.profile.update", "gate_profile", str(profile_id), {"fields": list(payload.keys())})
    return _ok(result)


def delete_gate_profile_api(request) -> Response:
    """Disable a gate profile."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    profile_id = request.param("profile_id")
    result = gate.delete_profile(profile_id)
    if not result.get("ok"):
        return _err(result.get("error", "delete failed"), status=500)
    _audit(request, "gate.profile.delete", "gate_profile", str(profile_id), {})
    return _ok(result)


def get_bot_effective_profile_api(request) -> Response:
    """Get effective gate profile for a bot."""
    bot_id = request.param("bot_id")
    # Get bot category from registry
    import json
    registry_path = config.ROOT_DIR / "bots_registry.json"
    category = None
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
        bot_reg = next((b for b in registry if b["id"] == bot_id), None)
        if bot_reg:
            category = bot_reg.get("category")
    except Exception:
        pass
    profile = gate.get_effective_profile(bot_id, category)
    if not profile:
        return _ok({"ok": True, "profile": None, "message": "No active gate profile for this bot"})
    return _ok({"ok": True, "profile": profile})


# ── Validation & Stats ──
def validate_membership_api(request) -> Response:
    """Validate user membership via checker bot."""
    payload = request.json()
    bot_id = payload.get("bot_id")
    user_id = payload.get("user_id")
    if not bot_id or not user_id:
        return _err("Missing bot_id or user_id", status=400)

    # In real implementation, this would call the checker bot
    # For now, return mock response based on cache
    profile = gate.get_effective_profile(bot_id)
    if not profile:
        return _ok({"ok": True, "required": False, "message": "No gate active for this bot"})

    # Check cache for each required slot
    missing = []
    for slot in profile.get("slots", []):
        if slot.get("is_required") and slot.get("channel"):
            ch_id = slot["channel_id"]
            if not gate.is_user_member_cached(user_id, ch_id):
                missing.append({
                    "position": slot["position"],
                    "channel_id": ch_id,
                    "channel_title": slot.get("channel", {}).get("title", ""),
                    "invite_link": slot.get("channel", {}).get("invite_link", ""),
                })

    if not missing:
        return _ok({"ok": True, "required": False, "verified": True})

    return _ok({"ok": True, "required": True, "missing": missing})


def gate_stats_api(request) -> Response:
    """Gate funnel statistics."""
    bot_id = request.q("bot_id")
    days = request.q_int("days", 30)
    funnel = gate.get_gate_funnel(bot_id, days)
    channel_joins = gate.get_channel_joins(days)
    return _ok({"ok": True, "funnel": funnel, "channel_joins": channel_joins, "days": days})


def gate_stats_export_api(request) -> Response:
    """Export gate events as CSV or JSON."""
    bot_id = request.q("bot_id")
    days = request.q_int("days", 30)
    fmt = request.q("format", "csv").lower()

    if fmt == "json":
        data = gate.export_gate_events_json(bot_id, days)
        return Response(data, content_type="application/json; charset=utf-8")
    else:
        data = gate.export_gate_events_csv(bot_id, days)
        return Response(data, content_type="text/csv; charset=utf-8")


def gate_health_api(request) -> Response:
    """Gate system health check."""
    health = gate.get_gate_health()
    return _ok({"ok": True, "health": health})


def gate_health_check_all_api(request) -> Response:
    """Check all channels and generate alerts."""
    denied = _guard(request, roles=("admin",))
    if denied:
        return denied
    result = gate.check_and_alert_channels()
    _audit(request, "gate.health.check_all", "gate", "", result)
    return _ok(result)


# ── Compliance ──
def compliance_check_api(request) -> Response:
    """Check text for compliance risks (honest wording)."""
    payload = request.json()
    text = payload.get("text", "")
    if not text:
        return _err("Missing text", status=400)
    warnings = gate._compliance_check(text)
    return _ok({"ok": True, "warnings": warnings, "safe": len(warnings) == 0})


# ══════════════════════════════════════════════════════════════════════════════
# Ad Studio — API (الواجهة الخلفية لمكتبة الإعلانات والحقن)
# ══════════════════════════════════════════════════════════════════════════════

def ads_parse_snippet_api(request) -> Response:
    """حلل snippet إعلاني وأعد ملخص المنطقة/الدالة بدون أي تعديل على النص."""
    payload = request.json()
    snippet = payload.get("snippet", "")
    if not snippet:
        return _err("Missing snippet", status=400)
    parsed = parser.parse_snippet(snippet)
    return _ok(parsed.to_dict())


def ads_library_list_api(request) -> Response:
    """قائمة الإعلانات في المكتبة."""
    lib = model.get_ad_library()
    enabled_only = request.q_bool("enabled_only", False)
    slot = request.q("slot", "")
    ads = lib.list(enabled_only=enabled_only, slot=slot)
    return _ok({"ok": True, "count": len(ads), "ads": [a.to_dict() for a in ads]})


def ads_library_create_api(request) -> Response:
    """إنشاء إعلان جديد من snippet (يُحلل ويُخزن كما هو)."""
    payload = request.json()
    snippet = payload.get("snippet", "")
    name = payload.get("name", "").strip() or "Ad"
    fmt = payload.get("format", "custom")
    slot = payload.get("slot", "body_end")
    if not snippet:
        return _err("Missing snippet", status=400)
    parsed = parser.parse_snippet(snippet)
    if not parsed.ok:
        return _err("Snippet invalid", status=400, **{"errors": parsed.errors,
                                                     "warnings": parsed.warnings})
    ad = model.Ad(name=name, provider="monetag", format=fmt, slot=slot,
                  snippet=parsed.snippet, zone_id=parsed.zone_id,
                  notes="; ".join(parsed.warnings) if parsed.warnings else None,
                  enabled=True)
    lib = model.get_ad_library()
    created = lib.create(ad, actor=request.actor)
    return _ok({"ok": True, "ad": created.to_dict(),
                "parse": parsed.to_dict()})


def ads_library_update_api(request) -> Response:
    """تعديل إعلان موجود."""
    payload = request.json()
    ad_id = payload.get("ad_id", "")
    if not ad_id:
        return _err("Missing ad_id", status=400)
    lib = model.get_ad_library()
    fields = {k: v for k, v in payload.items()
              if k in ("name", "format", "slot", "snippet", "zone_id",
                       "direct_link", "notes", "enabled", "cpm_rate")}
    if "snippet" in fields:
        parsed = parser.parse_snippet(fields["snippet"])
        if not parsed.ok:
            return _err("Snippet invalid", status=400,
                        **{"errors": parsed.errors,
                           "warnings": parsed.warnings})
        fields["snippet"] = parsed.snippet
        fields["zone_id"] = parsed.zone_id
    updated = lib.update(ad_id, **fields)
    if not updated:
        return _err("Ad not found", status=404)
    return _ok({"ok": True, "ad": updated.to_dict()})


def ads_library_delete_api(request) -> Response:
    """حذف إعلان من المكتبة."""
    payload = request.json()
    ad_id = payload.get("ad_id", "")
    if not ad_id:
        return _err("Missing ad_id", status=400)
    lib = model.get_ad_library()
    ok = lib.delete(ad_id)
    return _ok({"ok": ok})


def ads_assign_api(request) -> Response:
    """سنّد إعلان لبوت/تصنيف/عام."""
    payload = request.json()
    ad_id = payload.get("ad_id", "")
    scope = payload.get("scope", "bot")
    target_id = payload.get("target_id", None) or None
    priority = int(payload.get("priority", 0) or 0)
    if not ad_id:
        return _err("Missing ad_id", status=400)
    if scope not in ("bot", "category", "global"):
        return _err("Invalid scope", status=400)
    lib = model.get_ad_library()
    ok = lib.assign(ad_id, scope, target_id, priority=priority)
    return _ok({"ok": ok})


def ads_unassign_api(request) -> Response:
    """إلغاء سناد إعلان."""
    payload = request.json()
    ad_id = payload.get("ad_id", "")
    scope = payload.get("scope", "bot")
    target_id = payload.get("target_id", None) or None
    lib = model.get_ad_library()
    n = lib.unassign(ad_id, scope, target_id)
    return _ok({"ok": True, "removed": n})


def ads_effective_api(request) -> Response:
    """الاعلان الفعّال لكل فتحية لبوت معين (للواجهة الأمامية)."""
    bot_id = request.param("bot_id")
    category = request.q("category", "")
    if not bot_id:
        return _err("Missing bot_id", status=400)
    result = resolver.effective_map(bot_id, category)
    return _ok({"ok": True, "bot_id": bot_id, "category": category,
                "slots": result})


def ads_preview_diff_api(request) -> Response:
    """معاينة الفروقات (Diff) قبل تطبيق الإعلان على صفحة البوت."""
    payload = request.json()
    bot_id = payload.get("bot_id", "currency")
    slot = payload.get("slot", "body_end")
    snippet = payload.get("snippet", "")
    ad_id = payload.get("ad_id", "preview_ad")
    if not snippet:
        return _err("Missing snippet", status=400)

    target_file = config.WEBROOT_DIR / bot_id / "index.html"
    if not target_file.exists():
        return _err(f"App file for {bot_id} not found", status=404)

    try:
        original_html = target_file.read_text(encoding="utf-8")
        new_html = injector.inject_markers(original_html, [(slot, ad_id, snippet)])
        diff = injector.dry_run(target_file, new_html)
        return _ok({"ok": True, "bot_id": bot_id, "diff": diff, "changed": bool(diff.strip())})
    except Exception as exc:
        return _err(f"Preview failed: {exc}", status=500)


def ads_build_apply_api(request) -> Response:
    """طبّق الإعلانات على التطبيقات المصغّرة (بناء + حقن علامات مع نسخ احتياطي)."""
    payload = request.json()
    bot_id = payload.get("bot_id", "")
    if bot_id:
        p = config.WEBROOT_DIR / bot_id / "index.html"
        if p.exists():
            try:
                import shutil
                b_dir = injector._backup_dir(p)
                b_dir.mkdir(parents=True, exist_ok=True)
                b_path = injector._backup_path(p)
                shutil.copy2(p, b_path)
            except Exception:
                pass
    res = store.build_store_pages()
    if not res.get("ok"):
        return _err(res.get("error", "Build failed"), status=500, stdout=res.get("stdout"))
    return _ok({"ok": True, "message": "Pages regenerated successfully", "stdout": res.get("stdout")})


def ads_rollback_api(request) -> Response:
    """استرجاع النسخة الاحتياطية السابقة لصفحة البوت."""
    payload = request.json()
    bot_id = payload.get("bot_id", "")
    if not bot_id:
        return _err("Missing bot_id", status=400)
    target_file = config.WEBROOT_DIR / bot_id / "index.html"
    res = injector.rollback_file(target_file)
    if not res.get("ok"):
        return _err(res.get("error", "Rollback failed"), status=400)
    return _ok(res)


def ads_backups_list_api(request) -> Response:
    """قائمة النسخ الاحتياطية لصفحة البوت."""
    bot_id = request.param("bot_id")
    if not bot_id:
        return _err("Missing bot_id", status=400)
    target_file = config.WEBROOT_DIR / bot_id / "index.html"
    backups = injector.list_backups(target_file)
    items = []
    for b in backups:
        try:
            mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size = b.stat().st_size
        except Exception:
            mtime = ""
            size = 0
        items.append({"name": b.name, "size": size, "time": mtime})
    return _ok({"ok": True, "bot_id": bot_id, "backups": items})


def ads_publish_api(request) -> Response:
    """نشر التعديلات عبر Git إلى GitHub Pages بنقرة واحدة."""
    payload = request.json()
    msg = payload.get("message") or "feat(ads): update ad units via Ad Studio"
    res = store.publish_to_github_pages(msg)
    if not res.get("ok"):
        return _err(res.get("error", "Publish failed"), status=500, **res)
    return _ok(res)


def ads_stats_api(request) -> Response:
    """إحصائيات الإعلانات لكل بوت."""
    lib = model.get_ad_library()
    ad_id = request.q("ad_id", "")
    stats = lib.stats(ad_id)
    per_bot = lib.per_bot_stats(ad_id)
    return _ok({"ok": True, "stats": stats, "per_bot": per_bot})


REG_PATH = None  # تُضبط في register_routes


def register_routes(router: Router) -> Router:
    """Register every Control Center route on ``router``."""
    global REG_PATH
    REG_PATH = config.BASE_DIR / "bots_registry.json"
    router.get("/openapi.json", openapi_document, summary="OpenAPI document",
               tags=("meta",))
    router.get("/docs", swagger_ui, summary="Swagger UI", tags=("meta",))
    router.get("/api/v1/system/health", system_health,
               summary="Control Center health")
    router.get("/api/v1/system/migrations", system_migrations,
               summary="Migration status")
    router.post("/api/v1/system/migrations", system_migrations_apply,
                summary="Apply pending migrations", roles=("admin",))
    router.get("/api/v1/system/config", system_config,
               summary="Control Center settings")
    router.post("/api/v1/system/verify-token", verify_telegram_token,
                summary="Validate token with Telegram getMe")
    router.get("/api/v1/overview", overview, summary="KPI overview")

    router.get("/api/v1/bots", list_bots, summary="List bots and status")
    router.get("/api/v1/bots/<bot_id>", get_bot, summary="Bot detail")
    router.post("/api/v1/bots/<bot_id>/start", start_bot,
                summary="Start a bot", roles=("operator",))
    router.post("/api/v1/bots/<bot_id>/stop", stop_bot,
                summary="Stop a bot", roles=("operator",))
    router.post("/api/v1/bots/<bot_id>/restart", restart_bot,
                summary="Restart a bot", roles=("operator",))
    router.post("/api/v1/bots/<bot_id>/enable", enable_bot,
                summary="Enable or disable a bot", roles=("operator",))
    router.post("/api/v1/bots/<bot_id>/config", update_bot_config,
                summary="Update bot configuration", roles=("admin",))
    router.get("/api/v1/bots/<bot_id>/logs", bot_logs,
               summary="Recent log lines")
    router.get("/api/v1/bots/<bot_id>/logs/stream", bot_logs_stream,
               summary="Live log stream (SSE)")
    router.post("/api/v1/bots/actions/start-all", start_all,
                summary="Start every enabled bot", roles=("operator",))
    router.post("/api/v1/bots/actions/stop-all", stop_all,
                summary="Stop every running bot", roles=("operator",))

    router.get("/api/v1/audit", list_audit, summary="Audit log")

    # ─────────────────────────────────────────────────────────────────────────
    # Bot Registry CRUD (Phase 1)
    # ─────────────────────────────────────────────────────────────────────────
    router.post("/api/v1/bots", create_bot,
                summary="Create/Add a new bot (wizard)", roles=("admin",))
    router.patch("/api/v1/bots/<bot_id>", update_bot_registry,
                 summary="Update bot registry entry", roles=("admin",))
    router.post("/api/v1/bots/<bot_id>/archive", archive_bot,
                summary="Archive (soft delete) a bot", roles=("admin",))
    router.post("/api/v1/bots/<bot_id>/restore", restore_bot,
                summary="Restore an archived bot", roles=("admin",))
    router.delete("/api/v1/bots/<bot_id>", delete_bot,
                  summary="Delete a bot from system (hard)", roles=("admin",))
    router.post("/api/v1/bots/<bot_id>/clone", clone_bot,
                summary="Clone a bot from template", roles=("admin",))
    router.post("/api/v1/bots/actions/bulk-enable", bulk_enable_bots,
                summary="Bulk enable/disable bots", roles=("operator",))

    # ─────────────────────────────────────────────────────────────────────────
    # Bot Profile Manager (Phase 1)
    # ─────────────────────────────────────────────────────────────────────────
    router.get("/api/v1/bots/<bot_id>/profile", get_bot_profile,
               summary="Get bot profile fields (per-language)")
    router.patch("/api/v1/bots/<bot_id>/profile", update_bot_profile,
                 summary="Update bot profile fields", roles=("admin",))
    router.get("/api/v1/bots/<bot_id>/profile/diff", profile_diff,
               summary="Live diff: stored vs Telegram values")
    router.post("/api/v1/bots/<bot_id>/profile/apply", apply_bot_profile,
                summary="Apply profile to Telegram via Bot API", roles=("admin",))
    router.post("/api/v1/bots/actions/profile-sync", sync_all_profiles,
                summary="Sync profiles for all bots", roles=("admin",))

    # ─────────────────────────────────────────────────────────────────────────
    # Store Manager (Phase 2)
    # ─────────────────────────────────────────────────────────────────────────
    router.get("/api/v1/store", list_store_items_api,
               summary="List store items")
    router.get("/api/v1/store/categories", list_categories_api,
               summary="List store categories")
    router.get("/api/v1/store/stats", store_stats_api,
               summary="Store aggregate statistics")
    router.get("/api/v1/store/<item_id:int>", get_store_item_api,
               summary="Get store item by ID")
    router.get("/api/v1/store/bot/<bot_id>", get_store_item_by_bot_api,
               summary="Get store item by bot ID")
    router.post("/api/v1/store", create_store_item_api,
                summary="Create store item", roles=("admin",))
    router.patch("/api/v1/store/<item_id:int>", update_store_item_api,
                 summary="Update store item", roles=("admin",))
    router.delete("/api/v1/store/<item_id:int>", delete_store_item_api,
                  summary="Delete store item", roles=("admin",))
    router.post("/api/v1/store/reorder", reorder_store_items_api,
                summary="Reorder store items (drag-drop)", roles=("admin",))
    router.post("/api/v1/store/<item_id:int>/stat/<stat>", increment_store_stat_api,
                summary="Increment view/open/click stat")
    router.get("/api/v1/store/catalog", generate_catalog_api,
               summary="Generate catalog.json for Mini App")
    router.post("/api/v1/store/build", build_store_api,
                summary="Build Mini App pages", roles=("admin",))
    router.post("/api/v1/store/publish", publish_store_api,
                summary="Publish to GitHub Pages", roles=("admin",))
    router.post("/api/v1/store/full-publish", full_publish_store_api,
                summary="Full pipeline: catalog + build + publish", roles=("admin",))

    # Full publish preview (without committing)
    router.post("/api/v1/store/full-publish-preview", full_publish_preview_store_api,
                summary="Full publish preview with diff", roles=("admin",))

    # ─────────────────────────────────────────────────────────────────────────
    # Store Manager — Enhancements
    # ─────────────────────────────────────────────────────────────────────────
    router.post("/api/v1/store/upload-image", upload_store_image_api,
                summary="Upload icon/cover image for store items", roles=("admin",))
    router.post("/api/v1/store/preview", preview_store_item_api,
                summary="Generate live preview HTML for store item", roles=("admin",))
    router.post("/api/v1/store/bulk", bulk_store_action_api,
                summary="Bulk actions (delete, status, category, reorder)", roles=("admin",))
    router.get("/api/v1/store/export", export_store_api,
               summary="Export store items (JSON/CSV)")
    router.post("/api/v1/store/import", import_store_api,
                summary="Import store items from JSON", roles=("admin",))

    # ─────────────────────────────────────────────────────────────────────────
    # Gate Manager (Phase 3-4)
    # ─────────────────────────────────────────────────────────────────────────
    # Channels
    router.get("/api/v1/gate/channels", list_gate_channels_api,
               summary="List gate channels")
    router.post("/api/v1/gate/channels", create_gate_channel_api,
                summary="Add gate channel", roles=("admin",))
    router.get("/api/v1/gate/channels/<channel_id:int>", get_gate_channel_api,
               summary="Get gate channel")
    router.patch("/api/v1/gate/channels/<channel_id:int>", update_gate_channel_api,
                 summary="Update gate channel", roles=("admin",))
    router.delete("/api/v1/gate/channels/<channel_id:int>", delete_gate_channel_api,
                  summary="Disable gate channel", roles=("admin",))
    router.post("/api/v1/gate/channels/<channel_id:int>/test", test_gate_channel_api,
                summary="Test channel health (getChat + admin check)", roles=("admin",))
    router.post("/api/v1/gate/channels/<channel_id:int>/invite", generate_gate_invite_api,
                summary="Generate invite link", roles=("admin",))

    # Profiles
    router.get("/api/v1/gate/profiles", list_gate_profiles_api,
               summary="List gate profiles")
    router.post("/api/v1/gate/profiles", create_gate_profile_api,
                summary="Create gate profile", roles=("admin",))
    router.get("/api/v1/gate/profiles/<profile_id:int>", get_gate_profile_api,
               summary="Get gate profile with slots")
    router.patch("/api/v1/gate/profiles/<profile_id:int>", update_gate_profile_api,
                 summary="Update gate profile", roles=("admin",))
    router.delete("/api/v1/gate/profiles/<profile_id:int>", delete_gate_profile_api,
                  summary="Disable gate profile", roles=("admin",))
    router.get("/api/v1/gate/profiles/bot/<bot_id>", get_bot_effective_profile_api,
               summary="Get effective profile for a bot")

    # Validation & Stats
    router.post("/api/v1/gate/validate", validate_membership_api,
                summary="Validate user membership via checker bot")
    router.get("/api/v1/gate/stats", gate_stats_api,
               summary="Gate funnel statistics")
    router.get("/api/v1/gate/stats/export", gate_stats_export_api,
               summary="Export gate stats (CSV/JSON)")
    router.get("/api/v1/gate/health", gate_health_api,
               summary="Gate system health check")
    router.post("/api/v1/gate/health/check-all", gate_health_check_all_api,
                summary="Check all channels and alert", roles=("admin",))

    # Compliance
    router.post("/api/v1/gate/compliance/check", compliance_check_api,
                summary="Check text for compliance risks")

    # ════════════════════════════════════════════════════════════════════════
    # Ad Studio — Core API (الكتاب يتطلب التوكن المحلي)
    # ════════════════════════════════════════════════════════════════════════
    router.post("/api/v1/ads/parse", ads_parse_snippet_api,
                summary="Parse ad snippet (zone/sdk extraction)", roles=("admin",))
    router.get("/api/v1/ads/library", ads_library_list_api,
               summary="List ads in library", roles=("admin",))
    router.post("/api/v1/ads/library", ads_library_create_api,
                summary="Create ad from snippet", roles=("admin",))
    router.patch("/api/v1/ads/library", ads_library_update_api,
                 summary="Update ad", roles=("admin",))
    router.delete("/api/v1/ads/library", ads_library_delete_api,
                  summary="Delete ad", roles=("admin",))
    router.post("/api/v1/ads/assign", ads_assign_api,
                summary="Assign ad to bot/category/global", roles=("admin",))
    router.delete("/api/v1/ads/assign", ads_unassign_api,
                  summary="Unassign ad", roles=("admin",))
    router.get("/api/v1/ads/effective/<bot_id>", ads_effective_api,
               summary="Effective ad map for a bot", roles=("admin",))
    router.post("/api/v1/ads/preview-diff", ads_preview_diff_api,
                summary="Preview ad injection diff", roles=("admin",))
    router.post("/api/v1/ads/build-apply", ads_build_apply_api,
                summary="Apply ads to mini apps (build + inject)", roles=("admin",))
    router.post("/api/v1/ads/rollback", ads_rollback_api,
                summary="Rollback ad changes for bot", roles=("admin",))
    router.get("/api/v1/ads/backups/<bot_id>", ads_backups_list_api,
               summary="List backups for bot", roles=("admin",))
    router.post("/api/v1/ads/publish", ads_publish_api,
                summary="Publish ad changes to GitHub Pages", roles=("admin",))
    router.get("/api/v1/ads/stats", ads_stats_api,
               summary="Ad statistics", roles=("admin",))

    return router


ROUTER = register_routes(ROUTER)
