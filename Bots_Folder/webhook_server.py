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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

logger = logging.getLogger("WebhookServer")

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
                        "endpoints": ["/health", "POST /webhook/<bot_id>"],
                        "bots": server.bot_names(),
                    })
                else:
                    self._json(404, {"error": "Not Found"})

            def do_POST(self):
                path = urlparse(self.path).path.rstrip("/")

                # 1) التحقق من السر (إن فُعّل)
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
