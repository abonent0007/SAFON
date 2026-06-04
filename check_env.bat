@echo off
chcp 65001 >nul
title С.А.Ф.О.Н. - Диагностика окружения

echo ========================================
echo    С.А.Ф.О.Н. - Диагностика окружения
echo ========================================
echo.

echo [1/6] Проверка Python 3.11 в системе...
py -3.11 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ОШИБКА] Python 3.11 НЕ НАЙДЕН!
    echo   Установите Python 3.11.10
) else (
    for /f "tokens=2" %%v in ('py -3.11 --version 2^>^&1') do echo   Найден Python %%v
)

echo.
echo [2/6] Проверка виртуального окружения...
if exist venv\Scripts\python.exe (
    echo   [OK] Виртуальное окружение найдено
    for /f "tokens=2" %%v in ('venv\Scripts\python.exe --version 2^>^&1') do set VENVVER=%%v
    echo   Версия в окружении: Python %VENVVER%
    echo %VENVVER% | find "3.11" >nul
    if %errorlevel% neq 0 (
        echo   [ВНИМАНИЕ] Версия окружения НЕ 3.11! Пересоздайте через install.bat
    )
) else (
    echo   [ОШИБКА] Виртуальное окружение не найдено
    echo   Запустите install.bat
)

echo.
echo [3/6] Проверка установленных пакетов...
if exist venv\Scripts\pip.exe (
    echo   Установленные пакеты:
    venv\Scripts\pip.exe list | findstr -i "flask numpy torch transformers skyfield sentence"
)

echo.
echo [4/6] Проверка файла .env...
if exist .env (
    echo   [OK] .env найден
    findstr "GOOGLE_MAPS_API_KEY" .env
) else (
    echo   [ОШИБКА] .env не найден!
    if exist .env.example (
        copy .env.example .env >nul
        echo   Создан .env из .env.example - ОТРЕДАКТИРУЙТЕ ЕГО!
    )
)

echo.
echo [5/6] Проверка порта 5000...
netstat -aon | find ":5000" | find "LISTENING" >nul
if %errorlevel% neq 0 (
    echo   Порт 5000 свободен
) else (
    echo   [ВНИМАНИЕ] Порт 5000 занят!
)

echo.
echo [6/6] Проверка папок...
if not exist data mkdir data
if not exist logs mkdir logs
echo   Папка data: %CD%\data
echo   Папка logs: %CD%\logs

echo.
echo ========================================
echo    ДИАГНОСТИКА ЗАВЕРШЕНА
echo ========================================
pause
