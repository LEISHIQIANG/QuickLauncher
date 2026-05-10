@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

REM Switch to project root directory (assuming script is in scripts/ folder)
cd /d "%~dp0.."

echo.
echo ========================================
echo   QuickLauncher Build Tool
echo ========================================
echo.
echo   Step: Obfuscate - Compile - Package
echo.

REM === Version Information ===
set "APP_PUBLISHER=Layton"
set "APP_VERSION=%~1"
if "%APP_VERSION%"=="" set /p "APP_VERSION=Version (default 2.6.7.5): "
if "%APP_VERSION%"=="" set "APP_VERSION=2.6.7.5"

echo.
echo   Version: %APP_VERSION%
echo   Publisher: %APP_PUBLISHER%
echo.
echo ----------------------------------------

REM ============================================
REM [1/5] Check Python
REM ============================================
echo.
echo [1/5] Checking Python...
set "PYTHON_CMD="
set "SELECTOR_PY="

python --version >nul 2>&1
if !ERRORLEVEL! EQU 0 set "SELECTOR_PY=python"

if not defined SELECTOR_PY (
    py -3 --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "SELECTOR_PY=py -3"
)

if not defined SELECTOR_PY (
    echo   [X] No Python found to run the build interpreter selector.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

!SELECTOR_PY! scripts\select_build_python.py --min 3.11 --max 3.12 --prefer "3.12,3.11" --explain
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [X] Nuitka build requires 64-bit CPython 3.9-3.12.
    echo   [!] Python 3.13 is detected but intentionally skipped for this build.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

for /f "delims=" %%p in ('!SELECTOR_PY! scripts\select_build_python.py --min 3.11 --max 3.12 --prefer "3.12,3.11" --cmd') do set "PYTHON_CMD=%%p"
if not defined PYTHON_CMD (
    echo   [X] Failed to select Python interpreter.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

REM ============================================
REM [2/5] Check Inno Setup
REM ============================================
echo.
echo [2/5] Checking Inno Setup...
set "ISCC="
for %%p in (
    "E:\Inno Setup 6\ISCC.exe"
    "D:\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do (
    if exist %%~p set "ISCC=%%~p"
)

if "!ISCC!"=="" (
    echo   [X] Inno Setup 6 not found!
    echo   Please install: https://jrsoftware.org/isinfo.php
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)
echo   Found: Inno Setup

REM ============================================
REM [3/5] Install dependencies
REM ============================================
echo.
echo [3/5] Installing dependencies...
!PYTHON_CMD! -m pip install --upgrade pip -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
!PYTHON_CMD! -m pip install nuitka ordered-set zstandard python-minifier -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
!PYTHON_CMD! -m pip install PyQt5==5.15.11 PyQt5-Qt5==5.15.2 pynput pywin32 psutil pillow -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
echo   Done

REM ============================================
REM [4/5] Obfuscate code
REM ============================================
echo.
echo [4/5] Obfuscating code...
echo.

REM Clean all caches (ensure using latest code)
echo   Cleaning all caches...
if exist "obfuscated_src" rmdir /s /q "obfuscated_src" 2>nul
if exist "dist\QuickLauncher" rmdir /s /q "dist\QuickLauncher" 2>nul
if exist "dist\main.dist" rmdir /s /q "dist\main.dist" 2>nul
if exist "dist\main.build" rmdir /s /q "dist\main.build" 2>nul
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
del /s /q *.pyc >nul 2>&1
if exist "%LOCALAPPDATA%\Nuitka\Nuitka\Cache" rd /s /q "%LOCALAPPDATA%\Nuitka\Nuitka\Cache" 2>nul
echo   Cache cleaned

echo   Obfuscating source code...

!PYTHON_CMD! scripts\obfuscate.py
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [X] Obfuscation failed!
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

if not exist "obfuscated_src\main.py" (
    echo   [X] Output verification failed!
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

REM ============================================
REM [5/5] Nuitka compile
REM ============================================
echo.
echo ========================================
echo [5/5] Nuitka compiling...
echo ========================================
echo.
echo   [!] First build may take 5-15 minutes
echo   [!] Please wait...
echo.

if exist "dist\QuickLauncher" rmdir /s /q "dist\QuickLauncher" 2>nul
if exist "dist\main.dist" rmdir /s /q "dist\main.dist" 2>nul
if exist "dist\main.build" rmdir /s /q "dist\main.build" 2>nul

!PYTHON_CMD! -m nuitka ^
    --mingw64 ^
    --standalone ^
    --windows-console-mode=disable ^
    --show-progress ^
    --lto=yes ^
    --remove-output ^
    --no-pyi-file ^
    --windows-icon-from-ico="assets\app.ico" ^
    --enable-plugin=pyqt5 ^
    --include-qt-plugins=platforms ^
    --noinclude-qt-translations ^
    --noinclude-dlls=opengl32.dll,d3dcompiler_*.dll ^
    --noinclude-dlls=qt5quick.dll,qt5qml*.dll,qt5multimedia.dll,qt5webengine*.dll ^
    --noinclude-dlls=qt5dbus.dll,qt53d*.dll,qt5designer*.dll,qt5help.dll ^
    --noinclude-dlls=qt5location.dll,qt5positioning.dll,qt5sensors.dll ^
    --noinclude-dlls=qt5serialport.dll,qt5sql.dll,qt5test.dll,qt5xml.dll ^
    --noinclude-dlls=qt5svg.dll,qt5printsupport.dll ^
    --noinclude-dlls=mfc140u.dll,mfc140*.dll ^
    --noinclude-dlls=msvcp140.dll,msvcp140_1.dll,msvcp140_2.dll ^
    --noinclude-dlls=vcruntime140.dll,vcruntime140_1.dll ^
    --noinclude-dlls=concrt140.dll,vcomp140.dll ^
    --noinclude-dlls=api-ms-win-crt-*.dll,ucrtbase.dll ^
    --noinclude-dlls=qt6pdf.dll ^
    --noinclude-dlls=libcrypto-3.dll,libssl-3.dll ^
    --company-name="%APP_PUBLISHER%" ^
    --product-name="QuickLauncher" ^
    --file-version="%APP_VERSION%" ^
    --product-version="%APP_VERSION%" ^
    --copyright="Copyright (C) %APP_PUBLISHER%" ^
    --output-dir=dist ^
    --include-data-dir=assets=assets ^
    --include-data-files=hooks\hooks.dll=hooks\hooks.dll ^
    --include-package=ui ^
    --include-package=core ^
    --include-package=hooks ^
    --include-module=pynput.mouse._win32 ^
    --include-module=pynput.keyboard._win32 ^
    --include-module=win32gui ^
    --include-module=win32ui ^
    --include-module=win32con ^
    --include-module=win32api ^
    --include-module=win32process ^
    --include-module=win32event ^
    --include-module=pythoncom ^
    --include-module=win32com.client ^
    --include-module=win32com.shell.shell ^
    --include-module=psutil ^
    --include-module=PIL.Image ^
    --include-module=ctypes.wintypes ^
    --nofollow-import-to=pytest,unittest,tkinter,test,setuptools,pip,distutils,IPython,notebook,numpy,matplotlib,scipy,pandas,sklearn,tensorflow,torch,cv2,email,http,urllib3,requests,asyncio,xml,html,csv,pypinyin ^
    --jobs=%NUMBER_OF_PROCESSORS% ^
    --assume-yes-for-downloads ^
    --output-filename=QuickLauncher.exe ^
    obfuscated_src\main.py

echo.
echo   Cleaning temp files...
rmdir /s /q "obfuscated_src" 2>nul

if not exist "dist\main.dist\QuickLauncher.exe" (
    echo.
    echo   [X] Compile failed! Check errors above.
    echo.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

ren "dist\main.dist" "QuickLauncher"
copy "assets\app.ico" "dist\QuickLauncher\" >nul 2>&1

REM Clean unnecessary files
echo.
echo   Cleaning unnecessary files...
cd dist\QuickLauncher
del /f /q qt5pdf.dll qt6pdf.dll qt5quick*.dll qt5qml*.dll qt5multimedia.dll qt5dbus.dll qt53d*.dll 2>nul
del /f /q qt5designer*.dll qt5help.dll qt5location.dll qt5positioning.dll qt5sensors.dll 2>nul
del /f /q qt5serialport.dll qt5sql.dll qt5test.dll qt5xml.dll qt5xmlpatterns.dll 2>nul
del /f /q qt5svg.dll qt5printsupport.dll 2>nul
del /f /q mfc140*.dll atl140.dll 2>nul
del /f /q libcrypto-*.dll libssl-*.dll libeay32.dll ssleay32.dll 2>nul
del /f /q _sqlite3.pyd 2>nul
if exist "PyQt5" (
    del /f /q PyQt5\QtPdf.pyd PyQt5\QtQuick*.pyd PyQt5\QtQml*.pyd PyQt5\QtMultimedia*.pyd 2>nul
    del /f /q PyQt5\QtDesigner*.pyd PyQt5\QtHelp.pyd PyQt5\QtSql.pyd PyQt5\QtTest.pyd PyQt5\QtXml*.pyd 2>nul
    del /f /q PyQt5\QtSvg.pyd PyQt5\QtPrintSupport.pyd 2>nul
)
if exist "PyQt5\qt-plugins\platforms" (
    del /f /q PyQt5\qt-plugins\platforms\qdirect2d.dll 2>nul
    del /f /q PyQt5\qt-plugins\platforms\qoffscreen.dll 2>nul
    del /f /q PyQt5\qt-plugins\platforms\qminimal.dll 2>nul
)
if exist "PyQt5\qt-plugins\styles" rmdir /s /q PyQt5\qt-plugins\styles 2>nul
if exist "PyQt5\qt-plugins\tls" rmdir /s /q PyQt5\qt-plugins\tls 2>nul
if exist "PyQt5\qt-plugins\mediaservice" rmdir /s /q PyQt5\qt-plugins\mediaservice 2>nul
if exist "PyQt5\qt-plugins\printsupport" rmdir /s /q PyQt5\qt-plugins\printsupport 2>nul
if exist "PyQt5\qt-plugins\imageformats" (
    del /f /q PyQt5\qt-plugins\imageformats\qtiff.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qicns.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qwbmp.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qtga.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qpdf.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qsvg.dll 2>nul
)
if exist "PyQt5\qt-plugins\iconengines" (
    del /f /q PyQt5\qt-plugins\iconengines\qsvgicon.dll 2>nul
)
if exist "PyQt5\qt-plugins\platformthemes" (
    del /f /q PyQt5\qt-plugins\platformthemes\qxdgdesktopportal.dll 2>nul
)
if exist "PIL" del /f /q PIL\_imagingcms.pyd PIL\_imagingtk.pyd PIL\_imagingmath.pyd 2>nul
if exist "config" (
    del /f /q config\*.log config\*.log.* 2>nul
    del /f /q config\data.json config\data.json.backup 2>nul
)
cd ..\..
echo   Done

REM UPX compression
echo.
echo   UPX compressing...
if exist "upx.exe" (
    upx.exe --ultra-brute dist\QuickLauncher\QuickLauncher.exe >nul 2>&1
    upx.exe --best --lzma dist\QuickLauncher\python*.dll >nul 2>&1
    upx.exe --best --lzma dist\QuickLauncher\qt6*.dll >nul 2>&1
    upx.exe --best --lzma dist\QuickLauncher\*.pyd >nul 2>&1
    if exist "dist\QuickLauncher\PIL" upx.exe --best --lzma dist\QuickLauncher\PIL\*.pyd >nul 2>&1
    if exist "dist\QuickLauncher\psutil" upx.exe --best --lzma dist\QuickLauncher\psutil\*.pyd >nul 2>&1
    if exist "dist\QuickLauncher\win32com\shell" upx.exe --best --lzma dist\QuickLauncher\win32com\shell\*.pyd >nul 2>&1
    echo   [OK] UPX compression done!
) else (
    echo   [!] upx.exe not found, skipping compression
)

echo.
echo   [OK] Nuitka compile done!

REM ============================================
REM Generate installer
REM ============================================
echo.
echo ----------------------------------------
echo Generating installer (Inno Setup)...
echo ----------------------------------------
echo.

"!ISCC!" /DMyAppName="QuickLauncher" /DMyAppVersion="%APP_VERSION%" /DMyAppFileVersion="%APP_VERSION%" /DMyAppPublisher="%APP_PUBLISHER%" scripts\installer.iss

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [X] Installer generation failed!
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

REM ============================================
REM Done
REM ============================================
echo.
echo ========================================
echo   BUILD SUCCESS!
echo ========================================
echo.
echo   Output:
echo   - Portable: dist\QuickLauncher\QuickLauncher.exe
echo   - Installer: dist\QuickLauncher_Setup_%APP_VERSION%.exe
echo.
echo   Protection:
echo   [Y] Variable obfuscation
echo   [Y] Docstring removal
echo   [Y] Code compression
echo   [Y] Native compilation
echo.
echo   Source code: NOT modified
echo.
echo ========================================
if "%QL_NO_PAUSE%"=="" pause
