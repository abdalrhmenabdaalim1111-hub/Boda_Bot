"""
tests/test_growth_engine.py — اختبارات محرك النمو ونظام التعيين الذكي للشبكة
"""
import pytest
import json
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "Bots_Folder"))

import growth_engine
from growth_engine import GrowthEngine

# بول بوتات ثابت للاختبار (10 بوتات + المتجر)
POOL = [
    {"id": "store", "name": "متجر بودا", "username": "@BodaStoreeBot", "url": "https://t.me/BodaStoreeBot"},
    {"id": "b1", "name": "بوت 1", "username": "@B1", "url": "https://t.me/B1"},
    {"id": "b2", "name": "بوت 2", "username": "@B2", "url": "https://t.me/B2"},
    {"id": "b3", "name": "بوت 3", "username": "@B3", "url": "https://t.me/B3"},
    {"id": "b4", "name": "بوت 4", "username": "@B4", "url": "https://t.me/B4"},
    {"id": "b5", "name": "بوت 5", "username": "@B5", "url": "https://t.me/B5"},
    {"id": "b6", "name": "بوت 6", "username": "@B6", "url": "https://t.me/B6"},
    {"id": "b7", "name": "بوت 7", "username": "@B7", "url": "https://t.me/B7"},
    {"id": "b8", "name": "بوت 8", "username": "@B8", "url": "https://t.me/B8"},
    {"id": "b9", "name": "بوت 9", "username": "@B9", "url": "https://t.me/B9"},
]


class FakeDB:
    """قاعدة بيانات وهمية بلا شبكة — تحاكي واجهة database.BodaDatabase"""

    def __init__(self, started=None, blocked=None, counts=None):
        self.activations = {}          # user_id -> iso timestamp
        self.assignments = {}          # user_id -> [bot_id]
        self.started = started or {}   # (bot_id, user_id) -> True
        self.blocked = set(blocked or [])
        self.counts = counts or {}

    def is_network_activated(self, uid):
        return self.activations.get(uid) is not None

    def set_network_activated(self, uid, val=True):
        self.activations[uid] = datetime.now().isoformat() if val else None

    def get_network_activation_time(self, uid):
        return self.activations.get(uid)

    def get_network_assignments(self, uid):
        return self.assignments.get(uid, [])

    def set_network_assignments(self, uid, ids):
        self.assignments[uid] = list(ids)

    def clear_network_assignments(self, uid):
        self.assignments.pop(uid, None)

    def has_user_started(self, bot_id, uid):
        return (bot_id, uid) in self.started

    def get_bot_user_counts(self):
        return dict(self.counts)

    def get_blocked_bot_ids(self, uid):
        return [b for (b, u) in self.blocked if u == uid]

    def mark_user_blocked(self, bot_name, uid):
        self.blocked.add((bot_name, uid))


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """محرك بقاعدة وهمية وبول بوتات ثابت — بلا اتصال شبكة"""
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({
        "assignment_size": 5,
        "activation_ttl_days": 7,
        "fixed_bot_ids": ["store"],
        "balance": True,
    })
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())
    fake = FakeDB()
    monkeypatch.setattr(growth_engine, "_get_db", lambda: fake)
    return eng, fake


# ── التعيين الذكي ─────────────────────────────────────────────────────────────

def test_assignment_size_and_current_bot_included(engine):
    eng, db = engine
    a = eng.get_or_create_assignment(101, current_bot="b3")
    assert len(a) == 5
    assert "b3" in a                           # البوت الحالي مشمول الآن — المستخدم موجود فيه
    assert "store" in a                        # المتجر ثابت دائماً
    assert len(set(a)) == 5                    # لا تكرار

    # التعيين محفوظ ويُعاد استخدامه
    assert eng.get_or_create_assignment(101) == a


def test_assignment_varies_between_users(engine):
    eng, db = engine
    sets = {tuple(eng.get_or_create_assignment(u, "x")) for u in range(200, 210)}
    # 10 مستخدمين من بول 10 بوتات — النظام العشوائي يجب أن يعطي تشكيلات مختلفة
    assert len(sets) > 1


def test_assignment_balance_prefers_low_counts(engine):
    eng, db = engine
    # b1 عنده 100 مستخدم والباقي صفر — يجب ألا يُختار ب1 تقريباً أبداً
    db.counts = {"b1": 100}
    picks = [eng.get_or_create_assignment(u, "x") for u in range(300, 310)]
    assert all("b1" not in p for p in picks)


# ── بوابة التفعيل والتحقق الحقيقي ─────────────────────────────────────────────

def test_new_user_gets_gate(engine):
    eng, db = engine
    allowed, text, kb = eng.check_network_activation(MagicMock(), 401, current_bot="b2")
    assert allowed is False
    assert "تفعيل الحساب" in text
    assert kb is not None


