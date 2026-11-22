# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import venv
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

def run_command(cmd):
    print(f"Executing: {cmd}")
    return subprocess.run(cmd, shell=True, cwd=BASE_DIR)

def setup():
    print("--- Professional Setup for Boda Bot System ---")
    
    # 1. Create Virtual Environment
    venv_dir = BASE_DIR / "venv"
    if not venv_dir.exists():
        print("[1/4] Creating Virtual Environment...")
        venv.create(venv_dir, with_pip=True)
    
    # 2. Path to pip inside venv
    pip_path = str(venv_dir / "Scripts" / "pip.exe")
    python_path = str(venv_dir / "Scripts" / "python.exe")
    
    # 3. Install Requirements
    print("[2/4] Installing requirements...")
    run_command(f"{pip_path} install --upgrade pip")
    if (BASE_DIR / "requirements.txt").exists():
        run_command(f"{pip_path} install -r requirements.txt")
    run_command(f"{pip_path} install uvicorn fastapi psutil cryptography")

    # 4. Clean up junk
    print("[3/4] Cleaning old cache and logs...")
    junk_dirs = ["__pycache__", "Backups", "Logs"]
    for d in junk_dirs:
        dir_path = BASE_DIR / d
        if dir_path.exists():
            import shutil
            shutil.rmtree(dir_path, ignore_errors=True)
            print(f"   - Removed {d}")

    # 5. Create Pro Launcher
    print("[4/4] Creating Pro Launcher...")
    launcher_content = f"""@echo off
title Boda Pro System
cd /d "%~dp0"
call venv\\Scripts\\activate
echo [🛠️] Cleaning ports...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 1 >nul
echo [🚀] Starting System...
start "Boda-Server" "{python_path}" start_boda.py
timeout /t 5 >nul
start http://127.0.0.1:8080/dashboard
exit
"""
    (BASE_DIR / "Start_Pro.bat").write_text(launcher_content)
    
    print("\n✅ Setup Complete! Use Start_Pro.bat to run the system.")

if __name__ == "__main__":
    setup()
