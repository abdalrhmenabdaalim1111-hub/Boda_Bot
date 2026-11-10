# =============================================================================
#  monitor_agent.py — وكيل المراقبة الخارجية وتنبيهات Telegram
#
#  الوظيفة:
#      • فحص /health و /api/stats دورياً (متوافق مع UptimeRobot أو أي مراقب)
#      • إرسال تنبيه Telegram عند تعطل النظام أو تعافيه
#      • منع إغراقك بالرسائل: تنبيه أول مرة ثم كل مدة تبريد (افتراضياً 30 دقيقة)
#
#  الإعداد في .env:
#      BODA_MONITOR_URL=http://127.0.0.1:8080/health
#      BODA_MONITOR_INTERVAL=60
#      BODA_MONITOR_COOLDOWN_MIN=30
#      BODA_MONITOR_BOT_TOKEN=123456:ABC...     # توكن بوت الإشعارات
#      BODA_ADMIN_CHAT_ID=123456789             # شات الأدمن لاستقبال التنبيهات
#      API_SERVER_KEY=...                        # إن كان خادم API محمياً
#
#  التشغيل:
#      python monitor_agent.py           # مراقبة مستمرة
#      python monitor_agent.py --once    # فحص واحد (مناسب لـ cron)
#      python monitor_agent.py --test    # إرسال رسالة تجريبية للتأكد من الإعداد
# =============================================================================
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

DEFAULT_HEALTH_URL = os.getenv("BODA_MONITOR_URL",
                               "http://127.0.0.1:8080/health").strip()
DEFAULT_INTERVAL = int(os.getenv("BODA_MONITOR_INTERVAL", "60") or 60)
DEFAULT_COOLDOWN_MIN = int(os.getenv("BODA_MONITOR_COOLDOWN_MIN", "30") or 30)


# ── تقييم الحالة ─────────────────────────────────────────────────────────────
def evaluate_health(status_code, payload) -> tuple:
    """
    تقييم استجابة /health.

    Returns:
        (is_healthy: bool, detail: str)
    """
    if status_code != 200:
        return False, f"HTTP {status_code}"
    if not isinstance(payload, dict):
        return False, "استجابة غير صالحة (ليست JSON)"
    status = str(payload.get("status", "")).strip().lower()
    if status not in ("healthy", "ok", "up", "running"):
        return False, f"الحالة غير سليمة: {status or 'غير محددة'}"
    if payload.get("database_ready") is False:
        return False, "قاعدة البيانات غير جاهزة"
    return True, "سليم"


def should_alert(is_healthy: bool, prev_healthy, last_alert_ts: float,
                 now_ts: float, cooldown_sec: float) -> bool:
    """
    قرار إرسال التنبيه:
      • تعافٍ بعد عطل → تنبيه واحد
      • أول عطل → تنبيه فوري
      • استمرار العطل → تنبيه كل مدة التبريد فقط
    """
    if is_healthy:
        return prev_healthy is False
    if prev_healthy is not False:
        return True
    return (now_ts - last_alert_ts) >= cooldown_sec


