
"""
StartManager.py — مدير تشغيل جميع البوتات
🚀 WebApp-First
@BodaStoreBot
"""
import sys
import os
import logging
import subprocess
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format="[StartManager] %(asctime)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("StartManager")

# مسار مجلد البوتات
BOTS_FOLDER = Path(__file__).parent / "Bots_Folder"

class BotManager:
    """مدير لتشغيل وإيقاف البوتات"""

    def __init__(self):
        self.bots = {}
        self.processes = {}

    def load_bots(self):
        """تحميل جميع ملفات البوتات"""
        if not BOTS_FOLDER.exists():
            log.error(f"مجلد البوتات غير موجود: {BOTS_FOLDER}")
            return False

        for bot_file in BOTS_FOLDER.glob("*.py"):
            if bot_file.name.startswith("bot_") and bot_file.name != "bot_template.py":
                bot_name = bot_file.stem.replace("bot_", "")
                self.bots[bot_name] = bot_file
                log.info(f"تم تحميل البوت: {bot_name}")

        return len(self.bots) > 0

    def start_bot(self, bot_name):
        """تشغيل بوت معين"""
        if bot_name not in self.bots:
            log.error(f"البوت غير موجود: {bot_name}")
            return False

        if bot_name in self.processes and self.processes[bot_name].poll() is None:
            log.warning(f"البوت {bot_name} يعمل بالفعل")
            return False

        try:
            process = subprocess.Popen(
                [sys.executable, str(self.bots[bot_name])],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            self.processes[bot_name] = process
            log.info(f"تم تشغيل البوت: {bot_name} (PID: {process.pid})")
            return True
        except Exception as e:
            log.error(f"فشل تشغيل البوت {bot_name}: {e}")
            return False

    def stop_bot(self, bot_name):
        """إيقاف بوت معين"""
        if bot_name not in self.processes:
            log.warning(f"البوت {bot_name} غير مشغل")
            return False

        try:
            process = self.processes[bot_name]
            process.terminate()
            process.wait(timeout=5)
            del self.processes[bot_name]
            log.info(f"تم إيقاف البوت: {bot_name}")
            return True
        except Exception as e:
            log.error(f"فشل إيقاف البوت {bot_name}: {e}")
            return False

    def start_all(self):
        """تشغيل جميع البوتات"""
        for bot_name in self.bots:
            self.start_bot(bot_name)
            time.sleep(1)  # تأخير بسيط بين تشغيل كل بوت

    def stop_all(self):
        """إيقاف جميع البوتات"""
        for bot_name in list(self.processes.keys()):
            self.stop_bot(bot_name)

    def status(self):
        """حالة جميع البوتات"""
        status = {}
        for bot_name in self.bots:
            if bot_name in self.processes:
                process = self.processes[bot_name]
                status[bot_name] = "running" if process.poll() is None else "stopped"
            else:
                status[bot_name] = "stopped"
        return status

def main():
    """الدالة الرئيسية"""
    log.info("🚀 بدء تشغيل StartManager")

    manager = BotManager()

    # تحميل البوتات
    if not manager.load_bots():
        log.error("لم يتم العثور على أي بوتات")
        return

    log.info(f"تم تحميل {len(manager.bots)} بوت")

    # تشغيل جميع البوتات
    manager.start_all()

    # عرض حالة البوتات
    while True:
        status = manager.status()
        running = sum(1 for s in status.values() if s == "running")
        log.info(f"البوتات النشطة: {running}/{len(status)}")
        time.sleep(60)  # تحديث الحالة كل دقيقة

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("تم إيقاف StartManager")
    except Exception as e:
        log.error(f"خطأ في StartManager: {e}")
        sys.exit(1)
