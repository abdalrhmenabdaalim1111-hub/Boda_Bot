# =============================================================================
#  Bots_Folder/webhook_server.py — خادم Webhook حقيقي متعدد البوتات (v1.0)
#
#  المشكلة التي يحلها:
#      النسخة السابقة كانت تسجّل رابط Webhook لدى تيليجرام فقط دون تشغيل
#      خادم HTTP يستقبل التحديثات — أي أن البوت يتوقف فعلياً عن العمل.
#
#  المزايا:
#      • خادم HTTP واحد يخدم كل البوتات (توفير موارد كبير مقابل Polling)
#      • توجيه كل تحديث للبوت الصحيح عبر المسار /webhook/<secret>/<bot_id>
#      • حماية عبر X-Telegram-Bot-Api-Secret-Token (secret_token)
#      • /health جاهز لمراقبات UptimeRobot وغيرها
#      • ThreadingHTTPServer لمعالجة متزامنة دون حجب
# =============================================================================
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

logger = logging.getLogger("WebhookServer")

BASE_DIR = Path(__file__).parent.parent.resolve()
WEBROOT_DIR = BASE_DIR / "webroot"
WEBAPPS_DIR = BASE_DIR / "webapps"

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def webhook_path_for(bot_name: str, secret: str = "") -> str:
    """مسار Webhook القياسي — يُستخدم أيضاً دون إنشاء خادم (وضع serve=False)."""
    clean = str(bot_name).replace("bot_", "").strip().lower()
    if secret:
        return f"/webhook/{secret}/{clean}"
    return f"/webhook/{clean}"


