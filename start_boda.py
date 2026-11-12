# -*- coding: utf-8 -*-
"""
start_boda.py — المشغل الموحد لنظام بودة ولوحة التحكم (Control Center Launcher)

يقوم هذا السكريبت بـ:
1. فحص وتحرير المنفذ 8080 إذا كان مشغولاً بنسخة سابقة.
2. التأكد من وجود ملف .env وإعداده.
3. تطبيق أي ترحيلات مطلوبة لقاعدة البيانات.
4. تحديث وبناء لوحة التحكم وتطبيقات الويب المصغرة.
5. فتح لوحة التحكم تلقائياً في المتصفح الافتراضي.
6. تشغيل خادم النظام وبث السجلات ومراقبة البوتات.
"""
from __future__ import annotations

import os
import sys
import time
import socket
import shutil
import threading
import subprocess
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
os.chdir(BASE_DIR)

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def is_port_in_use(port: int = 8080, host: str = "127.0.0.1") -> bool:
    """Check if the target port is currently bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def free_port(port: int = 8080) -> None:
    """Kill any process holding the port on Windows or Unix."""
    if not is_port_in_use(port):
        return

    print(f"⚠️  المنفذ {port} مشغول حالياً، جاري تحريره...")
    if sys.platform == "win32":
        try:
            # Find PID using netstat
            output = subprocess.check_output(
                f'netstat -ano | findstr ":{port} "',
                shell=True,
                text=True,
                errors="ignore"
            )
            pids = set()
            for line in output.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[-1].isdigit():
                    pids.add(int(parts[-1]))

            my_pid = os.getpid()
            for pid in pids:
                if pid != my_pid and pid > 0:
                    subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True)
            time.sleep(1)
        except Exception:
            pass
    else:
        try:
            subprocess.run(f"fuser -k {port}/tcp", shell=True, capture_output=True)
            time.sleep(1)
        except Exception:
            pass


def ensure_env() -> None:
    """Ensure .env exists."""
    env_file = BASE_DIR / ".env"
    example_file = BASE_DIR / ".env.example"
    if not env_file.exists():
        if example_file.exists():
            print("📝 إنشاء ملف .env من النموذج .env.example...")
            shutil.copy(example_file, env_file)
        else:
            print("⚠️  تحذير: ملف .env و .env.example غير موجودين.")


def apply_migrations() -> None:
    """Run database migrations."""
    try:
        from control_center import migrations
        report = migrations.ensure_ready()
        applied = report.get("applied", [])
        if applied:
            print(f"🗄️  تم تطبيق ترحيلات قاعدة البيانات: {', '.join(applied)}")
        else:
            print("🗄️  قاعدة البيانات جاهزة ومحدثة.")
    except Exception as e:
        print(f"⚠️  تعذر فحص الترحيلات: {e}")


def build_dashboard() -> None:
    """Rebuild the dashboard HTML if generator exists."""
    generator = BASE_DIR / "tools" / "build_mini_apps.py"
    if generator.exists():
        try:
            print("🔄 جاري تحديث صفحات لوحة التحكم والتطبيقات المصغرة...")
            res = subprocess.run(
                [sys.executable, str(generator)],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if res.returncode == 0:
                print("✅ اكتمل تجهيز وتحديث لوحة التحكم بنجاح.")
            else:
                print(f"⚠️  تحذير أثناء بناء اللوحة: {res.stderr[:200]}")
        except Exception as e:
            print(f"⚠️  خطأ أثناء بناء اللوحة: {e}")


def open_browser_delayed(url: str, delay: float = 1.2) -> None:
    """Open browser after a short delay so the server has started."""
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    t = threading.Thread(target=_open, daemon=True)
    t.start()


def print_banner(url: str) -> None:
    banner = f"""
╔═══════════════════════════════════════════════════════════════════╗
║                   🤖  نظام بودة للبوتات (Boda Bot)                ║
║                     لوحة التحكم والإدارة المركزية                ║
╚═══════════════════════════════════════════════════════════════════╝

  🌐  رابط لوحة التحكم :  {url}
  📊  فحص الصحة        :  http://127.0.0.1:8080/health
  🤖  إدارة البوتات     :  تشغيل / إيقاف / توكنات / إعلانات
  
  💡 اضغط Ctrl+C في هذه النافذة لإيقاف الخادم بالكامل.
─────────────────────────────────────────────────────────────────────
"""
    print(banner)


def main():
    dashboard_url = "http://127.0.0.1:8080/dashboard"

    print("🚀 جاري تهيئة نظام بودة...")
    free_port(8080)
    ensure_env()
    apply_migrations()
    build_dashboard()

    # Schedule browser opening
    open_browser_delayed(dashboard_url, delay=1.5)
    print_banner(dashboard_url)

    # Start API server in foreground
    import api_server
    try:
        server = api_server.run_api_server(host="127.0.0.1", port=8080)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹️  تم استلام أمر الإيقاف...")
    finally:
        try:
            from control_center.api import reset_supervisor
            reset_supervisor()
        except Exception:
            pass
        print("👋 تم إيقاف نظام بودة بالكامل بنجاح.")


if __name__ == "__main__":
    main()

