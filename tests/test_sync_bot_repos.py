"""
tests/test_sync_bot_repos.py — اختبارات دالة بناء محتوى مستودع البوت (بلا شبكة)
"""
import sys
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "sync_bot_repos", ROOT / "tools" / "sync_bot_repos.py")
sync_bot_repos = importlib.util.module_from_spec(_spec)
sys.modules["sync_bot_repos"] = sync_bot_repos
_spec.loader.exec_module(sync_bot_repos)


def _make_webroot(tmp_path: Path, bot_id: str = "demo") -> Path:
    webroot = tmp_path / "webroot"
    page = webroot / bot_id
    page.mkdir(parents=True)
    (page / "index.html").write_text(
        '<head><meta property="og:url" '
        f'content="https://someone.github.io/Boda_Bot/{bot_id}/"></head>'
        '<link href="../data/style-x.css">', encoding="utf-8")
    (webroot / "data").mkdir()
    (webroot / "data" / "catalog.json").write_text("[]", encoding="utf-8")
    (webroot / "data" / "stats.json").write_text("{}", encoding="utf-8")
    return webroot


def test_build_repo_content_rewrites_paths_and_og(tmp_path):
    """المسارات النسبية تصبح ./data و og:url يشير لمستودع البوت المستقل"""
    webroot = _make_webroot(tmp_path)
    bot = {"id": "demo", "name": "عرض", "username": "@DemoBot",
           "emoji": "🧪", "description": "تجربة"}
    dest = tmp_path / "staging"

    info = sync_bot_repos.build_repo_content(
        bot, webroot, dest,
        site="https://someone.github.io", owner="someone")

    html = (dest / "index.html").read_text(encoding="utf-8")
    assert "./data/" in html            # استُبدل ../data/
    assert "../data/" not in html
    assert "boda-bot-demo/" in html     # og:url أُعيد توجيهه
    assert "Boda_Bot/demo/" not in html
    assert "demo" == info["name"].replace("boda-bot-", "")

    assert (dest / ".nojekyll").exists()
    readme = (dest / "README.md").read_text(encoding="utf-8")
    assert "someone.github.io/boda-bot-demo/" in readme
    assert "t.me/DemoBot" in readme
    assert (dest / "data" / "catalog.json").exists()
    assert (dest / "data" / "stats.json").exists()


def test_build_repo_content_missing_stats_is_tolerated(tmp_path):
    """غياب stats.json لا يكسر البناء"""
    webroot = _make_webroot(tmp_path)
    (webroot / "data" / "stats.json").unlink()
    bot = {"id": "demo", "name": "عرض", "username": "@DemoBot"}
    dest = tmp_path / "staging"

    sync_bot_repos.build_repo_content(
        bot, webroot, dest, site="https://someone.github.io", owner="someone")

    assert (dest / "index.html").exists()
    assert (dest / "data" / "catalog.json").exists()
    assert not (dest / "data" / "stats.json").exists()
