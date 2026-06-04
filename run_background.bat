@echo off
chcp 65001 >nul
title С.А.Ф.О.Н. - Фоновый режим

echo ========================================
echo    С.А.Ф.О.Н. - Фоновый запуск
echo ========================================
echo.

echo [1/6] Проверка Python 3.11 в системе...
py -3.11 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ОШИБКА] Python 3.11 не найден в системе!
    echo   Установите Python 3.11.10:
    echo   https://www.python.org/downloads/release/python-31110/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('py -3.11 --version 2^>^&1') do set PYVER=%%v
echo   Python %PYVER% найден

echo.
echo [2/6] Проверка виртуального окружения Python 3.11...
if not exist "venv\Scripts\python.exe" (
    echo   [ОШИБКА] Виртуальное окружение не найдено!
    echo   Запустите install.bat для создания окружения с Python 3.11
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('venv\Scripts\python.exe --version 2^>^&1') do set VENVVER=%%v
echo   Окружение: Python %VENVVER%
echo %VENVVER% | find "3.11" >nul
if %errorlevel% neq 0 (
    echo   [ОШИБКА] Окружение создано НЕ на Python 3.11!
    echo   Удалите папку venv и перезапустите install.bat
    pause
    exit /b 1
)
echo   [OK] Версия Python строго 3.11

echo.
echo [3/6] Проверка LM Studio...
curl -s http://localhost:1234/v1/models >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] LM Studio обнаружен (порт 1234)
) else (
    echo   ⚠️ LM Studio не запущен!
    echo   Запустите LM Studio, загрузите DeepSeek V4 Pro
    echo   и нажмите "Start Local Inference Server"
    echo.
    set /p CONT="Продолжить без AI? (y/n): "
    if /i not "!CONT!"=="y" exit /b 1
)

echo.
echo [4/6] Подготовка окружения...
if not exist data mkdir data
if not exist logs mkdir logs
if not exist .env (
    echo   [ПРЕДУПРЕЖДЕНИЕ] .env не найден, создаю из .env.example
    if exist .env.example copy .env.example .env >nul
)

echo [5/6] Запуск С.А.Ф.О.Н.а в фоне (Python 3.11)...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| find ":5000" ^| find "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

start /B venv\Scripts\python.exe web\app.py > logs\safon.log 2>&1

for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST 2^>nul ^| find "PID:"') do set PID=%%a
echo %PID% > logs\safon.pid

timeout /t 3 /nobreak >nul

echo [6/6] Проверка статуса...
curl -s http://localhost:5000/api/ai/status >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo    [OK] С.А.Ф.О.Н. ЗАПУЩЕН!
    echo ========================================
    echo.
    echo   PID: %PID%
    echo   Логи: logs\safon.log
    echo   Открыть: http://localhost:5000
) else (
    echo   [ОШИБКА] Не удалось запустить!
    echo   Проверьте логи: logs\safon.log
)

echo.
echo Для остановки запустите stop_background.bat
pause
