import psutil
import os
from pathlib import Path

def kill_all_bot_processes():
    BASE_DIR = Path(__file__).parent.resolve()
    print(f"🧹 تنظيف العمليات التابعة لمجلد: {BASE_DIR}")
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # التحقق مما إذا كانت العملية هي python وتشغل ملفاً داخل مجلد المشروع
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline:
                    # تحقق إذا كان أي من وسائط الأمر يحتوي على مسار المشروع أو اسم المجلد
                    is_project_proc = any(str(BASE_DIR) in str(arg) for arg in cmdline)
                    is_module_proc = any("Bots_Folder." in str(arg) for arg in cmdline)
                    
                    if is_project_proc or is_module_proc:
                        print(f"   - إيقاف العملية: {proc.pid} ({' '.join(cmdline)})")
                        proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

if __name__ == "__main__":
    kill_all_bot_processes()
