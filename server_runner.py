# =============================================================================
#  server_runner.py — المشغّل الإنتاجي بلا واجهة (Headless Supervisor)
#
#  لماذا؟
#      Manager.py واجهة Tkinter تحتاج شاشة — غير مناسبة للسيرفرات.
#      هذا المشغّل يدير كل البوتات في عملية واحدة (أو مجموعة محددة) داخل Docker.
#
#  المزايا:
#      • Polling (افتراضي) أو Webhook (USE_WEBHOOK=true) عبر خادم واحد مشترك
#      • تشغيل مجموعة محددة من البوتات: BODA_BOTS=currency,qrgen أو --bots
#      • إعادة تشغيل تلقائية لأي بوت يتعطل مع Backoff تدريجي
#      • نسخ احتياطي مجدول لقاعدة البيانات + اختبار استعادة فعلي تلقائي
#      • إيقاف نظيف عند SIGTERM/SIGINT (مناسب لـ Docker)
#
#  التشغيل:
#      python server_runner.py                    # كل البوتات — polling
#      python server_runner.py --bots currency,qrgen
#      USE_WEBHOOK=true WEBHOOK_BASE_URL=https://bots.example.com python server_runner.py
# =============================================================================
import argparse
import importlib
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
BOTS_DIR = BASE_DIR / "Bots_Folder"
REGISTRY = BASE_DIR / "bots_registry.json"

# تحميل متغيرات البيئة قبل فحص التوكنات واختيار الوضع
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

if str(BOTS_DIR) not in sys.path:
    sys.path.insert(0, str(BOTS_DIR))

try:
    from logger_config import configure_windows_encoding, get_logger
    configure_windows_encoding()
    log = get_logger("runner")
except Exception:  # pragma: no cover - fallback لو تعذر استيراد اللوجر
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="[Runner] %(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    log = logging.getLogger("runner")


# ── قراءة السجل والأدوات المساعدة ───────────────────────────────────────────
def load_registry(path: Path | None = None) -> list:
    """إرجاع قائمة البوتات من bots_registry.json (يدعم الشكلين list/dict)."""
    path = path or REGISTRY
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("bots", [])
    except Exception as e:
        log.error(f"تعذر قراءة السجل {path}: {e}")
        return []


def parse_bots_arg(raw: str) -> list:
    """تحويل نص الفلتر إلى قائمة معرفات نظيفة (يدعم , ومسافات وbot_ بادئة)."""
    if not raw:
        return []
    cleaned = raw.replace(";", ",").replace(" ", ",")
    parts = [p.strip().lower().replace("bot_", "") for p in cleaned.split(",")]
    return [p for p in parts if p and p not in ("all", "*")]


def select_bot_ids(registry: list, raw_filter: str = "") -> tuple:
    """
    اختيار البوتات المطلوبة مع الحفاظ على ترتيب السجل.

    Returns:
        (selected_ids, unknown_ids)
    """
    known = [b.get("id", "") for b in registry if b.get("id")]
    wanted = parse_bots_arg(raw_filter)
    if not wanted:
        return known, []
    wanted_set = set(wanted)
    selected = [bid for bid in known if bid in wanted_set]
    unknown = [bid for bid in wanted if bid not in set(known)]
    return selected, unknown


def token_env_key(bot_id: str) -> str:
    """اسم متغير التوكن المتوقع في .env لكل بوت."""
    return f"BOT_{bot_id.upper()}_TOKEN"


def has_valid_token(bot_id: str) -> bool:
    """فحص سريع لوجود توكن بصيغة صحيحة (بدون اتصال شبكي)."""
    import re
    token = os.getenv(token_env_key(bot_id), "").strip()
    return bool(re.match(r"^\d{5,}:[\w-]{20,}$", token))


def import_bot_module(bot_id: str):
    """استيراد وحدة البوت bot_<id>.py وإرجاعها (مع كائن bot بداخلها)."""
    module_name = f"bot_{bot_id}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    return importlib.import_module(module_name)


# ── نسخ احتياطي مجدول + تحقق تلقائي ─────────────────────────────────────────
def start_backup_scheduler(stop_event: threading.Event,
                           interval_hours: float | None = None,
                           first_delay: float = 30.0) -> threading.Thread | None:
    """
    خيط خلفي ينشئ نسخة احتياطية دورياً ويجري عليها اختبار استعادة فعلي.
    يُعطَّل بضبط BODA_BACKUP_HOURS=0.
    """
    if interval_hours is None:
        try:
            interval_hours = float(os.getenv("BODA_BACKUP_HOURS", "24"))
        except ValueError:
            interval_hours = 24.0
    if interval_hours <= 0:
        log.info("💾 النسخ الاحتياطي المجدول: معطّل (BODA_BACKUP_HOURS=0)")
        return None

    def _loop():
        if stop_event.wait(first_delay):
            return
        while not stop_event.is_set():
            try:
                from backup_manager import create_backup, verify_backup
                path = create_backup(compress=True)
                report = verify_backup(path)
                if report.get("ok"):
                    log.info(f"💾 نسخة احتياطية موثّقة: {path.name} "
                             f"(جداول: {report.get('tables', {})})")
                else:
                    msg = f"فحص الاستعادة فشل للنسخة {path.name}: {report.get('error')}"
                    log.error(f"❌ {msg}")
                    try:
                        from monitor_agent import send_telegram_alert
                        send_telegram_alert(f"⚠️ <b>Boda Backup</b>\n{msg}")
                    except Exception:
                        pass
            except Exception as e:
                log.exception(f"❌ فشل النسخ الاحتياطي المجدول: {e}")
            if stop_event.wait(interval_hours * 3600):
                break

    t = threading.Thread(target=_loop, name="BackupScheduler", daemon=True)
    t.start()
    log.info(f"💾 النسخ الاحتياطي المجدول كل {interval_hours:g} ساعة (مع اختبار استعادة)")
    return t


