@echo off
title SAFON

echo ========================================
echo    S.A.F.O.N. - Launch
echo ========================================
echo.

echo [1/3] Checking venv Python 3.11...
if not exist "venv\Scripts\python.exe" (
    echo   ERROR: venv not found!
    echo   Run install.bat first
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('venv\Scripts\python.exe --version 2^>^&1') do set VENVVER=%%v
echo   venv Python: %VENVVER%
echo %VENVVER% | find "3.11" >nul
if %errorlevel% neq 0 (
    echo   ERROR: venv is NOT Python 3.11!
    echo   Delete venv folder and run install.bat again
    pause
    exit /b 1
)
echo   OK: Python 3.11 confirmed

echo.
echo [2/3] Checking config...
if not exist .env (
    echo   WARNING: .env not found
    if exist .env.example copy .env.example .env >nul
)
if not exist data mkdir data
if not exist logs mkdir logs

echo [3/3] Starting server...
echo   http://localhost:5000
echo   Press Ctrl+C to stop
echo.

venv\Scripts\python.exe web\app.py 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo   ERROR: Server stopped with code %errorlevel%
    echo ========================================
)
pause
