@echo off
setlocal
cd /d "%~dp0"
title Boda Bot System - Stop

where python >nul 2>&1
if %errorlevel% equ 0 (
    python stop_boda.py
    exit /b 0
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 stop_boda.py
    exit /b 0
)

for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr ":8080 "') do (
    taskkill /PID %%A /F >nul 2>&1
)
echo [OK] Stopped.
exit /b 0
