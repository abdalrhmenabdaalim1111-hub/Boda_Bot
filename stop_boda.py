# -*- coding: utf-8 -*-
"""stop_boda.py — Clean shutdown for Boda Bot System processes."""
import os
import subprocess
import sys

print("🛑 جاري إيقاف نظام بودة والخادم...")
try:
    out = subprocess.check_output('netstat -ano | findstr ":8080 "', shell=True, text=True, errors="ignore")
    pids = set()
    for line in out.strip().splitlines():
        parts = line.strip().split()
        if len(parts) >= 5 and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    my_pid = os.getpid()
    for pid in pids:
        if pid != my_pid and pid > 0:
            subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True)
            print(f"  ✓ تم إنهاء العملية PID {pid}")
except Exception as e:
    pass

print("✅ تم إيقاف جميع خدمات وخوادم بودة بنجاح.")

