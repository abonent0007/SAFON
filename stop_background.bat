@echo off
chcp 65001 >nul
title С.А.Ф.О.Н. - Остановка

echo ========================================
echo    С.А.Ф.О.Н. - Остановка фоновых процессов
echo ========================================
echo.

:: Способ 1: По PID файлу (самый надёжный)
if exist logs\safon.pid (
    set /p PID=<logs\safon.pid
    echo [1/3] Остановка по PID: %PID%
    taskkill /PID %PID% /F >nul 2>&1
    if %errorlevel%==0 (
        echo   [OK] Процесс %PID% остановлен
    ) else (
        echo   [INFO] Процесс %PID% уже неактивен
    )
    del logs\safon.pid
) else (
    echo [1/3] PID файл не найден
)

:: Способ 2: По порту 5000
echo [2/3] Проверка порта 5000...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| find ":5000" ^| find "LISTENING"') do (
    echo   Найден процесс на порту 5000: %%a
    taskkill /PID %%a /F >nul 2>&1
    echo   [OK] Процесс %%a остановлен
)

:: Способ 3: Очистка мусорных процессов Python из папки проекта
echo [3/3] Проверка процессов Python...
tasklist /FI "IMAGENAME eq python.exe" /FO TABLE 2>nul

echo.
set /p kill_all="Завершить ВСЕ процессы python.exe? (y/n): "
if /i "%kill_all%"=="y" (
    taskkill /F /IM python.exe >nul 2>&1
    echo   [OK] Все процессы Python завершены
)

echo.
echo [OK] С.А.Ф.О.Н. остановлен.
echo.
echo Для запуска используйте run_background.bat
pause