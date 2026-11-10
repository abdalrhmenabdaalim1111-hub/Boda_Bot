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
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

BASE_DIR    = Path(__file__).parent.resolve()
BOTS_DIR    = BASE_DIR / "Bots_Folder"
DATA_DIR    = BASE_DIR / "Data"
LOGS_DIR    = BASE_DIR / "Logs"
REGISTRY    = BASE_DIR / "bots_registry.json"
EVENTS_FILE = DATA_DIR / "events.jsonl"
WEBROOT_DIR = BASE_DIR / "webroot"
WEBAPPS_DIR = BASE_DIR / "webapps"

SERVER_VERSION = "5.0.0"
DEFAULT_PORT   = 8080

# 🔐 مفتاح API من البيئة (اختياري للوصول الخارجي)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass
API_SERVER_KEY = os.getenv("API_SERVER_KEY", "").strip()

# ── Control Center integration (Phase 1) ─────────────────────────────────────
# The Control Center is an *extension* of this server: every legacy route
# below keeps working exactly as before, and the new /api/v1 surface is
# dispatched first. If the package cannot be imported the legacy server
# still starts — a broken control plane must never take the bots offline.
try:
    from control_center import api as cc_api
    from control_center import migrations as cc_migrations
    from control_center.http import Response as CCResponse
    from control_center.http import Request as CCRequest
    CONTROL_CENTER_AVAILABLE = True
except Exception as _cc_error:  # pragma: no cover - defensive
    cc_api = None
    cc_migrations = None
    CCResponse = None
    CONTROL_CENTER_AVAILABLE = False
    print(f"⚠️  Control Center غير متاح ({_cc_error}) — يعمل الخادم بالوضع القديم")


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


def _env_configured() -> bool:
    """
    هل البيئة مضبوطة؟
    محليًا: وجود .env — داخل Docker: .env غير منسوخ (env_file يحقن المتغيرات)
    لذلك نعتبر وجود أي توكن بوت صالح دليلًا كافيًا.
    """
    if (BASE_DIR / ".env").exists():
        return True
    return any(
        k.startswith("BOT_") and k.endswith("_TOKEN") and str(v).strip()
        for k, v in os.environ.items()
    )


def get_system_health() -> dict:
    """جمع بيانات الفحص الصحي للنظام"""
    db_file = DATA_DIR / "boda_bot.db"

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": SERVER_VERSION,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "env_configured": _env_configured(),
        "database_ready": db_file.exists(),
        "uptime_seconds": int(time.time() - getattr(get_system_health, "_start_time", time.time()))
    }

get_system_health._start_time = time.time()


def get_readiness() -> dict:
    """
    فحص الجاهزية (Readiness) للمراقبة الخارجية:
    يعيد ready=False وخادم HTTP 503 إذا كانت البيئة أو قاعدة البيانات غير جاهزة.
    """
    env_file = BASE_DIR / ".env"
    db_file = DATA_DIR / "boda_bot.db"
    checks = {
        "env_configured": _env_configured(),
        "database_ready": db_file.exists(),
    }
    ready = all(checks.values())
    return {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
        "version": SERVER_VERSION,
    }


