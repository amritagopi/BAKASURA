@echo off
title Bakasura Launcher 👹

echo ========================================================
echo       BAKASURA PROTOCOL: INITIALIZING...
echo ========================================================
echo.

:: 0. Kill stale processes
echo [0/2] Purging old daemons...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
taskkill /F /IM "Bakasura Brain" >nul 2>&1

:: 1. Start Backend (Brain)
echo [1/2] Waking the Brain (Port 8001)...
start "Bakasura Brain" cmd /k "cd /d %~dp0 && .venv\Scripts\activate && cd core && python main.py"

:: Wait a bit for backend to warm up
timeout /t 3 >nul

:: 2. Start Frontend (Face)
echo [2/2] Summoning the Face...
cd /d %~dp0\app
npm run tauri dev

echo.
echo ========================================================
echo       SYSTEMS ONLINE. HAPPY HUNTING.
echo ========================================================
pause
