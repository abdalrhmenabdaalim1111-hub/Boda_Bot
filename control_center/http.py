"""
control_center/http.py — a tiny HTTP router, OpenAPI generator and SSE helper.

The Control Center deliberately does **not** introduce a web framework
(decision D2). This module provides just enough structure to register
routes on top of the standard library ``http.server``:

* :class:`Router` — method + path-pattern matching with ``<param>`` segments
* :class:`Request` / :class:`Response` — thin wrappers around the raw handler
* :meth:`Router.openapi` — an OpenAPI 3.1 document generated from the route
  metadata, served at ``/openapi.json`` with a Swagger UI at ``/docs``
* :func:`sse` — Server-Sent Events framing for live log streaming
"""

import json
import re
import time
from urllib.parse import parse_qs

JSON_CONTENT_TYPE = "application/json; charset=utf-8"


class Response:
    """A prepared HTTP response."""

    def __init__(self, body=None, status: int = 200,
                 content_type: str = JSON_CONTENT_TYPE,
                 headers: dict | None = None):
        self.status = status
        self.content_type = content_type
        self.headers = headers or {}
        self.body = body
        # Set to True by handlers that already wrote the response themselves
        # (Server-Sent Events) — the dispatcher then sends nothing.
        self.sent = False

    def payload(self) -> bytes:
        """Serialise the body to bytes."""
        if self.body is None:
            return b""
        if isinstance(self.body, bytes):
            return self.body
        if isinstance(self.body, str):
            return self.body.encode("utf-8")
        return json.dumps(self.body, ensure_ascii=False, default=str).encode("utf-8")


class Request:
    """A parsed incoming request."""

    def __init__(self, handler, method: str, path: str,
                 query: dict | None = None, body: bytes = b"",
                 params: dict | None = None):
        self.handler = handler
        self.method = method
        self.path = path
        self.query = query or {}
        self.body = body or b""
        self.params = params or {}
        self.user = None          # filled by the auth layer
        self.actor = "anonymous"

    # ── Accessors ──────────────────────────────────────────────────────────
    def header(self, name: str, default: str = "") -> str:
        value = self.handler.headers.get(name) if self.handler else None
        return value if value is not None else default

    def q(self, name: str, default: str = "") -> str:
        """First value of a query-string parameter."""
        values = self.query.get(name)
        if not values:
            return default
        return values[0]

    def q_int(self, name: str, default: int = 0) -> int:
        try:
            return int(self.q(name, str(default)))
        except (TypeError, ValueError):
            return default

    def q_bool(self, name: str, default: bool = False) -> bool:
        raw = self.q(name, "").strip().lower()
        if not raw:
            return default
        return raw in ("1", "true", "yes", "on")

    def json(self) -> dict:
        """Parse the request body as JSON; returns ``{}`` on any problem."""
        if not self.body:
            return {}
        try:
            data = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {"_raw": data}

    def client_ip(self) -> str:
        try:
            return self.handler.client_address[0]
        except Exception:
            return ""

    def param(self, name: str, default: str = "") -> str:
        return self.params.get(name, default)


class Route:
    """A registered route."""

    def __init__(self, method: str, pattern: str, handler, summary: str = "",
                 auth: bool = False, roles=None, tags=None, params=None):
        self.method = method.upper()
        self.pattern = pattern
        self.handler = handler
        self.summary = summary
        self.auth = auth
        self.roles = tuple(roles or ())
        self.tags = list(tags or ("control-center",))
        self.params = list(params or self._extract_params(pattern))
        self.regex = self._compile(pattern)

    @staticmethod
    def _extract_params(pattern: str) -> list:
        return re.findall(r"<([a-zA-Z_][a-zA-Z0-9_]*)>", pattern)

    @staticmethod
    def _compile(pattern: str):
        escaped = re.escape(pattern)
        # re.escape escapes '<' and '>' in Python 3.7+, so restore them.
        escaped = escaped.replace(r"\<", "<").replace(r"\>", ">")
        pattern_re = re.sub(r"<([a-zA-Z_][a-zA-Z0-9_]*)>", r"(?P<\1>[^/]+)", escaped)
        return re.compile(f"^{pattern_re}$")


