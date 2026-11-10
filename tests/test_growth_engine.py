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

def test_assignment_size_and_current_bot_excluded(engine):
    eng, db = engine
    a = eng.get_or_create_assignment(101, current_bot="b3")
    assert len(a) == 5
    assert "b3" not in a                       # البوت الحالي مستثنى
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
