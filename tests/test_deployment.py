"""
tests/test_deployment.py — اختبارات ملفات النشر الإنتاجي (Docker/Webhook/Monitoring)
تضمن ألا تعود الصورة إلى تشغيل واجهة Tkinter أو تفقد إعدادات الإنتاج.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_dockerfile_runs_headless_runner():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "server_runner.py" in text
    assert "StartManager.py" not in text
    assert "STOPSIGNAL SIGTERM" in text


def test_compose_has_production_services():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert text.count("restart: always") >= 3
    assert "server_runner.py" in text
    assert "api_server.py" in text
    assert "monitor_agent.py" in text
    assert "condition: service_healthy" in text
    assert "BODA_BOTS" in text


def test_dockerignore_hides_secrets_and_data():
    lines = [ln.strip() for ln in
             (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()]
    assert ".env" in lines
    assert "Data/" in lines
    assert "Backups/*" in lines


def test_readme_documents_production_workflow():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for keyword in ("server_runner.py", "Webhook", "UptimeRobot",
                    "monitor_agent.py", "backup-verify", "restart: always"):
        assert keyword in text


def test_webhook_server_is_importable():
    import sys
    bots_dir = str(ROOT / "Bots_Folder")
    if bots_dir not in sys.path:
        sys.path.insert(0, bots_dir)
    from webhook_server import WebhookServer
    assert hasattr(WebhookServer, "public_url")
    assert hasattr(WebhookServer, "webhook_path")