# ── مزامنة استباقية لتطبيقات الويب وإعلانات Monetag ─────────────────────────
def preflight_sync_mini_apps():
    """فحص ومزامنة استباقية لملفات تطبيقات الويب وحقن شفرات الإعلانات قبل الانطلاق."""
    try:
        from ad_watcher import sync_mini_apps
        res = sync_mini_apps()
        if res.get("ok"):
            log.info("📢 المزامنة الاستباقية: تم تجهيز ملفات تطبيقات الويب وحقن شفرات Monetag.")
        else:
            log.warning(f"⚠ تعذر إكمال مزامنة تطبيقات الويب: {res.get('error')}")
    except Exception as e:
        log.warning(f"⚠ خطأ في المزامنة الاستباقية: {e}")


# ── وضع Polling ──────────────────────────────────────────────────────────────
def polling_worker(bot_id: str, module, stop_event: threading.Event):
    """تشغيل بوت واحد عبر Polling مع إعادة تشغيل تلقائية عند الانهيار."""
    from bot_base import start_polling

    backoff = 5
    while not stop_event.is_set():
        try:
            log.info(f"▶ [{bot_id}] بدء Polling...")
            start_polling(module.bot, bot_id, allowed_updates=None)
            log.warning(f"⚠ [{bot_id}] توقف Polling بشكل غير متوقع — إعادة تشغيل")
        except KeyboardInterrupt:
            break
        except SystemExit as e:
            log.error(f"✖ [{bot_id}] خرج (code={e.code}) — إعادة محاولة")
        except BaseException as e:
            log.exception(f"✖ [{bot_id}] انهيار — إعادة محاولة خلال {backoff}ث")
            try:
                from error_tracker import track_exception
                track_exception(bot_id, e, context="runner_crash")
            except Exception:
                pass

        if stop_event.wait(backoff):
            break
        backoff = min(backoff * 2, 300)


def run_polling(modules: dict, stop_event: threading.Event) -> int:
    """تشغيل كل البوتات المحددة في خيوط مستقلة."""
    threads = []
    for bot_id, module in modules.items():
        t = threading.Thread(target=polling_worker,
                             args=(bot_id, module, stop_event),
                             name=f"bot_{bot_id}", daemon=True)
        t.start()
        threads.append(t)

    log.info(f"✅ يعمل الآن {len(threads)} بوتاً بنظام Polling — اضغط Ctrl+C للإيقاف")
    while not stop_event.wait(1):
        pass

    log.info("⏹ جاري إيقاف البوتات...")
    for t in threads:
        t.join(timeout=3)
    return 0


# ── وضع Webhook ──────────────────────────────────────────────────────────────
def run_webhook(modules: dict, stop_event: threading.Event,
                host: str, port: int, base_url: str, secret: str) -> int:
    """تشغيل خادم Webhook واحد يستقبل تحديثات كل البوتات المحددة."""
    from webhook_server import WebhookServer
    from bot_base import prepare_bot, get_db

    db = get_db()
    sessions = {}
    server = WebhookServer(host=host, port=port, secret=secret)
    started = []

    for bot_id, module in modules.items():
        try:
            me = module.bot.get_me()
            log.info(f"✅ [{bot_id}] متصل: @{getattr(me, 'username', '?')}")
            prepare_bot(module.bot, bot_id, log)
            server.register(bot_id, module.bot)

            kwargs = dict(url=server.public_url(base_url, bot_id),
                          drop_pending_updates=True)
            if secret:
                kwargs["secret_token"] = secret
            module.bot.set_webhook(**kwargs)

            if db:
                try:
                    sessions[bot_id] = db.record_bot_start(bot_id)
                except Exception:
                    pass
            started.append(bot_id)
            log.info(f"🌐 [{bot_id}] Webhook: {server.webhook_path(bot_id)}")
        except Exception as e:
            log.error(f"✖ [{bot_id}] فشل تجهيز Webhook: {e}")
            try:
                from error_tracker import track_exception
                track_exception(bot_id, e, context="runner_webhook_setup")
            except Exception:
                pass

    if not started:
        log.error("❌ لا يوجد أي بوت جاهز — تحقق من التوكنات و WEBHOOK_BASE_URL")
        return 1

    server.start()
    log.info(f"✅ Webhook server يعمل على {host}:{server.actual_port} "
             f"لـ {len(started)} بوتاً — بانتظار التحديثات")
    log.info(f"📱 خادم تطبيقات الويب المصغرة متاح على: http://{host}:{server.actual_port}/apps/<bot_id>")
    log.info(f"📢 واجهة التحكم بالإعلانات متاحة على: http://{host}:{server.actual_port}/api/ads/status")
    while not stop_event.wait(1):
        pass

    log.info("⏹ إيقاف Webhook وحذف الروابط...")
    for bot_id in started:
        try:
            modules[bot_id].bot.remove_webhook()
        except Exception:
            pass
        if db and bot_id in sessions:
            try:
                db.record_bot_stop(sessions[bot_id])
            except Exception:
                pass
    server.stop()
    return 0


