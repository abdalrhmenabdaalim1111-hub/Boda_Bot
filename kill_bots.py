"""
kill_bots.py — أداة إنهاء جميع عمليات البوت العالقة
تُستخدم قبل تشغيل Manager.py لضمان عدم وجود instances قديمة
"""
import subprocess, sys, os

def kill_all_bot_processes():
    """إنهاء جميع عمليات Python التي تشغّل ملفات bot_*.py"""
    print("🔪 جاري إنهاء جميع عمليات البوت العالقة...")
    
    try:
        # PowerShell command to find and kill bot processes
        result = subprocess.run([
            "powershell", "-Command",
            "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*bot_*.py*' } | "
            "Select-Object ProcessId, CommandLine | Format-Table -AutoSize"
        ], capture_output=True, text=True, timeout=10)
        
        if result.stdout.strip():
            print("📋 العمليات الموجودة:")
            print(result.stdout)
        
        # Kill them
        kill_result = subprocess.run([
            "powershell", "-Command",
            "Get-WmiObject Win32_Process | "
            "Where-Object { $_.CommandLine -like '*bot_*.py*' -and $_.ProcessId -ne " + str(os.getpid()) + " } | "
            "ForEach-Object { "
            "  Write-Host \"Killing PID $($_.ProcessId): $($_.CommandLine.Substring(0, [Math]::Min(80,$_.CommandLine.Length)))\"; "
            "  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue "
            "}"
        ], capture_output=True, text=True, timeout=15)
        
        if kill_result.stdout.strip():
            print(kill_result.stdout)
            
        print("✅ تم إنهاء جميع العمليات العالقة!")
        print()
        
    except Exception as e:
        print(f"⚠️ خطأ: {e}")

if __name__ == "__main__":
    kill_all_bot_processes()
    print("الآن يمكنك تشغيل Manager.py بأمان.")
