"""
api_server.py — خادم واجهة برمجة التطبيقات (API) وفحص الصحة والمراقبة
يوفر واجهة برمجية HTTP خفيفة ومستقلة (تعتمد على المكتبة القياسية) لمراقبة:
- فحص صحة النظام (/health)
- إحصائيات الاستخدام وقاعدة البيانات (/api/stats)
- قائمة البوتات المسجلة وحالاتها (/api/bots)
- استعراض أحدث السجلات (/api/logs)
- استقبال أحداث التتبع من التطبيقات المصغّرة (POST /api/track)

🔐 الأمان (v5):
- طلبات localhost (127.0.0.1) مسموحة دائماً (للاستخدام المحلي والاختبارات)
- الطلبات الخارجية تتطلب ترويسة X-API-Key مطابقة للمتغير API_SERVER_KEY في .env
- إن لم يُضبط API_SERVER_KEY تُرفض كل الطلبات الخارجية (آمن افتراضياً)
- الاستماع الافتراضي على 127.0.0.1 فقط — استخدم --host 0.0.0.0 عمداً عند الحاجة

الاستخدام:
    python api_server.py              ← تشغيل الخادم على المنفذ 8080
    python api_server.py --port 5000  ← تشغيل على منفذ مخصص
"""
import os
import sys
import json
import time
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

BASE_DIR    = Path(__file__).parent.resolve()
BOTS_DIR    = BASE_DIR / "Bots_Folder"
DATA_DIR    = BASE_DIR / "Data"
LOGS_DIR    = BASE_DIR / "Logs"
REGISTRY    = BASE_DIR / "bots_registry.json"
EVENTS_FILE = DATA_DIR / "events.jsonl"

SERVER_VERSION = "5.0.0"
DEFAULT_PORT   = 8080

# 🔐 مفتاح API من البيئة (اختياري للوصول الخارجي)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass
API_SERVER_KEY = os.getenv("API_SERVER_KEY", "").strip()


def record_event(event: dict) -> bool:
    """تسجيل حدث تتبع وارد من تطبيق مصغّر في Data/events.jsonl"""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        event["received_at"] = datetime.now().isoformat()
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _get_db():
    try:
        sys.path.insert(0, str(BOTS_DIR))
        from database import get_db
        return get_db()
    except Exception:
        return None


def get_system_health() -> dict:
    """جمع بيانات الفحص الصحي للنظام"""
    env_file = BASE_DIR / ".env"
    db_file = DATA_DIR / "boda_bot.db"

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": SERVER_VERSION,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "env_configured": env_file.exists(),
        "database_ready": db_file.exists(),
        "uptime_seconds": int(time.time() - getattr(get_system_health, "_start_time", time.time()))
    }

get_system_health._start_time = time.time()


def get_bots_list() -> list:
    """استرجاع قائمة البوتات من الـ Registry"""
    if not REGISTRY.exists():
        return []
    try:
        with open(REGISTRY, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("bots", [])
    except Exception:
        return []


def get_db_stats() -> dict:
    """استرجاع إحصائيات قاعدة البيانات"""
    db = _get_db()
    if not db:
        return {"error": "Database not available", "total_users": 0, "bots_stats": []}
    return {
        "total_users": db.get_all_users_count(),
        "database_size": db.get_db_size(),
        "bots_stats": db.get_stats_summary()
    }


def get_recent_logs(bot_name: str = None, max_lines: int = 50) -> list:
    """استرجاع آخر أسطر السجلات"""
    if not LOGS_DIR.exists():
        return []

    lines = []
    if bot_name:
        log_file = LOGS_DIR / f"{bot_name}.log"
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f.readlines()[-max_lines:]]
            except Exception:
                pass
    else:
        # قراءة من أحدث ملف سجل
        log_files = sorted(LOGS_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        if log_files:
            try:
                with open(log_files[0], "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f.readlines()[-max_lines:]]
            except Exception:
                pass

    return lines


class BodaAPIHandler(BaseHTTPRequestHandler):
    """معالج طلبات HTTP لـ Boda Bot API"""

    def _send_json(self, status_code: int, data: dict or list):
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _is_authorized(self) -> bool:
        """الطلبات المحلية مسموحة؛ الخارجية تتطلب X-API-Key صحيحاً"""
        client_ip = self.client_address[0]
        if client_ip in ("127.0.0.1", "::1", "localhost"):
            return True
        if API_SERVER_KEY:
            key = self.headers.get("X-API-Key", "")
            return bool(key) and key == API_SERVER_KEY
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # /health عام دائماً (لأدوات المراقبة)
        if path in ("", "/health"):
            self._send_json(200, get_system_health())
            return

        if not self._is_authorized():
            self._send_json(403, {"error": "Forbidden — أدخل X-API-Key صحيحاً"})
            return

        if path == "/api/stats":
            self._send_json(200, get_db_stats())

        elif path == "/api/bots":
            self._send_json(200, get_bots_list())

        elif path == "/api/logs":
            bot = qs.get("bot", [None])[0]
            try:
                limit = int(qs.get("limit", [50])[0])
            except ValueError:
                limit = 50
            self._send_json(200, {
                "bot": bot or "latest",
                "lines": get_recent_logs(bot_name=bot, max_lines=limit)
            })

        elif path == "/api/events":
            # آخر أحداث التتبع المستلمة من التطبيقات
            events = []
            if EVENTS_FILE.exists():
                try:
                    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                        events = [json.loads(l) for l in f.readlines()[-200:] if l.strip()]
                except Exception:
                    pass
            self._send_json(200, {"count": len(events), "events": events[::-1]})

        else:
            self._send_json(404, {
                "error": "Not Found",
                "endpoints": ["/health", "/api/stats", "/api/bots",
                              "/api/logs", "/api/events", "POST /api/track"]
            })

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/track":
            # نقطة تتبع أحداث التطبيقات المصغّرة (مفتوحة مع تحديد حجم الطلب)
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 4 * 1024)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except Exception:
                body = {}
            ok = record_event(body if isinstance(body, dict) else {"raw": str(body)[:200]})
            self._send_json(200 if ok else 500, {"ok": ok})
            return

        if not self._is_authorized():
            self._send_json(403, {"error": "Forbidden — أدخل X-API-Key صحيحاً"})
            return

        self._send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        # تعطيل طباعة الطلبات في terminal للحفاظ على نظافة المخرجات
        pass


def run_api_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> HTTPServer:
    """تشغيل خادم الـ API (افتراضياً محلي فقط — مرر --host 0.0.0.0 عمداً عند النشر)"""
    server = HTTPServer((host, port), BodaAPIHandler)
    print(f"🚀 Boda Bot API Server v{SERVER_VERSION} running on http://{host}:{port}")
    if host in ("0.0.0.0", "::") and not API_SERVER_KEY:
        print("⚠️  تحذير: الاستماع على كل الواجهات بدون API_SERVER_KEY — الطلبات الخارجية سترفض تلقائياً")
    return server


def start_api_thread(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> threading.Thread:
    """تشغيل خادم الـ API في Thread خلفي"""
    server = run_api_server(host, port)
    t = threading.Thread(target=server.serve_forever, daemon=True, name="BodaAPIServer")
    t.start()
    return t


if __name__ == "__main__":
    port = DEFAULT_PORT
    host = "127.0.0.1"
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (ValueError, IndexError):
            pass
    if "--host" in sys.argv:
        try:
            host = sys.argv[sys.argv.index("--host") + 1]
        except IndexError:
            pass

    server = run_api_server(host=host, port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹ إيقاف خادم API.")
        server.server_close()
