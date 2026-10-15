@echo off
setlocal enabledelayedexpansion

title A.L.F.R.E.D. Executive Core Launcher

echo =====================================================================
echo           A.L.F.R.E.D. - Autonomous Logistics Functional
echo                 Response ^& Executive Director
echo =====================================================================
echo.

:: 1. Verify Virtual Environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found in .venv.
    echo Please create the environment first:
    echo   uv venv --python 3.11 .venv
    echo   .venv\Scripts\pip install -r backend\requirements.txt
    pause
    exit /b 1
)

:: 2. Verify HUD Build
if not exist "hud\dist\index.html" (
    echo [INFO] HUD production build not detected. Compiling HUD...
    cd hud
    call npm run build
    cd ..
)

echo [OK] Core dependencies verified.
echo.

:: 3. Launch Backend Coordinator in background process
echo [STARTING] A.L.F.R.E.D. Backend Coordinator (ws://127.0.0.1:8765)...
start "ALFRED-Backend" /min cmd /c "call .venv\Scripts\activate.bat && python -m backend.main"

:: Brief wait for WebSocket server initialization
timeout /t 2 /nobreak > nul

:: 4. Launch Electron HUD Desktop Overlay
echo [STARTING] A.L.F.R.E.D. Desktop HUD Overlay...
cd hud
call npm run electron:start
cd ..

echo.
echo [SHUTTING DOWN] Closing background services...
taskkill /fi "WINDOWTITLE eq ALFRED-Backend*" /t /f > nul 2>&1
echo System nominal. Goodbye, Sir.
