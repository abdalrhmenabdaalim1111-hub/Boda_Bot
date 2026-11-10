"""
control_center/auth.py — request authorisation.

Phase 1 keeps the **existing** security model of the project: requests from
localhost are trusted, remote requests must carry the shared ``X-API-Key``
header. Phase 5 replaces this module with JWT sessions and role checks
without changing any route signature — every handler already goes through
:func:`authorize`.

Role names used across the Control Center:

``admin``    full access, including users, settings and destructive actions
``operator`` may run bots, manage ads and read statistics
``viewer``   read-only
"""

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


def legacy_key_ok(request) -> bool:
    """True when the shared ``X-API-Key`` header matches the configured key."""
    key = config.api_server_key()
    if not key:
        return False
    provided = request.header("X-API-Key", "").strip()
    return bool(provided) and provided == key


def session_user(request):
    """Resolve the session user of a request (Phase 5 fills this in)."""
    return getattr(request, "user", None)


def authorize(request, roles=None) -> tuple:
    """
    Authorise a request.

    Returns ``(allowed, payload)``. When not allowed, ``payload`` is a dict
    with an ``error`` key and the HTTP status to answer with.
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
        request.actor = "local"
        return True, {}

    if legacy_key_ok(request):
        request.actor = "api-key"
        return True, {}

    return False, {"error": "Forbidden — أدخل X-API-Key صحيحاً", "status": 403}
