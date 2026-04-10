@echo off
title 0xRex — Autonomous Crypto Trading
color 0A

echo.
echo   ██████╗██████╗ ██╗   ██╗██████╗ ████████╗ ██████╗ ██████╗  ██████╗ ████████╗
echo  ██╔════╝██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗██╔═══██╗╚══██╔══╝
echo  ██║     ██████╔╝ ╚████╔╝ ██████╔╝   ██║   ██║   ██║██████╔╝██║   ██║   ██║
echo  ██║     ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   ██║   ██║██╔══██╗██║   ██║   ██║
echo  ╚██████╗██║  ██║   ██║   ██║        ██║   ╚██████╔╝██████╔╝╚██████╔╝   ██║
echo   ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝    ╚═════╝ ╚═════╝  ╚═════╝    ╚═╝
echo.
echo  AUTONOMOUS CRYPTO TRADING — CryptoCred TA + GCR Pearls of Wisdom
echo  ═══════════════════════════════════════════════════════════════════
echo.

cd /d "%~dp0"

echo [*] Checking Python environment...
python --version || (echo ERROR: Python not found && pause && exit /b 1)

echo [*] Installing dependencies...
pip install fastapi uvicorn[standard] numpy python-dotenv loguru --quiet

echo.
echo [*] Starting 0xRex server on http://localhost:8000
echo [*] Press Ctrl+C to stop
echo.

python -m uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload

pause