def test_verify_blocks_until_all_started(engine):
    eng, db = engine
    uid = 500
    assignment = eng.get_or_create_assignment(uid, "x")
    # لم يشترك بعد في شيء
    ok, missing = eng.verify_activation(uid, "x")
    assert ok is False
    assert len(missing) == 5

    # اشترك في الكل
    for bid in assignment:
        db.started[(bid, uid)] = True
    ok, missing = eng.verify_activation(uid, "x")
    assert ok is True
    assert missing == []
    assert db.is_network_activated(uid)


def test_activation_ttl_expiry(engine):
    eng, db = engine
    uid = 600
    assignment = eng.get_or_create_assignment(uid, "x")
    for bid in assignment:
        db.started[(bid, uid)] = True
    eng.verify_activation(uid, "x")
    assert db.is_network_activated(uid)

    # تقديم الزمن 8 أيام → تجديد صامت (ما زال مشتركاً)
    db.activations[uid] = (datetime.now() - timedelta(days=8)).isoformat()
    eng._activation_cache.clear()  # محاكاة انتهاء كاش الذاكرة أيضاً
    allowed, text, kb = eng.check_network_activation(MagicMock(), uid, "x")
    assert allowed is True
    assert text is None
    # وتجديد الطابع الزمني
    assert (datetime.now() - datetime.fromisoformat(db.activations[uid])).days < 1


def test_unsubscribe_detected_and_bot_replaced(engine):
    eng, db = engine
    uid = 700
    assignment = eng.get_or_create_assignment(uid, "x")
    for bid in assignment:
        db.started[(bid, uid)] = True
    eng.verify_activation(uid, "x")
    assert db.is_network_activated(uid)

    # ألغى الاشتراك: حظر بوت من الخمسة + تقديم الزمن
    victim = [b for b in assignment if b != "store"][0]
    db.blocked.add((victim, uid))
    db.activations[uid] = (datetime.now() - timedelta(days=8)).isoformat()
    eng._activation_cache.clear()  # محاكاة انتهاء كاش الذاكرة أيضاً

    allowed, text, kb = eng.check_network_activation(MagicMock(), uid, "x")
    assert allowed is False
    assert "لم تعد مشتركاً" in text
    # المحظور استُبدل بمساويه ولم يبقَ في التعيين
    new_assignment = db.get_network_assignments(uid)
    assert victim not in new_assignment
    assert len(new_assignment) == 5
    assert "store" in new_assignment


# ── الإحالات والمتجر ──────────────────────────────────────────────────────────

def test_referral_link_generation(engine):
    eng, _ = engine
    link = eng.get_referral_link("@VidLoadXBot", 12345)
    assert link == "https://t.me/VidLoadXBot?start=ref_12345"

    share_url = eng.get_share_url("@VidLoadXBot", 12345, "تحميل الفيديوهات")
    assert "t.me/share/url" in share_url
    assert "ref_12345" in share_url


def test_store_button_and_card(engine):
    eng, _ = engine
    btn = eng.get_store_button()
    assert btn is not None
    assert "متجر التطبيقات" in btn.text
    assert "https://t.me/BodaStoreeBot" in btn.url

    card = eng.get_store_card_text()
    assert "Boda Apps Store" in card


# ── تغطية الفروع المفقودة ────────────────────────────────────────────────────────

def test_load_registry_pool_empty_fallback(tmp_path, monkeypatch):
    """عند فشل قراءة الريجستري → يستخدم required_network_bots من الإعدادات"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({
        "assignment_size": 5,
        "activation_ttl_days": 7,
        "fixed_bot_ids": ["store"],
        "balance": True,
        "required_network_bots": [
            {"id": "fallback1", "name": "Fallback 1", "username": "@F1", "url": "https://t.me/F1"},
            {"id": "fallback2", "name": "Fallback 2", "username": "@F2", "url": "https://t.me/F2"},
        ]
    })
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    eng._registry_cache = (None, 0)
    monkeypatch.setattr(growth_engine, "REGISTRY_FILE", tmp_path / "nonexistent.json")

    pool = eng._load_registry_pool()
    assert len(pool) == 2
    assert pool[0]["id"] == "fallback1"
    assert pool[1]["id"] == "fallback2"


def test_load_registry_pool_cache(tmp_path, monkeypatch):
    """الكاش يعمل لمدة 60 ثانية"""
    import growth_engine
    import time
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"assignment_size": 5, "fixed_bot_ids": ["store"], "balance": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    # أول قراءة تملأ الكاش
    pool1 = eng._load_registry_pool()
    # تعديل الكاش يدوياً
    eng._registry_cache = ([{"id": "cached"}], time.time())
    pool2 = eng._load_registry_pool()
    assert pool2 == [{"id": "cached"}]


def test_balanced_pick_no_balance(tmp_path, monkeypatch):
    """عند balance=False → ترتيب عشوائي فقط"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"assignment_size": 5, "fixed_bot_ids": ["store"], "balance": False})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    fake = FakeDB()
    monkeypatch.setattr(growth_engine, "_get_db", lambda: fake)

    # مع balance=False يتم shuffle فقط
    candidates = ["b1", "b2", "b3", "b4", "b5"]
    # لا يمكن اختبار العشوائية بسهولة لكن نتأكد أن الدالة تعمل
    result = eng._balanced_pick(candidates[:])
    assert set(result) == set(candidates)


