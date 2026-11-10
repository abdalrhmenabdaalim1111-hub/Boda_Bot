"""
tests/test_diagnose.py — اختبارات التشخيص الذكي الشامل (dev_tools)
"""
import json
import dev_tools


class FakeDB:
    """قاعدة بيانات وهمية لاختبار التجميع دون لمس ملفات حقيقية"""

    def get_error_summary(self, days=7):
        return {
            "total_errors": 12,
            "by_type": {"AUTH_TOKEN_INVALID": 8, "NETWORK_TIMEOUT": 4},
            "by_bot": {"currency": 7, "fitcheck": 5},
        }

    def get_recent_errors(self, limit=50):
        return [
            {"fingerprint": "abc123", "bot_name": "currency"},
            {"fingerprint": "abc123", "bot_name": "currency"},
            {"fingerprint": "def456", "bot_name": "fitcheck"},
        ]

    def get_ad_summary(self):
        return {
            "total_impressions": 100, "total_clicks": 5, "overall_ctr": 5.0,
            "today_impressions": 10, "today_clicks": 1, "active_bots_count": 2,
        }

    def get_ad_stats(self):
        return [{"bot_name": "currency", "impressions": 60, "clicks": 4, "ctr_percent": 6.67}]


def _make_fake_project(tmp_path, with_beta_token=True):
    reg = [{"id": "alpha"}, {"id": "beta"}]
    (tmp_path / "bots_registry.json").write_text(json.dumps(reg), encoding="utf-8")
    env = "BOT_ALPHA_TOKEN=123456789:AAHabcdefghijk12345XY\n"
    if with_beta_token:
        env += "BOT_BETA_TOKEN=123456789:AAHabcdefghijk12345ZZ\n"
    (tmp_path / ".env").write_text(env, encoding="utf-8")
    webroot = tmp_path / "webroot"
    for bid in ("alpha", "beta"):
        (webroot / bid).mkdir(parents=True)
        (webroot / bid / "index.html").write_text("<html></html>", encoding="utf-8")


def test_collect_diagnostics_complete(tmp_path, monkeypatch):
    _make_fake_project(tmp_path)
    monkeypatch.setattr(dev_tools, "REGISTRY", tmp_path / "bots_registry.json")
    monkeypatch.setattr(dev_tools, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(dev_tools, "BASE_DIR", tmp_path)

    monetag = {"alpha": {"has_ad": True}, "beta": {"has_ad": False}}
    rep = dev_tools.collect_diagnostics(db=FakeDB(), monetag_statuses=monetag)

    assert rep["bots_total"] == 2
    assert rep["tokens_ok"] == 2
    assert rep["pages_ok"] == 2
    assert rep["ads_ready"] == 1
    assert rep["ads_total"] == 2
    assert rep["top_fingerprints"][0] == ("abc123", 2)
    assert rep["errors_summary"]["total_errors"] == 12
    assert rep["ad_summary"]["overall_ctr"] == 5.0
    assert rep["ad_top"][0]["bot_name"] == "currency"


def test_collect_diagnostics_missing_token_and_page(tmp_path, monkeypatch):
    _make_fake_project(tmp_path, with_beta_token=False)
    monkeypatch.setattr(dev_tools, "REGISTRY", tmp_path / "bots_registry.json")
    monkeypatch.setattr(dev_tools, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(dev_tools, "BASE_DIR", tmp_path)
    # احذف صفحة beta لإثبات نقص الصفحات
    (tmp_path / "webroot" / "beta" / "index.html").unlink()

    rep = dev_tools.collect_diagnostics(db=FakeDB(), monetag_statuses={})
    assert rep["tokens_ok"] == 1
    assert rep["pages_ok"] == 1
    assert rep["ads_ready"] == 0


def test_cmd_diagnose_renders_report(monkeypatch, capsys):
    fake = {
        "bots_total": 2, "tokens_ok": 1, "pages_ok": 2,
        "ads_ready": 0, "ads_total": 2,
        "errors_summary": {"total_errors": 12,
                           "by_type": {"AUTH_TOKEN_INVALID": 8, "NETWORK_TIMEOUT": 4},
                           "by_bot": {"alpha": 12}},
        "top_fingerprints": [("abc", 3)],
        "recent_errors_count": 12,
        "ad_summary": {"total_impressions": 100, "total_clicks": 5, "overall_ctr": 5.0,
                       "today_impressions": 10, "today_clicks": 1},
        "ad_top": [{"bot_name": "currency", "impressions": 60}],
    }
    monkeypatch.setattr(dev_tools, "collect_diagnostics", lambda: fake)

    code = dev_tools.cmd_diagnose()
    out = capsys.readouterr().out

    assert code == 0
    assert "التشخيص الذكي" in out
    assert "1/2" in out            # توكنات
    assert "import-tokens" in out  # توصية إضافة التوكن
    assert "tokens-verify" in out  # توصية بسبب أخطاء التوكن المسيطرة
    assert "set-ad" in out         # توصية شفرات Monetag
    assert "currency (60)" in out  # أفضل البوتات إعلانياً


def test_diagnose_real_repo_runs(capsys):
    """تشغيل التشخيص على المشروع الحقيقي — يجب ألا يتعطل أبداً"""
    code = dev_tools.cmd_diagnose()
    out = capsys.readouterr().out
    assert code == 0
    assert "بنية النظام" in out
    assert "التوصيات" in out