def get_engagement_overview() -> dict:
    """
    بيانات لوحة التحليلات (/api/overview) — تُبنى من قاعدة البيانات المشتركة:
    • نشاط المستخدمين: الإجمالي + يوم/7 أيام/30 يوماً (آخر ظهور) ونسبة الالتصاق DAU/MAU
    • قمع بوابة الشبكة: مستخدمون → معيّنون على بوتات الخمسة → فعّلوا الشبكة
    • الإحالات الفيروسية، أعلى 10 بوتات، ولمحة سريعة من اختبار A/B للإعلانات
    """
    db = _get_db()
    if db is None:
        return {"error": "قاعدة البيانات غير متاحة"}

    now = datetime.now()

    def _cutoff(days: int) -> str:
        return (now - timedelta(days=days)).strftime("%Y-%m-%d") + " 00:00:00"

    with db._get_conn() as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        distinct_users = int(conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM users").fetchone()[0])

        def _active(cutoff: str) -> int:
            return int(conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM users WHERE last_seen >= ?",
                (cutoff,)).fetchone()[0])

        dau, wau, mau = _active(_cutoff(0)), _active(_cutoff(7)), _active(_cutoff(30))

        assigned = int(conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM network_assignments").fetchone()[0])
        activated = int(conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM network_activations "
            "WHERE is_active = 1").fetchone()[0])
        referrals_total = int(conn.execute(
            "SELECT COUNT(*) FROM referrals").fetchone()[0])
        referrers = int(conn.execute(
            "SELECT COUNT(DISTINCT referrer_id) FROM referrals").fetchone()[0])
        top_rows = conn.execute(
            "SELECT bot_name, COUNT(*) AS users, "
            "SUM(CASE WHEN last_seen >= ? THEN 1 ELSE 0 END) AS active30 "
            "FROM users GROUP BY bot_name ORDER BY users DESC LIMIT 10",
            (_cutoff(30),)).fetchall()

    top_bots = [{"bot_name": r["bot_name"], "users": int(r["users"]),
                 "active_30d": int(r["active30"] or 0)} for r in top_rows]

    def _pct(part: int, whole: int) -> float:
        return round(part * 100.0 / whole, 1) if whole else 0.0

    overview = {
        "generated_at": datetime.now().isoformat(),
        "users": {
            "total": total,
            "distinct_users": distinct_users,
            "dau": dau,
            "wau": wau,
            "mau": mau,
        },
        "retention_dau_mau_percent": _pct(dau, mau),
        "funnel": {
            "users": distinct_users,
            "assigned": assigned,
            "assigned_percent": _pct(assigned, distinct_users),
            "activated": activated,
            "activated_percent": _pct(activated, distinct_users),
        },
        "referrals": {
            "total": referrals_total,
            "unique_referrers": referrers,
        },
        "top_bots": top_bots,
    }

    try:
        overview["ab_testing"] = db.get_ab_report()
        overview["ab_testing"]["ok"] = True
    except Exception as e:  # لوحة الإعلانات لا تُعطّل اللوحة الأساسية
        overview["ab_testing"] = {"ok": False, "error": str(e)[:120]}
    return overview


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

    def _send_bytes(self, status_code: int, body: bytes, content_type: str = "text/html; charset=utf-8"):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _is_authorized(self) -> bool:
        """الطلبات المحلية مسموحة؛ الخارجية تتطلب X-API-Key صحيحاً"""
        client_ip = self.client_address[0]
        if client_ip in ("127.0.0.1", "::1", "localhost"):
            return True
        if API_SERVER_KEY:
            key = self.headers.get("X-API-Key", "")
            return bool(key) and key == API_SERVER_KEY
        return False

    # ── Control Center dispatch ─────────────────────────────────────────────
    def _send_control_center(self, response) -> None:
        """Write a Control Center response (CORS headers included)."""
        if response is None:
            return
        if getattr(response, "sent", False):
            return  # the handler already wrote the response (SSE)
        payload = response.payload()
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for key, value in (response.headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _dispatch_control_center(self, method: str) -> bool:
        """
        Hand the request to the Control Center router.

        Returns True when the request was handled (including error answers),
        False when it must fall through to the legacy routes.
        """
        if not CONTROL_CENTER_AVAILABLE:
            return False
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if not (path.startswith("/api/v1") or path in ("/openapi.json", "/docs")):
            return False

        body = b""
        if method == "POST":
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 1024 * 1024)
                body = self.rfile.read(length) if length else b""
            except Exception:
                body = b""

        request = CCRequest(self, method, path, parse_qs(parsed.query), body)
        route, params = cc_api.ROUTER.match(method, path)
        if route is None:
            if params and params.get("_method_mismatch"):
                self._send_json(405, {"error": "Method Not Allowed"})
            else:
                self._send_json(404, {"error": "Not Found",
                                      "hint": "استخدم /openapi.json لعرض المسارات"})
            return True

        request.params = params
        try:
            response = route.handler(request)
        except Exception as exc:
            import traceback
            self._send_json(500, {"error": str(exc),
                                  "traceback": traceback.format_exc()[-1200:]})
            return True

        self._send_control_center(response)
        return True

    def do_OPTIONS(self):
        """CORS preflight for the Control Center and the legacy API."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        if self._dispatch_control_center("GET"):
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # /health عام دائماً (لأدوات المراقبة)
        if path in ("", "/health"):
            self._send_json(200, get_system_health())
            return

        if path == "/ready":
            payload = get_readiness()
            self._send_json(200 if payload.get("ready") else 503, payload)
            return

        # تقديم تطبيقات الويب بدون حجب المفتاح (متاح لمستخدمي تيليجرام)
        if path.startswith("/apps"):
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
                    self._send_bytes(200, target_file.read_bytes(), content_type=c_type)
                    return
                except Exception as e:
                    self._send_json(500, {"error": f"Failed reading file: {e}"})
                    return
            else:
                self._send_bytes(404, b"<!DOCTYPE html><html><body><h2>MiniApp Not Found</h2></body></html>")
                return

        # لوحة التحليلات — صفحة عامة (بياناتها نفسها محمية بمفتاح /api/overview)
        if path == "/dashboard":
            target_file = WEBROOT_DIR / "dashboard" / "index.html"
            if target_file.exists():
                try:
                    self._send_bytes(200, target_file.read_bytes())
                except Exception as e:
                    self._send_json(500, {"error": f"Failed reading dashboard: {e}"})
            else:
                self._send_bytes(404, b"<!DOCTYPE html><html><body><h2>Dashboard Not Found</h2></body></html>")
            return

        if not self._is_authorized():
            self._send_json(403, {"error": "Forbidden — أدخل X-API-Key صحيحاً"})
            return

        if path == "/api/overview":
            # لوحة النمو: نشطون/احتفاظ/قمع/إحالات/أعلى بوتات/A-B
            overview = get_engagement_overview()
            self._send_json(200 if overview.get("error") is None else 503, overview)

        elif path == "/api/stats":
            self._send_json(200, get_db_stats())

        elif path == "/api/bots":
            self._send_json(200, get_bots_list())

        elif path == "/api/ads/status":
            try:
                sys.path.insert(0, str(BOTS_DIR))
                from ad_manager import get_ad_manager
                statuses = get_ad_manager().get_all_monetag_statuses()
                self._send_json(200, {"ok": True, "count": len(statuses), "apps": statuses})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

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
                "endpoints": ["/health", "/ready", "GET /apps/<bot_id>", "/dashboard",
                              "/api/stats", "/api/overview", "/api/bots", "/api/ads/status",
                              "/api/logs", "/api/events", "POST /api/track", "POST /api/ads/set"]
            })

    def do_POST(self):
        if self._dispatch_control_center("POST"):
            return
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

        if path == "/api/ads/set":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                bot_id = payload.get("bot_id", "").strip().lower().replace("bot_", "")
                if not bot_id:
                    self._send_json(400, {"error": "Missing bot_id"})
                    return
                d_link = payload.get("direct_link", "").strip()
                z_id = str(payload.get("zone_id", "")).strip()
                s_url = payload.get("script_url", "").strip()
                fmt = payload.get("format", "direct_link")
                freq = int(payload.get("frequency", 3))
                active = bool(payload.get("active", True))

                sys.path.insert(0, str(BOTS_DIR))
                from ad_manager import get_ad_manager
                mgr = get_ad_manager()
                mgr.set_monetag_config(bot_id, direct_link=d_link, zone_id=z_id,
                                       script_url=s_url, format_type=fmt,
                                       frequency=freq, active=active)
                from ad_watcher import sync_mini_apps
                sync_report = sync_mini_apps()
                self._send_json(200, {
                    "ok": True,
                    "bot_id": bot_id,
                    "message": f"Updated Monetag ads for {bot_id} and synchronized HTML files.",
                    "sync": sync_report
                })
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        self._send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        # تعطيل طباعة الطلبات في terminal للحفاظ على نظافة المخرجات
        pass


def run_api_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> HTTPServer:
    """
    تشغيل خادم الـ API (افتراضياً محلي فقط — مرر --host 0.0.0.0 عمداً عند النشر)

    يستخدم ``ThreadingHTTPServer`` لأن بثّ السجلات (SSE) يتطلب أن لا يحجب
    طلب واحد بقية الطلبات.
    """
    if CONTROL_CENTER_AVAILABLE:
        try:
            report = cc_migrations.ensure_ready()
            if report.get("applied"):
                print(f"🗄️  تم تطبيق ترحيلات قاعدة البيانات: {', '.join(report['applied'])}")
        except Exception as e:
            print(f"⚠️  تعذر تطبيق الترحيلات: {e}")

    server = ThreadingHTTPServer((host, port), BodaAPIHandler)
    server.daemon_threads = True
    print(f"🚀 Boda Bot API Server v{SERVER_VERSION} running on http://{host}:{port}")
    if CONTROL_CENTER_AVAILABLE:
        print(f"🧭  Control Center API: http://{host}:{port}/api/v1  (توثيق: /docs)")
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