def test_get_or_create_assignment_no_db(tmp_path, monkeypatch):
    """عند عدم وجود DB → يعيد التعيين دون حفظ"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"assignment_size": 5, "fixed_bot_ids": ["store"], "balance": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())
    monkeypatch.setattr(growth_engine, "_get_db", lambda: None)

    assignment = eng.get_or_create_assignment(999, current_bot="b3")
    assert len(assignment) == 5
    assert "store" in assignment
    assert "b3" in assignment


def test_is_expired_none_and_invalid(tmp_path):
    """_is_expired مع None أو تنسيق غير صالح → True"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"activation_ttl_days": 7})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    assert eng._is_expired(None) is True
    assert eng._is_expired("invalid-date") is True
    assert eng._is_expired("not-a-date") is True


def test_cache_allow(tmp_path):
    """_cache_allow يضبط الكاش بشكل صحيح"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"activation_ttl_days": 7})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    eng._cache_allow(123, days=1.0)
    assert 123 in eng._activation_cache
    assert eng._activation_cache[123] > time.time()


def test_check_network_activation_disabled(tmp_path, monkeypatch):
    """معطل كلياً → السماح"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"enabled": False, "require_5_bots_activation": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    mock_bot = MagicMock()
    allowed, text, kb = eng.check_network_activation(mock_bot, 123, "currency")
    assert allowed is True
    assert text is None
    assert kb is None


def test_check_network_activation_not_require_5(tmp_path, monkeypatch):
    """require_5_bots_activation=False → السماح"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"enabled": True, "require_5_bots_activation": False})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    mock_bot = MagicMock()
    allowed, text, kb = eng.check_network_activation(mock_bot, 123, "currency")
    assert allowed is True
    assert text is None
    assert kb is None


def test_check_network_activation_no_db(tmp_path, monkeypatch):
    """بدون DB → السماح (fail-open)"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"enabled": True, "require_5_bots_activation": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    monkeypatch.setattr(growth_engine, "_get_db", lambda: None)

    mock_bot = MagicMock()
    allowed, text, kb = eng.check_network_activation(mock_bot, 123, "currency")
    assert allowed is True
    assert text is None
    assert kb is None


def test_check_network_activation_ttl_renewal(tmp_path, monkeypatch):
    """TTL صالح → تجديد صامت للطابع الزمني"""
    import growth_engine
    from database import BodaDatabase
    import time

    # استخدام DB حقيقي مؤقت
    db_file = tmp_path / "test.db"
    db = BodaDatabase(str(db_file))
    BodaDatabase._instance = db

    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"activation_ttl_days": 7, "fixed_bot_ids": ["store"], "balance": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], time.time())
    monkeypatch.setattr(growth_engine, "_get_db", lambda: db)

    uid = 800
    assignment = eng.get_or_create_assignment(uid, "x")
    for bid in assignment:
        db.track_user(bid, uid, "Test", "test")
    eng.verify_activation(uid, "x")

    # تفعيل حديث
    mock_bot = MagicMock()
    allowed, text, kb = eng.check_network_activation(mock_bot, uid, "x")
    assert allowed is True
    assert text is None


def test_build_gate_text_modes(tmp_path):
    """_build_gate_text يولد نصوص صحيحة للأنماط الثلاثة"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"fixed_bot_ids": ["store"], "balance": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    bot_ids = ["store", "b1", "b2"]
    text_new = eng._build_gate_text(bot_ids, mode="new")
    assert "تفعيل الحساب" in text_new
    assert "مرحباً بك" in text_new

    text_missing = eng._build_gate_text(bot_ids, mode="missing")
    assert "باقي خطوة واحدة" in text_missing

    text_recheck = eng._build_gate_text(bot_ids, mode="recheck")
    assert "تم إيقاف تفعيلك" in text_recheck
    assert "لم تعد مشتركاً" in text_recheck


def test_build_activation_keyboard(tmp_path):
    """_build_activation_keyboard يبني لوحة مفاتيح صحيحة"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"fixed_bot_ids": ["store"], "balance": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    bots = [{"id": "store", "name": "متجر", "username": "@Store", "url": "https://t.me/Store"},
            {"id": "b1", "name": "بوت 1", "username": "@B1", "url": "https://t.me/B1"}]
    kb = eng._build_activation_keyboard(bots)

    # التحقق من وجود الأزرار (keyboard هو list من lists)
    assert hasattr(kb, "keyboard")
    # زر لكل بوت + زر التحقق
    # keyboard هو list من rows، كل row يحتوي على زر واحد (row_width=1)
    assert len(kb.keyboard) == 3
    # أول زرين للبوتات
    assert "متجر" in kb.keyboard[0][0].text
    assert "بوت 1" in kb.keyboard[1][0].text
    # الزر الأخير للتحقق
    assert "تحقق من التفعيل" in kb.keyboard[2][0].text