def format_alert(is_healthy: bool, detail: str, stats: dict | None = None) -> str:
    """صياغة رسالة Telegram بالعربية."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if is_healthy:
        lines = ["✅ <b>Boda Bot System — عاد للعمل</b>",
                 f"🕒 {ts}",
                 f"📊 {detail}"]
        if isinstance(stats, dict) and not stats.get("error"):
            if "total_users" in stats:
                lines.append(f"👥 إجمالي المستخدمين: {stats['total_users']}")
    else:
        lines = ["🚨 <b>Boda Bot System — عطل!</b>",
                 f"🕒 {ts}",
                 f"❗ {detail}",
                 "🔎 تحقق من الحاويات: docker compose ps"]
    return "\n".join(lines)


# ── الاتصال والشبكة ──────────────────────────────────────────────────────────
def fetch_json(url: str, timeout: float = 8.0,
               headers: dict | None = None) -> tuple:
    """
    GET آمن يعيد (status_code, payload) دون رفع استثناءات.
    عند فشل الشبكة يعيد (None, رسالة الخطأ النصية).
    """
    try:
        import requests
        resp = requests.get(url, timeout=timeout, headers=headers or {})
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        return resp.status_code, payload
    except Exception as e:
        return None, str(e)[:200]


def check_once(health_url: str, stats_url: str | None = None,
               api_key: str = "") -> dict:
    """فحص واحد شامل وإرجاع تقرير قابل للاختبار."""
    code, payload = fetch_json(health_url)
    ok, detail = evaluate_health(code, payload)
    stats = None
    if ok and stats_url:
        headers = {"X-API-Key": api_key} if api_key else {}
        scode, spayload = fetch_json(stats_url, headers=headers)
        if scode == 200 and isinstance(spayload, dict):
            stats = spayload
    return {
        "ok": ok,
        "detail": detail,
        "status_code": code,
        "payload": payload if isinstance(payload, dict) else None,
        "stats": stats,
    }


def send_telegram_alert(text: str, token: str = "", chat_id: str = "",
                        timeout: float = 10.0) -> bool:
    """إرسال رسالة HTML إلى Telegram. يعيد False بهدوء إن لم يُضبط الإعداد."""
    token = (token or os.getenv("BODA_MONITOR_BOT_TOKEN", "")).strip()
    chat_id = (chat_id or os.getenv("BODA_ADMIN_CHAT_ID", "")).strip()
    if not token or not chat_id:
        return False
    try:
        import requests
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=timeout,
        )
        return bool(resp.ok and resp.json().get("ok"))
    except Exception:
        return False


# ── الحلقة الرئيسية ──────────────────────────────────────────────────────────
def run_once(health_url: str, stats_url: str | None = None,
             api_key: str = "", notify: bool = True) -> int:
    """فحص واحد: يعيد 0 إن كان سليماً و1 إن كان معطلاً."""
    report = check_once(health_url, stats_url, api_key)
    stamp = datetime.now().strftime("%H:%M:%S")
    if report["ok"]:
        print(f"[{stamp}] ✅ النظام سليم ({report['detail']})")
        return 0
    print(f"[{stamp}] ❌ عطل: {report['detail']}")
    if notify:
        send_telegram_alert(format_alert(False, report["detail"]))
    return 1


def monitor_loop(health_url: str, stats_url: str | None,
                 interval: int, cooldown_sec: float,
                 api_key: str = "") -> int:
    """حلقة مراقبة مستمرة مع منع تكرار التنبيهات."""
    print(f"👁 مراقبة {health_url} كل {interval} ثانية "
          f"(تبريد التنبيه {int(cooldown_sec // 60)} دقيقة)")
    prev_ok = None
    last_alert = 0.0
    try:
        while True:
            report = check_once(health_url, stats_url, api_key)
            now = time.time()
            if should_alert(report["ok"], prev_ok, last_alert, now, cooldown_sec):
                if send_telegram_alert(
                        format_alert(report["ok"], report["detail"],
                                     report.get("stats"))):
                    last_alert = now
                    print(f"[{datetime.now():%H:%M:%S}] 📨 تنبيه Telegram أُرسل")
                else:
                    print(f"[{datetime.now():%H:%M:%S}] ⚠ تعذر إرسال التنبيه "
                          "(راجع BODA_MONITOR_BOT_TOKEN / BODA_ADMIN_CHAT_ID)")
            prev_ok = report["ok"]
            time.sleep(max(5, interval))
    except KeyboardInterrupt:
        print("\n👋 إيقاف المراقبة.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Boda Monitor Agent")
    p.add_argument("--once", action="store_true", help="فحص واحد ثم خروج")
    p.add_argument("--test", action="store_true", help="إرسال رسالة تجريبية")
    p.add_argument("--url", default=DEFAULT_HEALTH_URL, help="رابط /health")
    p.add_argument("--stats-url", default="", help="رابط /api/stats")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    p.add_argument("--cooldown", type=int, default=DEFAULT_COOLDOWN_MIN,
                   help="مدة التبريد بالدقائق")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.test:
        ok = send_telegram_alert(
            "🧪 <b>Boda Monitor</b>\nرسالة تجريبية — الإعداد يعمل بنجاح ✅")
        print("✅ تم إرسال الرسالة التجريبية" if ok else
              "❌ تعذر الإرسال — اضبط BODA_MONITOR_BOT_TOKEN و BODA_ADMIN_CHAT_ID")
        return 0 if ok else 1

    stats_url = args.stats_url.strip()
    if not stats_url and args.url.rstrip("/").endswith("/health"):
        stats_url = args.url.rstrip("/")[:-len("/health")] + "/api/stats"

    if args.once:
        return run_once(args.url, stats_url,
                        os.getenv("API_SERVER_KEY", "").strip())

    return monitor_loop(args.url, stats_url, args.interval,
                        args.cooldown * 60,
                        os.getenv("API_SERVER_KEY", "").strip())


if __name__ == "__main__":
    raise SystemExit(main())
