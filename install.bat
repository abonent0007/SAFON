@echo off
chcp 65001 >nul
title С.А.Ф.О.Н. - Установка

echo ========================================
echo    С.А.Ф.О.Н. - Установка с Python 3.11
echo ========================================
echo.

:: Проверка наличия Python 3.11 в системе
echo [1/5] Проверка Python 3.11...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python 3.11 не найден!
    echo.
    echo Скачайте и установите Python 3.11.10:
    echo https://www.python.org/downloads/release/python-31110/
    echo.
    echo ВАЖНО: При установке поставьте галку "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('py -3.11 --version 2^>^&1') do set PYTHON_VER=%%v
echo   Найден Python %PYTHON_VER%

:: Создание виртуального окружения с Python 3.11
echo [2/5] Создание виртуального окружения с Python 3.11...
if exist venv (
    echo   Удаляем старое окружение...
    rmdir /s /q venv
)
py -3.11 -m venv venv
if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать виртуальное окружение
    pause
    exit /b 1
)
echo   [OK] Виртуальное окружение создано

:: Активация окружения
echo [3/5] Активация окружения...
call venv\Scripts\activate.bat

:: Проверка версии в окружении
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set VENV_VER=%%v
echo   Активирован Python %VENV_VER%

:: Обновление pip
echo [4/5] Обновление pip...
venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

:: Установка зависимостей
echo [5/5] Установка зависимостей...
echo   Это может занять 5-10 минут...

venv\Scripts\python.exe -m pip install -r requirements.txt

:: Проверка установки
echo.
echo ========================================
echo    ПРОВЕРКА УСТАНОВКИ
echo ========================================
venv\Scripts\python.exe -c "import flask; print('flask:', flask.__version__)"
venv\Scripts\python.exe -c "import flask_cors; print('flask_cors: OK')"
venv\Scripts\python.exe -c "import numpy; print('numpy:', numpy.__version__)"
venv\Scripts\python.exe -c "import sentence_transformers; print('sentence_transformers: OK')"

echo.
echo ========================================
echo    УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!
echo ========================================
echo.
echo Далее:
echo 1. Отредактируйте .env и вставьте Google Maps API ключ
echo 2. Запустите run_background.bat для фоновой работы
echo 3. Откройте http://localhost:5000
echo.
pause