def test_verify_activation_no_db(tmp_path, monkeypatch):
    """بدون DB → السماح (fail-open)"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"enabled": True, "require_5_bots_activation": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    monkeypatch.setattr(growth_engine, "_get_db", lambda: None)

    ok, missing = eng.verify_activation(123, "currency")
    assert ok is True
    assert missing == []


def test_get_store_button_custom_url(tmp_path):
    """get_store_button يستخدم رابط مخصص من الإعدادات"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"store_bot_url": "https://t.me/CustomStore"})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    btn = eng.get_store_button()
    assert btn.url == "https://t.me/CustomStore"


def test_get_store_card_text_content(tmp_path):
    """get_store_card_text يحتوي العناصر المطلوبة"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    card = eng.get_store_card_text()
    assert "Boda Apps Store" in card
    assert "30+ بوت" in card
    assert "أدوات" in card
    assert "تحميل" in card
    assert "تصميم" in card
    assert "ترجمة" in card
    assert "صحة" in card


def test_referral_and_share_urls(tmp_path):
    """get_referral_link و get_share_url يولدان روابط صحيحة"""
    import growth_engine
    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    link = eng.get_referral_link("@TestBot", 12345)
    assert link == "https://t.me/TestBot?start=ref_12345"

    share = eng.get_share_url("@TestBot", 12345, "Test Bot")
    assert "t.me/share/url" in share
    assert "ref_12345" in share
    # الـ bot title يتم ترميزه في URL
    assert "Test%20Bot" in share or "Test+Bot" in share


def test_referral_stats_and_record(tmp_path, monkeypatch):
    """إحصائيات الإحالات وتسجيلها"""
    import growth_engine
    from database import BodaDatabase
    db_file = tmp_path / "test.db"
    db = BodaDatabase(str(db_file))
    BodaDatabase._instance = db
    monkeypatch.setattr(growth_engine, "_get_db", lambda: db)

    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"viral_rewards": {"required_invites_for_vip": 3}})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    stats = eng.get_referral_stats(111, "testbot")
    assert stats["invites"] == 0
    assert stats["target"] == 3
    assert stats["is_vip"] is False
    assert stats["remaining"] == 3

    # تسجيل إحالة
    result = eng.record_referral(111, 222, "testbot")
    assert result is True

    stats = eng.get_referral_stats(111, "testbot")
    assert stats["invites"] == 1
    assert stats["remaining"] == 2

    # لا يمكن إحالة نفس الشخص مرتين
    result = eng.record_referral(111, 222, "testbot")
    assert result is False


def test_attach_growth_engine_activation_gate(tmp_path, monkeypatch):
    """attach_growth_engine يعترض الرسائل ويفحص التفعيل"""
    import growth_engine
    from database import BodaDatabase

    db_file = tmp_path / "test.db"
    db = BodaDatabase(str(db_file))
    BodaDatabase._instance = db
    monkeypatch.setattr(growth_engine, "_get_db", lambda: db)

    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"enabled": True, "require_5_bots_activation": True,
                "fixed_bot_ids": ["store"], "balance": True, "activation_ttl_days": 7})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    # محاكاة bot
    mock_bot = MagicMock()
    mock_bot.get_me.return_value = MagicMock(username="testbot")
    original_send = MagicMock()
    mock_bot.send_message = original_send
    mock_bot.process_new_messages = MagicMock()

    growth_engine.attach_growth_engine(mock_bot, "testbot")

    # إنشاء رسالة وهمية لمستخدم جديد
    msg = MagicMock()
    msg.chat.type = "private"
    msg.chat.id = 99999
    msg.from_user.id = 99999
    msg.from_user.username = "testuser"
    msg.from_user.full_name = "Test User"
    msg.text = "Hello"

    # يجب أن تمنع المعالجة وتُرسل بوابة التفعيل
    mock_bot.process_new_messages([msg])

    # التحقق من أن send_message دُعي مع بوابة التفعيل
    original_send.assert_called()
    call_args = original_send.call_args
    sent_text = call_args[1].get("text") if "text" in call_args[1] else call_args[0][1]
    assert "تفعيل الحساب" in sent_text


def test_attach_growth_engine_verify_callback(tmp_path, monkeypatch):
    """attach_growth_engine يسجل callback للتحقق"""
    import growth_engine
    from database import BodaDatabase

    db_file = tmp_path / "test.db"
    db = BodaDatabase(str(db_file))
    BodaDatabase._instance = db
    monkeypatch.setattr(growth_engine, "_get_db", lambda: db)

    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"enabled": True, "require_5_bots_activation": True,
                "fixed_bot_ids": ["store"], "balance": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    mock_bot = MagicMock()
    mock_bot.get_me.return_value = MagicMock(username="testbot")
    mock_bot.callback_query_handler = MagicMock()
    mock_bot.message_handler = MagicMock()
    mock_bot.send_message = MagicMock()
    mock_bot.answer_callback_query = MagicMock()

    growth_engine.attach_growth_engine(mock_bot, "testbot")

    # التحقق من تسجيل callback_query_handler
    assert mock_bot.callback_query_handler.called
    # التحقق من تسجيل message_handler للأوامر
    assert mock_bot.message_handler.call_count >= 2  # store + ref


def test_attach_growth_engine_blocked_detection(tmp_path, monkeypatch):
    """attach_growth_engine يكتشف الحظر 403 ويسجله"""
    import growth_engine
    from database import BodaDatabase
    from telebot.apihelper import ApiTelegramException

    db_file = tmp_path / "test.db"
    db = BodaDatabase(str(db_file))
    BodaDatabase._instance = db
    monkeypatch.setattr(growth_engine, "_get_db", lambda: db)

    cfg_file = tmp_path / "network_config.json"
    cfg = dict(growth_engine.DEFAULT_NETWORK_CONFIG)
    cfg.update({"enabled": True})
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    eng = growth_engine.GrowthEngine(config_file=cfg_file)

    mock_bot = MagicMock()
    mock_bot.get_me.return_value = MagicMock(username="testbot")
    original_send = MagicMock()
    mock_bot.send_message = original_send

    growth_engine.attach_growth_engine(mock_bot, "testbot")

    # محاكاة خطأ 403 - ApiTelegramException يحتاج result_json بـ error_code و description
    error = ApiTelegramException("Forbidden", 403, {"error_code": 403, "description": "bot was blocked by the user"})
    original_send.side_effect = error

    try:
        mock_bot.send_message(12345, "Test")
    except ApiTelegramException:
        pass

    # التحقق من تسجيل الحظر
    assert db.get_blocked_bot_ids(12345) == ["testbot"]


# إضافة import time في بداية الملف إذا لم يكن موجوداً
import time

# ── تغطية إضافية للأفرع غير المختبرة ────────────────────────────────────────

def test_get_db_exception_handling():
    """اختبار معالجة الاستثناء في _get_db"""
    # تحديث الوحدة بعد الباتش
    import growth_engine
    with patch("database.get_db", side_effect=Exception("DB error")):
        # إعادة استيراد _get_db لتطبيق الباتش
        from importlib import reload
        reload(growth_engine)
        result = growth_engine._get_db()
        assert result is None


def test_load_config_exception_handling(tmp_path):
    """اختبار معالجة خطأ قراءة ملف الإعدادات"""
    cfg_file = tmp_path / "bad_config.json"
    cfg_file.write_text("invalid json", encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    # يجب أن يحمل الإعدادات الافتراضية عند الفشل
    assert eng.config["assignment_size"] == 5
    assert eng.config["fixed_bot_ids"] == ["store"]


def test_load_config_file_not_exists_creates_default(tmp_path):
    """اختبار إنشاء ملف إعدادات افتراضي عند عدم وجوده"""
    cfg_file = tmp_path / "new_config.json"
    # لا ننشئ الملف

    eng = GrowthEngine(config_file=cfg_file)
    # يجب أن يستخدم الإعدادات الافتراضية
    assert eng.config["assignment_size"] == 5


def test_load_registry_pool_exception_fallback(tmp_path):
    """اختبار fallback عند فشل قراءة الريجستري"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"assignment_size": 5, "fixed_bot_ids": ["store"]}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    # محاكاة فشل قراءة الريجستري
    with patch("pathlib.Path.read_text", side_effect=Exception("File error")):
        pool = eng._load_registry_pool()
        # يجب أن يرجع required_network_bots ك fallback
        assert len(pool) > 0
        assert any(b["id"] == "store" for b in pool)


