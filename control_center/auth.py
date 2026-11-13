"""
control_center/auth.py — request authorisation (role layer).

Security model (Phase 1 hardening):

* READ requests from loopback are trusted (dashboard convenience).
* **State-changing requests** (POST/PUT/PATCH/DELETE) are gated at the HTTP
  layer — ``api_server.py`` requires the local admin token for loopback
  callers and the legacy ``X-API-Key`` for remote callers
  (see :func:`control_center.config.ensure_local_admin_token`).
* This module stays the per-route role layer: roles map to ``admin`` /
  ``operator`` / ``viewer`` and are checked here. Phase 5 will add real
  sessions without changing any route signature — every handler already
  goes through :func:`authorize`.

Role names used across the Control Center:

``admin``    full access, including users, settings and destructive actions
``operator`` may run bots, manage ads and read statistics
``viewer``   read-only
"""

import hmac

from . import config

ROLES = ("admin", "operator", "viewer")
ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


def client_ip(request) -> str:
    try:
        return request.handler.client_address[0]
    except Exception:
        return ""


def is_local(request) -> bool:
    """True when the request originates from the machine itself."""
    return client_ip(request) in ("127.0.0.1", "::1", "localhost")


def provided_key(request) -> str:
    """The credential the client presented: ``X-API-Key`` or a Bearer token."""
    key = request.header("X-API-Key", "").strip()
    if not key:
        auth = request.header("Authorization", "").strip()
        if auth.lower().startswith("bearer "):
            key = auth[7:].strip()
    return key


def legacy_key_ok(request) -> bool:
    """True when the shared ``X-API-Key`` header matches the configured key."""
    key = config.api_server_key()
    if not key:
        return False
    provided = provided_key(request)
    return bool(provided) and hmac.compare_digest(provided, key)


def session_user(request):
    """Resolve the session user of a request (Phase 5 fills this in)."""
    return getattr(request, "user", None)


def authorize(request, roles=None) -> tuple:
    """
    Authorise a request.

    Returns ``(allowed, payload)``. When not allowed, ``payload`` is a dict
    with an ``error`` key and the HTTP status to answer with.

    Local (loopback) requests may READ freely; state-changing requests must
    carry the local admin token whenever one is established
    (:func:`config.ensure_local_admin_token` runs at server startup).
    """
    required = tuple(roles or ())

    user = session_user(request)
    if user:
        role = str(user.get("role", "viewer")).lower()
        if required and ROLE_RANK.get(role, 0) < max(
                ROLE_RANK.get(r, 0) for r in required):
            return False, {"error": "insufficient role", "status": 403,
                           "required": list(required), "role": role}
        request.actor = str(user.get("username", role))
        return True, {}

    if is_local(request):
        # Local (loopback) requests are trusted for role purposes here.
        # State-changing requests are additionally gated at the HTTP layer
        # (api_server.py) which requires the local admin token — see
        # BodaAPIHandler._is_authorized / _dispatch_control_center.
        request.actor = "local"
        return True, {}

    if legacy_key_ok(request):
        request.actor = "api-key"
        return True, {}

    return False, {"error": "Forbidden — أدخل X-API-Key صحيحاً", "status": 403}
