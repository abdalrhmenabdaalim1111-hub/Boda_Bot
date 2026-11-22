# -*- coding: utf-8 -*-
"""
kill_bots.py — أداة إنهاء جميع عمليات البوت العالقة فوراً
تستخدم psutil للإنهاء الفوري خلال أجزاء من الثانية دون أي تأخير
"""
import os
import sys

def kill_all_bot_processes() -> int:
    """إنهاء جميع عمليات Python التي تشغّل ملفات bot_*.py"""
    killed = 0
    my_pid = os.getpid()

    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pid = proc.info['pid']
                if pid == my_pid:
                    continue
                cmdline = " ".join(proc.info.get('cmdline') or [])
                if ("bot_" in cmdline and ".py" in cmdline) or ("server_runner.py" in cmdline):
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        # Fallback to taskkill / fuser if psutil is not available
        import subprocess
        if sys.platform == "win32":
            try:
                subprocess.run(
                    'wmic process where "CommandLine like \'%bot_%.py%\'" call terminate',
                    shell=True, capture_output=True, timeout=5
                )
            except Exception:
                pass
        else:
            try:
                subprocess.run("pkill -f 'bot_.*\\.py'", shell=True, capture_output=True, timeout=5)
            except Exception:
                pass

    if killed > 0:
        print(f"🧹 تم إنهاء {killed} عملية بوت عالقة بنجاح.")
    return killed

if __name__ == "__main__":
    count = kill_all_bot_processes()
    print(f"✅ تم فحص العمليات — انتهت {count} عملية.")