def test_bot_meta_fallback(tmp_path):
    """اختبار fallback في _bot_meta للبوت غير الموجود"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"assignment_size": 5}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([], 0)  # بول فارغ

    meta = eng._bot_meta("nonexistent_bot")
    assert meta["id"] == "nonexistent_bot"
    assert meta["name"] == "nonexistent_bot"
    assert meta["username"] == ""
    assert meta["url"] == ""


def test_balanced_pick_no_db(tmp_path):
    """اختبار _balanced_pick عند عدم توفر DB"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"balance": True}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    with patch("growth_engine._get_db", return_value=None):
        candidates = ["b1", "b2", "b3"]
        result = eng._balanced_pick(candidates)
        # يجب أن يعيد القائمة مرتبة عشوائياً (بدون ترتيب بالعدادات)
        assert set(result) == set(candidates)


def test_balanced_pick_balance_false(tmp_path):
    """اختبار _balanced_pick مع balance=false"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"balance": False}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    candidates = ["b1", "b2", "b3"]
    result = eng._balanced_pick(candidates)
    # يجب أن تكون عشوائية فقط
    assert set(result) == set(candidates)


def test_check_network_activation_ttl_renewal_exception(tmp_path):
    """اختبار تجديد TTL مع استثناء في حساب الوقت المتبقي"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"activation_ttl_days": 7}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    db = FakeDB()
    # تفعيل سابق ولكن الوقت المتبقي يسبب استثناء
    db.activations[100] = "2020-01-01T00:00:00"  # تاريخ صحيح لكن قديم
    # جعل is_network_activated يعيد True و get_network_activation_time يعيد التاريخ

    with patch("growth_engine._get_db", return_value=db):
        allowed, text, kb = eng.check_network_activation(MagicMock(), 100, current_bot="b1")
        # يجب أن يمر بالتجديد (التاريخ منتهي الصلاحية لكن المستخدم ما زال مشتركاً)
        # تعيين محفوظ غير موجود، current_bot = b1
        # البوت الحالي b1 موجود في التعيين → سيحاول إنشاء تعيين جديد
        assert allowed is False  # بوابة مطلوبة لأن لا يوجد تعيين محفوظ


