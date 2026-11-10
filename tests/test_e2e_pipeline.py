"""
tests/test_e2e_pipeline.py — اختبار المسار الكامل (E2E) بحساب تجريبي محاكى

المسار المغطى بالكامل دون شبكة:
    POST HTTP بمُحدَّث /start حقيقي البنية (حساب تجريبي)
        → خادم Webhook (تحقق السر)
        → Update.de_json → المعالجات
        → الطبقات الموحدة (تتبع مستخدم + بوابة نمو + إعلانات)
        → قاعدة البيانات (جدول users)
        → API: POST /api/track (أحداث التطبيقات) + GET /api/stats
        → Data/events.jsonl

هذا ما تقوم به "حسابك التجريبي" يدوياً — لكنه مؤتمت وقابل للتكرار.
"""
import json
import sys
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent
BOTS_DIR = ROOT / "Bots_Folder"
for _p in (str(ROOT), str(BOTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import telebot  # noqa: E402

# توكن العرض الموحد (وهمي وموثق — نظّفه أداة الأسرار)
FAKE_TOKEN = "1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
SECRET = "e2e-secret"
USER_ID = 777000111
BOT_ID = "e2etest"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """قاعدة بيانات + ملف أحداث معزولان داخل tmp_path (لا مساس بالبيانات الحية)."""
    monkeypatch.setenv("BODA_DB_PATH", str(tmp_path / "e2e.db"))
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("API_SERVER_KEY", raising=False)
    monkeypatch.delenv("BODA_ALLOW_MISSING_TOKENS", raising=False)
    import database
    database.BodaDatabase.reset_instance()

    import api_server
    monkeypatch.setattr(api_server, "API_SERVER_KEY", "")
    monkeypatch.setattr(api_server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(api_server, "EVENTS_FILE", tmp_path / "events.jsonl")
    yield tmp_path
    database.BodaDatabase.reset_instance()


def _make_bot() -> tuple:
    """
    بوت حقيقي (كائن TeleBot) مع تعطيل كل إرسال شبكي، وتحضيره بطبقات النظام.
    يعيد (bot, sent): `sent` يسجل كل محاولة إرسال (توفرها الطبقات تلمليها).
    """
    from bot_base import prepare_bot
    sent = []

    def _record_send(*a, **k):
        sent.append((a, k))

    bot = telebot.TeleBot(FAKE_TOKEN, parse_mode="HTML", threaded=False)
    setattr(bot, "send_message", _record_send)
    for method in ("reply_to", "edit_message_text",
                   "answer_callback_query", "send_chat_action",
                   "answer_pre_checkout_query", "send_invoice"):
        setattr(bot, method, MagicMock())
    prepare_bot(bot, BOT_ID)
    return bot, sent


def _start_update(update_id: int = 5001) -> dict:
    """مُحدَّث /start بنفس بنية JSON التي يرسلها تيليجرام لحساب تجريبي."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": 77,
            "from": {"id": USER_ID, "is_bot": False, "first_name": "E2E",
                     "username": "e2e_user", "language_code": "ar"},
            "chat": {"id": USER_ID, "first_name": "E2E", "type": "private"},
            "date": 1700000000,
            "text": "/start",
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }


def _post(url: str, payload: dict, secret: str, code_only: bool = False):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "X-Telegram-Bot-Api-Secret-Token": secret,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return (resp.status if code_only else
                    (resp.status, json.loads(body)))
    except urllib.error.HTTPError as e:  # noqa: F821
        return (e.code if code_only else
                (e.code, e.read().decode("utf-8", errors="replace")))


def test_full_pipeline_http_to_db_to_api(env):
    """حساب تجريبي: /start عبر Webhook → DB ثم حدث تطبيق عبر /api/track → JSONL."""
    from bot_base import prepare_bot  # noqa: F401 (ضمان توفر المسار)
    from webhook_server import WebhookServer
    import database
    import api_server

    bot, sent = _make_bot()
    server = WebhookServer(host="127.0.0.1", port=0, secret=SECRET)
    try:
        server.register(BOT_ID, bot)
        server.start()

        url = f"http://127.0.0.1:{server.actual_port}" \
              f"{server.webhook_path(BOT_ID)}"
        code, body = _post(url, _start_update(), SECRET)
        assert code == 200, body
        assert body.get("ok") is True

        # 1) المستخدم التجريبي وصل قاعدة البيانات عبر الطبقة الموحدة
        db = database.get_db()
        assert db.get_user_count(BOT_ID) == 1

        # 2) خادم API يعمل محلياً ويتسلم أحداث التطبيق
        api_srv = api_server.run_api_server("127.0.0.1", 0)
        api_thread = __import__("threading").Thread(
            target=api_srv.serve_forever, daemon=True)
        api_thread.start()
        try:
            api_base = f"http://127.0.0.1:{api_srv.server_address[1]}"

            tcode, tbody = _post(
                f"{api_base}/api/track",
                {"event": "page_view", "bot": BOT_ID, "user_id": USER_ID,
                 "page": "index"},
                secret="")
            assert tcode == 200, tbody
            assert tbody.get("ok") is True

            # ملف الأحداث المعزول استقبل السطر مع توقيت الاستلام
            lines = (env / "events.jsonl").read_text(
                encoding="utf-8").strip().splitlines()
            assert len(lines) == 1
            recorded = json.loads(lines[0])
            assert recorded["event"] == "page_view"
            assert recorded["received_at"]

            # 3) الإحصاءات تعكس المستخدم الجديد
            with urllib.request.urlopen(
                    f"{api_base}/api/stats", timeout=10) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
            assert "total_users" in stats
        finally:
            api_srv.shutdown()
            api_srv.server_close()

        # 4) رد النظام على /start لم يلمس الشبكة: كل الإرسال مسجّل محلياً
        assert sent, "يجب أن يرد النظام على /start (طبقات موحدة) دون شبكة"
    finally:
        server.stop()


def test_rejected_without_secret(env):
    """المسار الكامل يرفض حتى البرنامج الصحيح بلا سر — حماية فعالة."""
    from webhook_server import WebhookServer
    import database
    import api_server

    bot, _sent = _make_bot()
    server = WebhookServer(host="127.0.0.1", port=0, secret=SECRET)
    try:
        server.register(BOT_ID, bot)
        server.start()
        url = f"http://127.0.0.1:{server.actual_port}" \
              f"{server.webhook_path(BOT_ID)}"
        code, _ = _post(url, _start_update(), secret="wrong-secret")
        assert code == 401
        # لم يسجل المستخدم في قاعدة البيانات
        db = database.get_db()
        assert db.get_user_count(BOT_ID) == 0
    finally:
        server.stop()
