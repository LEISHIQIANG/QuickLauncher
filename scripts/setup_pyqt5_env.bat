@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\.."

if "%~1"=="" (
    echo Usage: scripts\setup_pyqt5_env.bat 3.8^|3.11^|3.12
    exit /b 1
)

set "PY_VER=%~1"
if "%PY_VER%"=="3.8" (
    set "VENV_DIR=.venv-py38"
) else if "%PY_VER%"=="3.11" (
    set "VENV_DIR=.venv-py311"
) else if "%PY_VER%"=="3.12" (
    set "VENV_DIR=.venv-py312"
) else (
    echo [ERROR] Unsupported Python version: %PY_VER%
    echo Supported versions: 3.8, 3.11, 3.12
    exit /b 1
)

echo [1/4] Selecting Python %PY_VER%...
py -%PY_VER% -c "import sys, struct; assert struct.calcsize('P') == 8; print(sys.executable)" >nul
if errorlevel 1 (
    echo [ERROR] Python %PY_VER% 64-bit was not found by the py launcher.
    exit /b 1
)

echo [2/4] Creating/updating %VENV_DIR%...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    py -%PY_VER% -m venv "%VENV_DIR%"
    if errorlevel 1 exit /b 1
)

set "PY=%CD%\%VENV_DIR%\Scripts\python.exe"

echo [3/4] Installing PyQt5-only dependencies...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%PY%" -m pip uninstall -y PyQt6 PyQt6-Qt6 PyQt6-sip PySide6 PySide6-Essentials PySide6-Addons shiboken6 >nul 2>&1
"%PY%" -m pip install -r requirements.txt -r requirements-dev.txt
if errorlevel 1 exit /b 1

echo [4/4] Verifying Qt binding...
"%PY%" tools\check_qt.py
if errorlevel 1 exit /b 1
"%PY%" -c "import qt_compat; print(qt_compat.QT_LIB, qt_compat.PYQT_VERSION)"
if errorlevel 1 exit /b 1

echo [OK] %VENV_DIR% is ready.
