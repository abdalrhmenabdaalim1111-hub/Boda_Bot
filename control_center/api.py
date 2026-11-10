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

import time
from datetime import datetime

from . import audit, botconfig, config, crypto, db, migrations
from .auth import authorize
from .http import Response, Router, SSESession

ROUTER = Router()

_supervisor = None


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
    """Recent log lines of a bot."""
    bot_id = request.param("bot_id")
    limit = request.q_int("limit", 200)
    level = request.q("level", "")
    lines = get_supervisor().logs(bot_id, limit=limit, level=level)
    return _ok({"ok": True, "bot_id": bot_id, "count": len(lines),
                "lines": lines})


def bot_logs_stream(request) -> Response:
    """Live log stream (Server-Sent Events)."""
    bot_id = request.param("bot_id")
    supervisor = get_supervisor()
    session = SSESession(request.handler)
    session.start()
    pending = []
    lock = __import__("threading").Lock()

    def _on_line(entry):
        with lock:
            pending.append(entry)

    supervisor.subscribe(bot_id, _on_line)
    try:
        for entry in supervisor.logs(bot_id, limit=100):
            session.send("log", entry)
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


def swagger_ui(request) -> Response:
    """Swagger UI for the OpenAPI document."""
    return Response(_SWAGGER_HTML, content_type="text/html; charset=utf-8")


def register_routes(router: Router) -> Router:
    """Register every Control Center route on ``router``."""
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
    return router


ROUTER = register_routes(ROUTER)