# ── نقطة الدخول ──────────────────────────────────────────────────────────────
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Boda Bot System — مشغّل إنتاجي بلا واجهة")
    p.add_argument("--bots", default=os.getenv("BODA_BOTS", ""),
                   help="قائمة معرفات مفصولة بفواصل (افتراضياً الكل)")
    p.add_argument("--webhook", action="store_true",
                   help="إجبار وضع Webhook بدل Polling")
    p.add_argument("--polling", action="store_true",
                   help="إجبار وضع Polling")
    p.add_argument("--host", default=os.getenv("WEBHOOK_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int,
                   default=int(os.getenv("WEBHOOK_PORT", "8443")))
    p.add_argument("--base-url",
                   default=os.getenv("WEBHOOK_BASE_URL",
                                     os.getenv("WEBHOOK_URL", "")))
    p.add_argument("--dry-run", action="store_true",
                   help="عرض البوتات المختارة دون تشغيل")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    registry = load_registry()
    selected, unknown = select_bot_ids(registry, args.bots)
    if unknown:
        log.warning(f"⚠ معرفات غير معروفة تم تجاهلها: {', '.join(unknown)}")
    if not selected:
        log.error("❌ لا توجد بوتات مطابقة للتشغيل — راجع BODA_BOTS")
        return 2

    allow_missing = os.getenv("BODA_ALLOW_MISSING_TOKENS", "0").lower() in ("1", "true", "yes")
    ready, missing = [], []
    for bid in selected:
        (ready if (has_valid_token(bid) or allow_missing) else missing).append(bid)
    if missing:
        log.warning(f"⚠ بلا توكن صالح (تم تخطيها): {', '.join(missing)}")
    if not ready:
        log.error("❌ لا يوجد بوت بتوكن صالح — أضف التوكنات إلى .env")
        return 3

    if args.dry_run:
        log.info(f"🔎 وضع المعاينة: {len(ready)} بوتاً جاهزاً: {', '.join(ready)}")
        return 0

    # تحميل وحدات البوتات
    modules = {}
    for bid in ready:
        try:
            modules[bid] = import_bot_module(bid)
        except Exception as e:
            log.error(f"✖ [{bid}] تعذر الاستيراد: {e}")

    if not modules:
        return 4

    # اختيار الوضع
    use_webhook = args.webhook or (
        not args.polling and os.getenv("USE_WEBHOOK", "false").lower()
        in ("1", "true", "yes"))
    if use_webhook and not args.base_url:
        log.error("❌ USE_WEBHOOK مفعّل لكن WEBHOOK_BASE_URL غير مضبوط في .env")
        return 5

    stop_event = threading.Event()

    def _handle_signal(signum, _frame):
        log.info(f"📴 إشارة إيقاف ({signum}) — إنهاء نظيف...")
        stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _handle_signal)
            except (ValueError, OSError):
                pass

    # مزامنة استباقية لتطبيقات الويب وإعلانات Monetag قبل الانطلاق
    preflight_sync_mini_apps()

    # تشغيل مراقب ملفات الإعلانات التلقائي لمزامنة أي تعديل فورياً بدون إعادة تشغيل
    try:
        from ad_watcher import start_ad_watcher
        start_ad_watcher(stop_event, check_interval=2.0, custom_logger=log)
    except Exception as e:
        log.warning(f"⚠ تعذر بدء مراقب الإعلانات التلقائي: {e}")

    # النسخ الاحتياطي المجدول (يعمل في الوضعين)
    start_backup_scheduler(stop_event)

    if use_webhook:
        secret = os.getenv("WEBHOOK_SECRET", "").strip()
        if not secret:
            log.warning("⚠ WEBHOOK_SECRET غير مضبوط — يُنصح بضبطه لحماية الروابط")
        return run_webhook(modules, stop_event, args.host, args.port,
                           args.base_url, secret)

    return run_polling(modules, stop_event)


if __name__ == "__main__":
    raise SystemExit(main())