def test_check_network_activation_recheck_all_started_renewal(tmp_path):
    """اختبار إعادة التحقق - المستخدم ما زال مشتركاً في الكل → تجديد صامت"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"activation_ttl_days": 7}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    db = FakeDB(
        started={("store", 200), ("b1", 200), ("b2", 200), ("b3", 200), ("b4", 200)},
        counts={"store": 10, "b1": 5, "b2": 3}
    )
    # تعيين سابق
    db.assignments[200] = ["store", "b1", "b2", "b3", "b4"]
    # تفعيل سابق منتهي الصلاحية
    db.activations[200] = "2020-01-01T00:00:00"

    with patch("growth_engine._get_db", return_value=db):
        allowed, text, kb = eng.check_network_activation(MagicMock(), 200, current_bot="b1")
        assert allowed is True
        assert db.is_network_activated(200) is True


def test_verify_activation_no_db(tmp_path):
    """اختبار verify_activation عند عدم توفر DB"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    with patch("growth_engine._get_db", return_value=None):
        ok, missing = eng.verify_activation(100, "b1")
        # فشل مفتوح - يسمح بالتفعيل
        assert ok is True
        assert missing == []


def test_verify_activation_blocked_bots(tmp_path):
    """اختبار verify_activation مع بوتات محظورة"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    db = FakeDB(
        started={("store", 300), ("b1", 300)},
        blocked={("b2", 300)},
        counts={}
    )
    db.assignments[300] = ["store", "b1", "b2", "b3", "b4"]

    with patch("growth_engine._get_db", return_value=db):
        ok, missing = eng.verify_activation(300, "b1")
        assert ok is False
        # يجب أن يشمل المفقودين البوت المحظور b2
        missing_ids = [m["id"] for m in missing]
        assert "b2" in missing_ids


def test_get_store_button_custom_url(tmp_path):
    """اختبار get_store_button مع URL مخصص"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"store_bot_url": "https://t.me/CustomStore"}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    btn = eng.get_store_button()
    assert btn.url == "https://t.me/CustomStore"
    assert "متجر التطبيقات" in btn.text


def test_get_store_card_text_content(tmp_path):
    """اختبار محتوى بطاقة المتجر"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    text = eng.get_store_card_text()
    assert "متجر تطبيقات بودا" in text
    assert "30+ بوت" in text
    assert "أدوات" in text
    assert "تحميل" in text


def test_referral_and_share_urls(tmp_path):
    """اختبار توليد روابط الإحالة والمشاركة"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    ref_link = eng.get_referral_link("@TestBot", 12345)
    assert "t.me/TestBot" in ref_link
    assert "start=ref_12345" in ref_link

    share_url = eng.get_share_url("@TestBot", 12345, "Test Bot")
    assert "t.me/share/url" in share_url
    assert "ref_12345" in share_url


def test_referral_stats_and_record(tmp_path):
    """اختبار إحصائيات الإحالة وتسجيلها"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"viral_rewards": {"required_invites_for_vip": 3}}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    with patch("growth_engine._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.get_referral_count.return_value = 2
        mock_db.record_referral.return_value = True
        mock_get_db.return_value = mock_db

        stats = eng.get_referral_stats(100, "testbot")
        assert stats["invites"] == 2
        assert stats["target"] == 3
        assert stats["is_vip"] is False
        assert stats["remaining"] == 1

        result = eng.record_referral(100, 200, "testbot")
        assert result is True
        mock_db.record_referral.assert_called_once_with(100, 200, "testbot")


def test_attach_growth_engine_process_new_messages_exception(tmp_path):
    """اختبار attach_growth_engine مع استثناء في process_new_messages"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    import growth_engine
    growth_engine._growth_engine_instance = eng

    mock_bot = MagicMock()
    mock_bot.get_me.return_value = MagicMock(username="TestBot")

    # process_new_messages يطرح استثناء
    def bad_process_new_messages(messages):
        raise Exception("Processing error")

    mock_bot.process_new_messages = bad_process_new_messages

    # لا يجب أن يطرح استثناء
    from growth_engine import attach_growth_engine
    attach_growth_engine(mock_bot, "testbot")