class Router:
    """Registry of routes with path-parameter matching."""

    def __init__(self):
        self._routes: list = []

    def add(self, method: str, pattern: str, handler, summary: str = "",
            auth: bool = False, roles=None, tags=None) -> Route:
        """Register a route and return it."""
        route = Route(method, pattern, handler, summary=summary, auth=auth,
                      roles=roles, tags=tags)
        self._routes.append(route)
        return route

    def get(self, pattern, handler, **kwargs):
        return self.add("GET", pattern, handler, **kwargs)

    def post(self, pattern, handler, **kwargs):
        return self.add("POST", pattern, handler, **kwargs)

    def put(self, pattern, handler, **kwargs):
        return self.add("PUT", pattern, handler, **kwargs)

    def patch(self, pattern, handler, **kwargs):
        return self.add("PATCH", pattern, handler, **kwargs)

    def delete(self, pattern, handler, **kwargs):
        return self.add("DELETE", pattern, handler, **kwargs)

    def routes(self) -> list:
        return list(self._routes)

    def match(self, method: str, path: str):
        """
        Find the route handling ``method``/``path``.

        Returns ``(route, params)`` or ``(None, None)``. A path that exists
        under another method yields ``(None, {"_method_mismatch": True})``
        so the caller can answer 405 instead of 404.
        """
        method = method.upper()
        path_matched = False
        for route in self._routes:
            found = route.regex.match(path)
            if not found:
                continue
            path_matched = True
            if route.method == method:
                return route, found.groupdict()
        if path_matched:
            return None, {"_method_mismatch": True}
        return None, None

    def openapi(self, info: dict | None = None) -> dict:
        """Build an OpenAPI 3.1 document from the registered routes."""
        paths: dict = {}
        for route in self._routes:
            # OpenAPI uses {name} for path parameters, the router uses <name>.
            oa_path = re.sub(r"<([a-zA-Z_][a-zA-Z0-9_]*)>", r"{\1}", route.pattern)
            entry = paths.setdefault(oa_path, {})
            parameters = []
            for name in route.params:
                parameters.append({
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                })
            operation = {
                "summary": route.summary or route.handler.__name__,
                "operationId": route.handler.__name__,
                "tags": route.tags,
                "responses": {"200": {"description": "Successful response"}},
            }
            if route.method in ("POST", "PUT", "PATCH"):
                operation["requestBody"] = {
                    "required": False,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                }
            if parameters:
                operation["parameters"] = parameters
            if route.auth:
                operation["security"] = [{"bearerAuth": []}]
            entry[route.method.lower()] = operation

        return {
            "openapi": "3.1.0",
            "info": info or {
                "title": "Boda Bot Control Center API",
                "version": "1.0.0",
                "description": "Control plane for the Boda Bot ecosystem.",
            },
            "servers": [{"url": "/"}],
            "components": {
                "securitySchemes": {
                    "bearerAuth": {"type": "http", "scheme": "bearer"},
                    "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
                }
            },
            "paths": paths,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Server-Sent Events
# ─────────────────────────────────────────────────────────────────────────────
def sse(event: str = "message", data=None, event_id: str = "") -> bytes:
    """Frame one Server-Sent Event."""
    chunks = []
    if event_id:
        chunks.append(f"id: {event_id}\n")
    if event:
        chunks.append(f"event: {event}\n")
    payload = data
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False, default=str)
    for line in payload.split("\n"):
        chunks.append(f"data: {line}\n")
    chunks.append("\n")
    return "".join(chunks).encode("utf-8")


def sse_ping() -> bytes:
    """A comment frame used as a keep-alive."""
    return b": ping\n\n"


class SSESession:
    """
    Helper to stream events from a handler.

    Usage inside a route handler::

        sess = SSESession(self)
        sess.start()
        sess.send("log", {"line": "hello"})
        sess.stop()
    """

    def __init__(self, handler, keepalive: float = 15.0):
        self.handler = handler
        self.keepalive = keepalive
        self._closed = False

    def start(self):
        self.handler.send_response(200)
        self.handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.handler.send_header("Cache-Control", "no-cache, no-store")
        self.handler.send_header("X-Accel-Buffering", "no")
        self.handler.send_header("Connection", "close")
        self.handler.end_headers()
        self.handler.wfile.flush()

    def send(self, event: str = "message", data=None, event_id: str = "") -> bool:
        """Write one event. Returns False when the client disconnected."""
        if self._closed:
            return False
        try:
            self.handler.wfile.write(sse(event, data, event_id))
            self.handler.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._closed = True
            return False

    def ping(self) -> bool:
        return self.send_raw(sse_ping())

    def send_raw(self, payload: bytes) -> bool:
        if self._closed:
            return False
        try:
            self.handler.wfile.write(payload)
            self.handler.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._closed = True
            return False

    def stop(self):
        self._closed = True


def parse_query(query_string: str) -> dict:
    """Parse a raw query string into a dict of lists."""
    return parse_qs(query_string or "")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
