@echo off
setlocal
cd /d "%~dp0"
title Boda Bot System - Control Center

where python >nul 2>&1
if %errorlevel% equ 0 (
    python start_boda.py
    if %errorlevel% neq 0 pause
    exit /b %errorlevel%
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 start_boda.py
    if %errorlevel% neq 0 pause
    exit /b %errorlevel%
)

echo.
echo ==============================================================
echo [ERROR] Python is not installed or not in your system PATH!
echo Please install Python 3.10+ from https://www.python.org/
echo Make sure to check "Add Python to PATH" during installation.
echo ==============================================================
echo.
pause
exit /b 1