class WebhookServer:
    """خادم Webhook واحد يستضيف عدة بوتات ويوزّع التحديثات عليها."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8443,
                 secret: str = ""):
        self.host = host
        self.port = int(port)
        self.secret = (secret or "").strip()
        self._bots: dict = {}
        self._lock = threading.Lock()
        self._thread = None

        self._httpd = ThreadingHTTPServer(
            (self.host, self.port), self._make_handler())
        self._httpd.daemon_threads = True

    # ── إدارة البوتات ────────────────────────────────────────────────────────
    def register(self, bot_name: str, bot) -> "WebhookServer":
        """تسجيل بوت لاستقبال تحديثاته عبر هذا الخادم."""
        with self._lock:
            self._bots[str(bot_name).replace("bot_", "")] = bot
        return self

    def unregister(self, bot_name: str) -> None:
        with self._lock:
            self._bots.pop(str(bot_name).replace("bot_", ""), None)

    @property
    def registered_count(self) -> int:
        with self._lock:
            return len(self._bots)

    def bot_names(self) -> list:
        with self._lock:
            return sorted(self._bots)

    @property
    def actual_port(self) -> int:
        """المنفذ الفعلي (مفيد عند استخدام port=0 في الاختبارات)."""
        return int(self._httpd.server_address[1])

    # ── بناء المسارات والروابط ───────────────────────────────────────────────
    def webhook_path(self, bot_name: str) -> str:
        """مسار Webhook الخاص بالبوت — يتضمن السر إن وُجد."""
        return webhook_path_for(bot_name, self.secret)

    def public_url(self, base_url: str, bot_name: str) -> str:
        """الرابط العام الكامل الذي يُسجَّل لدى تيليجرام."""
        return f"{base_url.rstrip('/')}{self.webhook_path(bot_name)}"

    def _resolve_bot(self, path: str):
        """استخراج اسم البوت من نهاية المسار وإرجاع كائن البوت."""
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2 or parts[0] != "webhook":
            return None
        bot_name = parts[-1].strip().lower()
        with self._lock:
            return self._bots.get(bot_name)

    # ── التشغيل والإيقاف ─────────────────────────────────────────────────────
    def start(self) -> "WebhookServer":
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="BodaWebhookHTTP",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"🌐 Webhook server listening on {self.host}:{self.actual_port} "
            f"({self.registered_count} bots, secret={'yes' if self.secret else 'no'})")
        return self

    def stop(self) -> None:
        # shutdown() يحجب إذا لم يبدأ serve_forever — نتحقق أولاً
        if self._thread is not None and self._thread.is_alive():
            try:
                self._httpd.shutdown()
            except Exception:
                pass
        try:
            self._httpd.server_close()
        except Exception:
            pass
        logger.info("⏹ Webhook server stopped")

    # ── معالج HTTP ───────────────────────────────────────────────────────────
    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            # منع طباعة كل طلب في الطرفية
            def log_message(self, fmt, *args):
                pass

            def _json(self, code: int, payload: dict):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _send_bytes(self, code: int, body: bytes, content_type: str = "text/html; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path.rstrip("/")
                if path in ("", "/health"):
                    self._json(200, {
                        "status": "ok",
                        "mode": "webhook",
                        "bots": server.registered_count,
                        "timestamp": datetime.now().isoformat(),
                    })
                elif path == "/":
                    self._json(200, {
                        "service": "Boda Webhook Server",
                        "endpoints": ["/health", "GET /apps/<bot_id>", "GET /api/ads/status",
                                      "POST /api/ads/set", "POST /webhook/<bot_id>"],
                        "bots": server.bot_names(),
                    })
                elif path == "/api/ads/status":
                    try:
                        from ad_manager import get_ad_manager
                        statuses = get_ad_manager().get_all_monetag_statuses()
                        self._json(200, {"ok": True, "count": len(statuses), "apps": statuses})
                    except Exception as e:
                        self._json(500, {"error": str(e)})
                elif path.startswith("/apps"):
                    parts = [p for p in path.split("/") if p and p != "apps"]
                    target_file = None
                    c_type = "text/html; charset=utf-8"

                    if not parts or parts[0] == "store":
                        target_file = WEBROOT_DIR / "store" / "index.html"
                    elif parts[0] == "data" and len(parts) > 1:
                        target_file = WEBROOT_DIR / "data" / parts[1]
                        c_type = "application/json; charset=utf-8"
                    else:
                        clean_bot = parts[0].replace("bot_", "").lower()
                        p1 = WEBROOT_DIR / clean_bot / "index.html"
                        p2 = WEBAPPS_DIR / f"{clean_bot}.html"
                        if p1.exists():
                            target_file = p1
                        elif p2.exists():
                            target_file = p2

                    if target_file and target_file.exists():
                        try:
                            content = target_file.read_bytes()
                            self._send_bytes(200, content, content_type=c_type)
                            return
                        except Exception as e:
                            self._json(500, {"error": f"Failed reading mini app file: {e}"})
                            return
                    else:
                        self._send_bytes(404, b"<!DOCTYPE html><html><body style='text-align:center;padding:50px;'><h2>\xd8\xa7\xd9\x84\xd8\xaa\xd8\xb7\xd8\xa8\xd9\x8a\xd9\x82 \xd8\xba\xd9\x8a\xd8\xb1 \xd9\x85\xd9\x88\xd8\xac\xd9\x88\xd8\xaf</h2></body></html>")
                else:
                    self._json(404, {"error": "Not Found"})

            def do_POST(self):
                path = urlparse(self.path).path.rstrip("/")

                # 1) نقطة نهاية لتحديث وحقن الإعلانات عن بُعد
                if path == "/api/ads/set":
                    if server.secret:
                        token = self.headers.get(SECRET_HEADER, "")
                        if token != server.secret:
                            self._json(401, {"error": "Unauthorized"})
                            return
                    try:
                        length = int(self.headers.get("Content-Length") or 0)
                        payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                        bot_id = payload.get("bot_id", "").strip().lower().replace("bot_", "")
                        if not bot_id:
                            self._json(400, {"error": "Missing bot_id"})
                            return
                        d_link = payload.get("direct_link", "").strip()
                        z_id = str(payload.get("zone_id", "")).strip()
                        s_url = payload.get("script_url", "").strip()
                        fmt = payload.get("format", "direct_link")
                        freq = int(payload.get("frequency", 3))
                        active = bool(payload.get("active", True))

                        from ad_manager import get_ad_manager
                        mgr = get_ad_manager()
                        mgr.set_monetag_config(bot_id, direct_link=d_link, zone_id=z_id,
                                               script_url=s_url, format_type=fmt,
                                               frequency=freq, active=active)
                        from ad_watcher import sync_mini_apps
                        sync_report = sync_mini_apps()
                        self._json(200, {
                            "ok": True,
                            "bot_id": bot_id,
                            "message": f"Updated Monetag ads for {bot_id} and synchronized HTML files.",
                            "sync": sync_report
                        })
                    except Exception as e:
                        self._json(500, {"error": str(e)})
                    return

                # 2) التحقق من السر لتحديثات تيليجرام (إن فُعّل)
                if server.secret:
                    token = self.headers.get(SECRET_HEADER, "")
                    if token != server.secret:
                        self._json(401, {"error": "Unauthorized"})
                        return

                # 2) تحديد البوت المستهدف من المسار
                target = server._resolve_bot(path)
                if target is None:
                    self._json(404, {"error": "Unknown webhook path"})
                    return

                # 3) قراءة التحديث وتحويله
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    raw = self.rfile.read(length) if length else b"{}"
                    payload = json.loads(raw.decode("utf-8"))
                    from telebot.types import Update
                    update = Update.de_json(payload)
                except Exception as e:
                    logger.warning(f"webhook payload error: {e}")
                    self._json(400, {"error": "Invalid update payload"})
                    return

                # 4) تمرير التحديث للبوت
                try:
                    target.process_new_updates([update])
                except Exception as e:
                    logger.error(f"webhook processing error: {e}")
                    self._json(500, {"error": "Processing failed"})
                    return

                self._json(200, {"ok": True})

        return Handler