def test_attach_growth_engine_callback_query_handler_exception(tmp_path):
    """اختبار attach_growth_engine مع استثناء في callback_query_handler"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    import growth_engine
    growth_engine._growth_engine_instance = eng

    mock_bot = MagicMock()
    mock_bot.get_me.return_value = MagicMock(username="TestBot")

    # callback_query_handler يطرح استثناء
    def bad_callback_handler(func):
        raise Exception("Handler error")
    mock_bot.callback_query_handler = bad_callback_handler

    from growth_engine import attach_growth_engine
    attach_growth_engine(mock_bot, "testbot")


def test_attach_growth_engine_message_handler_exception(tmp_path):
    """اختبار attach_growth_engine مع استثناء في message_handler"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    import growth_engine
    growth_engine._growth_engine_instance = eng

    mock_bot = MagicMock()
    mock_bot.get_me.return_value = MagicMock(username="TestBot")

    # message_handler يطرح استثناء
    def bad_message_handler(commands, func):
        raise Exception("Handler error")
    mock_bot.message_handler = bad_message_handler

    from growth_engine import attach_growth_engine
    attach_growth_engine(mock_bot, "testbot")


def test_attach_growth_engine_send_message_blocked_detection(tmp_path):
    """اختبار رصد الحظر 403 في send_message"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    import growth_engine
    growth_engine._growth_engine_instance = eng

    mock_bot = MagicMock()
    mock_bot.get_me.return_value = MagicMock(username="TestBot")

    from telebot.apihelper import ApiTelegramException

    # محاكاة استثناء 403 - ApiTelegramException يحتاج result_json
    def failing_send(chat_id, *args, **kwargs):
        raise ApiTelegramException("Forbidden", 403, {"error_code": 403, "description": "bot was blocked by the user"})

    mock_bot.send_message = failing_send

    from growth_engine import attach_growth_engine
    attach_growth_engine(mock_bot, "testbot")

    # اختبار استدعاء الدالة المغلف
    with patch("growth_engine._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        try:
            mock_bot.send_message(123, "test")
        except ApiTelegramException:
            pass

        # يجب أن يكون تم تسجيل الحظر
        mock_db.mark_user_blocked.assert_called_with("testbot", 123)


def test_attach_growth_engine_send_message_other_exception(tmp_path):
    """اختبار send_message مع استثناء غير 403"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"enabled": True}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    import growth_engine
    growth_engine._growth_engine_instance = eng

    mock_bot = MagicMock()
    mock_bot.get_me.return_value = MagicMock(username="TestBot")

    from telebot.apihelper import ApiTelegramException

    # محاكاة استثناء 500 (ليس 403)
    def failing_send(chat_id, *args, **kwargs):
        raise ApiTelegramException("Internal Server Error", 500, {"error_code": 500, "description": "Internal Server Error"})

    mock_bot.send_message = failing_send

    from growth_engine import attach_growth_engine
    attach_growth_engine(mock_bot, "testbot")

    with patch("growth_engine._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        try:
            mock_bot.send_message(123, "test")
        except ApiTelegramException:
            pass

        # لا يجب تسجيل الحظر لخطأ 500
        mock_db.mark_user_blocked.assert_not_called()


def test_is_expired_none_and_invalid(tmp_path):
    """اختبار _is_expired مع None وتاريخ غير صالح"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"activation_ttl_days": 7}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    assert eng._is_expired(None) is True
    assert eng._is_expired("invalid-date") is True


def test_cache_allow(tmp_path):
    """اختبار _cache_allow"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"activation_ttl_days": 7}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    before = __import__("time").time()
    eng._cache_allow(100)
    after = __import__("time").time()

    cached = eng._activation_cache[100]
    assert before < cached < after + 7 * 86400 + 1


def test_check_network_activation_disabled(tmp_path):
    """اختبار check_network_activation مع تعطيل المحرك"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"enabled": False}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    allowed, text, kb = eng.check_network_activation(MagicMock(), 100)
    assert allowed is True
    assert text is None
    assert kb is None


def test_check_network_activation_not_require_5(tmp_path):
    """اختبار check_network_activation مع تعطيل شرط الـ 5 بوتات"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"enabled": True, "require_5_bots_activation": False}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    allowed, text, kb = eng.check_network_activation(MagicMock(), 100)
    assert allowed is True
    assert text is None
    assert kb is None


def test_check_network_activation_no_db(tmp_path):
    """اختبار check_network_activation بدون DB"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"enabled": True, "require_5_bots_activation": True}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    with patch("growth_engine._get_db", return_value=None):
        allowed, text, kb = eng.check_network_activation(MagicMock(), 100)
        # فشل مفتوح
        assert allowed is True


def test_build_gate_text_modes(tmp_path):
    """اختبار _build_gate_text للأوضاع المختلفة"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    # وضع new (افتراضي)
    text_new = eng._build_gate_text(["store", "b1"])
    assert "تفعيل الحساب" in text_new

    # وضع recheck
    text_recheck = eng._build_gate_text(["store", "b1"], mode="recheck")
    assert "تم إيقاف تفعيلك" in text_recheck

    # وضع missing
    text_missing = eng._build_gate_text(["store", "b1"], mode="missing")
    assert "باقي خطوة واحدة" in text_missing


def test_build_activation_keyboard(tmp_path):
    """اختبار _build_activation_keyboard"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    metas = eng._metas(["store", "b1"])
    kb = eng._build_activation_keyboard(metas)

    assert kb is not None
    assert len(kb.keyboard) >= 3  # زر لكل بوت + زر التحقق


def test_verify_activation_no_db(tmp_path):
    """اختبار verify_activation بدون DB"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    with patch("growth_engine._get_db", return_value=None):
        ok, missing = eng.verify_activation(100, "b1")
        assert ok is True
        assert missing == []


def test_get_store_button_custom_url(tmp_path):
    """اختبار get_store_button مع URL مخصص"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"store_bot_url": "https://t.me/CustomStore"}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    btn = eng.get_store_button()
    assert btn.url == "https://t.me/CustomStore"
    assert "متجر التطبيقات" in btn.text


def test_get_store_card_text_content(tmp_path):
    """اختبار محتوى بطاقة المتجر"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    text = eng.get_store_card_text()
    assert "متجر تطبيقات بودا" in text
    assert "30+ بوت" in text


def test_referral_and_share_urls(tmp_path):
    """اختبار توليد روابط الإحالة والمشاركة"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    ref_link = eng.get_referral_link("@TestBot", 12345)
    assert "t.me/TestBot" in ref_link
    assert "start=ref_12345" in ref_link

    share_url = eng.get_share_url("@TestBot", 12345, "Test Bot")
    assert "t.me/share/url" in share_url
    assert "ref_12345" in share_url


def test_referral_stats_and_record(tmp_path):
    """اختبار إحصائيات الإحالة وتسجيلها"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"viral_rewards": {"required_invites_for_vip": 3}}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    with patch("growth_engine._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.get_referral_count.return_value = 2
        mock_db.record_referral.return_value = True
        mock_get_db.return_value = mock_db

        stats = eng.get_referral_stats(100, "testbot")
        assert stats["invites"] == 2
        assert stats["target"] == 3
        assert stats["is_vip"] is False
        assert stats["remaining"] == 1

        result = eng.record_referral(100, 200, "testbot")
        assert result is True
        mock_db.record_referral.assert_called_once_with(100, 200, "testbot")


def test_load_registry_pool_cache(tmp_path):
    """اختبار كاش _load_registry_pool"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    # تعيين كاش يدوي
    cached_pool = [{"id": "cached", "name": "Cached Bot", "username": "@Cached", "url": "https://t.me/Cached"}]
    eng._registry_cache = (cached_pool, __import__("time").time())

    pool = eng._load_registry_pool()
    assert pool == cached_pool


def test_load_registry_pool_empty_fallback(tmp_path):
    """اختبار fallback عند فشل الريجستري"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"required_network_bots": [{"id": "fallback", "name": "Fallback Bot", "username": "@Fallback", "url": "https://t.me/Fallback"}]}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    # محاكاة فشل كامل
    with patch("growth_engine.REGISTRY_FILE") as mock_reg:
        mock_reg.read_text.side_effect = Exception("Error")

        pool = eng._load_registry_pool()
        assert len(pool) == 1
        assert pool[0]["id"] == "fallback"


def test_balanced_pick_no_balance(tmp_path):
    """اختبار _balanced_pick مع balance=false"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"balance": False}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)

    candidates = ["b1", "b2", "b3"]
    result = eng._balanced_pick(candidates)
    assert set(result) == set(candidates)


def test_get_or_create_assignment_no_db(tmp_path):
    """اختبار get_or_create_assignment بدون DB"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"assignment_size": 5, "fixed_bot_ids": ["store"], "balance": False}), encoding="utf-8")

    eng = GrowthEngine(config_file=cfg_file)
    eng._registry_cache = ([dict(b) for b in POOL], __import__("time").time())

    with patch("growth_engine._get_db", return_value=None):
        assignment = eng.get_or_create_assignment(100, "b3")
        assert len(assignment) == 5
        assert "store" in assignment
        assert "b3" in assignment


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
