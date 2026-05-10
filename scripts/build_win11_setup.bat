@echo off
setlocal EnableDelayedExpansion
set "COPYCMD=/Y"
cd /d "%~dp0.."
chcp 65001 >nul
echo ========================================
echo QuickLauncher Win11 Full Build - Max Performance (Nuitka + PyQt5)
echo ========================================
echo.
echo [!] Note: This script is optimized for Windows 10/11
echo [!] Using Nuitka for fastest startup speed
echo [!] 64-bit Windows 10/11 only
echo.

REM === Version configuration ===
set "APP_PUBLISHER=Layton"
set "DEFAULT_APP_VERSION=1.5.6.0"
set "APP_VERSION="
set /p APP_VERSION=Enter version [1.5.6.0]:
if not defined APP_VERSION set "APP_VERSION=%DEFAULT_APP_VERSION%"

echo.
echo [Build Info]
echo   Publisher: %APP_PUBLISHER%
echo   Version: %APP_VERSION%
echo.
REM ====================

REM 1. Check Python 3.10+ (recommended)
echo [0/4] Stopping any running QuickLauncher process...
taskkill /IM QuickLauncher.exe /T /F >nul 2>&1
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq QuickLauncher.exe" | find /I "QuickLauncher.exe" >nul
if not errorlevel 1 (
    echo   [!] QuickLauncher.exe is still running. Close it manually or run this build script as administrator.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

echo [1/4] Checking build environment...
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
    echo   Please install Python 3.11 or 3.12 and ensure python.exe or py.exe is available.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

!SELECTOR_PY! scripts\select_build_python.py --min 3.11 --max 3.12 --prefer "3.12,3.11" --explain
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERROR] Nuitka build requires 64-bit CPython 3.9-3.12.
    echo   Python 3.13 is detected but intentionally skipped for this build.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

for /f "delims=" %%p in ('!SELECTOR_PY! scripts\select_build_python.py --min 3.11 --max 3.12 --prefer "3.12,3.11" --cmd') do set "PYTHON_CMD=%%p"
if not defined PYTHON_CMD (
    echo   [X] Failed to select Python interpreter.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

REM 2. Check Inno Setup
set "ISCC="
if exist "E:\Inno Setup 6\ISCC.exe" set "ISCC=E:\Inno Setup 6\ISCC.exe"
if exist "D:\Inno Setup 6\ISCC.exe" set "ISCC=D:\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo   [X] Inno Setup not installed! Cannot generate installer.
    echo   Please install Inno Setup 6 ^(Unicode^) and retry.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)
echo   [OK] Found Inno Setup: !ISCC!

REM 3. Install/update dependencies (Win11 specific config)
echo.
echo [2/4] Configuring Win11 environment (PyQt5)...

REM Temporarily clear proxy
REM set "HTTP_PROXY="
REM set "HTTPS_PROXY="

echo   Installing/updating PyQt5, Nuitka and other dependencies...
!PYTHON_CMD! -m pip install --upgrade pip -q -i https://pypi.tuna.tsinghua.edu.cn/simple
!PYTHON_CMD! -m pip install nuitka ordered-set zstandard PyQt5==5.15.11 PyQt5-Qt5==5.15.2 pynput pywin32 psutil pillow -q -i https://pypi.tuna.tsinghua.edu.cn/simple


echo.
echo [3/4] Starting Nuitka compilation (max performance mode)...
echo   [!] This may take several minutes, please wait...

REM Clean all caches (ensure latest code is used)
echo   Cleaning all build caches...
if exist "dist\QuickLauncher" rmdir /s /q "dist\QuickLauncher"
if exist "dist\main.dist" rmdir /s /q "dist\main.dist"
if exist "dist\main.build" rmdir /s /q "dist\main.build"
if exist "obfuscated_src" rmdir /s /q "obfuscated_src"
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
del /s /q *.pyc >nul 2>&1
REM Preserve the Nuitka download cache so MinGW/GCC is not re-downloaded every build.
echo   Cache cleanup completed

REM Nuitka build command - Win11 optimized (max size optimization mode)
!PYTHON_CMD! -m nuitka ^
    --mingw64 ^
    --standalone ^
    --windows-console-mode=disable ^
    --show-progress ^
    --assume-yes-for-downloads ^
    --lto=yes ^
    --remove-output ^
    --no-pyi-file ^
    --windows-icon-from-ico="assets\app.ico" ^
    --enable-plugin=pyqt5 ^
    --include-qt-plugins=platforms ^
    --noinclude-qt-translations ^
    --noinclude-dlls=opengl32.dll,d3dcompiler_*.dll ^
    --noinclude-dlls=qt5quick*.dll,qt5qml*.dll,qt5multimedia*.dll,qt5webengine*.dll,qt5webchannel*.dll ^
    --noinclude-dlls=qt5dbus.dll,qt53d*.dll,qt5designer*.dll,qt5help.dll,qt5bluetooth.dll,qt5nfc.dll ^
    --noinclude-dlls=qt5location.dll,qt5positioning.dll,qt5sensors.dll,qt5texttospeech.dll,qt5websockets.dll ^
    --noinclude-dlls=qt5serialport.dll,qt5sql.dll,qt5test.dll,qt5xml*.dll,qt5networkauth.dll,qt5purchasing.dll ^
    --noinclude-dlls=qt5remoteobjects.dll,qt5script*.dll,qt5scxml.dll,qt5virtualkeyboard.dll,qt5charts.dll,qt5datavisualization.dll ^
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
    --include-package=bootstrap ^
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
    --output-filename=QuickLauncher.exe ^
    main.py

if not exist "dist\main.dist\QuickLauncher.exe" (
    echo.
    echo   [!] Compilation failed! Please check the error messages above.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

REM Cleanup temporary build files
if exist "dist\main.build" (
    echo   Cleaning temporary build files...
    rmdir /s /q "dist\main.build" >nul 2>&1
)

REM Keep VC++ runtime DLLs
echo   Keeping VC++ runtime DLLs...
cd dist\main.dist

REM Remove unnecessary Qt modules and MFC
echo   Cleaning unnecessary Qt modules and MFC...
del /f /q qt5pdf.dll qt6pdf.dll qt5quick*.dll qt5qml*.dll qt5multimedia*.dll qt5dbus.dll qt53d*.dll 2>nul
del /f /q qt5designer*.dll qt5help.dll qt5location.dll qt5positioning.dll qt5sensors.dll 2>nul
del /f /q qt5serialport.dll qt5sql.dll qt5test.dll qt5xml*.dll qt5xmlpatterns.dll 2>nul
del /f /q qt5webengine*.dll qt5webchannel*.dll qt5websockets.dll qt5bluetooth.dll qt5nfc.dll 2>nul
del /f /q qt5texttospeech.dll qt5networkauth.dll qt5script*.dll qt5virtualkeyboard.dll 2>nul
del /f /q qt5svg.dll qt5printsupport.dll 2>nul
del /f /q mfc140*.dll atl140.dll 2>nul
del /f /q libcrypto-*.dll libssl-*.dll libeay32.dll ssleay32.dll 2>nul
del /f /q _sqlite3.pyd 2>nul
if exist "PyQt5" (
    del /f /q PyQt5\QtPdf.pyd PyQt5\QtQuick*.pyd PyQt5\QtQml*.pyd PyQt5\QtMultimedia*.pyd 2>nul
    del /f /q PyQt5\QtDesigner*.pyd PyQt5\QtHelp.pyd PyQt5\QtSql.pyd PyQt5\QtTest.pyd PyQt5\QtXml*.pyd 2>nul
    del /f /q PyQt5\QtSvg.pyd PyQt5\QtPrintSupport.pyd 2>nul
)

REM Remove unnecessary platform plugins (keep qwindows only)
echo   Cleaning unnecessary platform plugins...
if exist "PyQt5\qt-plugins\platforms" (
    del /f /q PyQt5\qt-plugins\platforms\qdirect2d.dll 2>nul
    del /f /q PyQt5\qt-plugins\platforms\qoffscreen.dll 2>nul
    del /f /q PyQt5\qt-plugins\platforms\qminimal.dll 2>nul
)

REM Remove styles plugins (use system default)
if exist "PyQt5\qt-plugins\styles" (
    rmdir /s /q PyQt5\qt-plugins\styles 2>nul
)

REM Remove unnecessary TLS plugins (no network features)
if exist "PyQt5\qt-plugins\tls" (
    rmdir /s /q PyQt5\qt-plugins\tls 2>nul
)

REM Remove unnecessary image format plugins (keep ico/png/jpg/gif/webp/bmp)
echo   Cleaning unnecessary image format plugins...
if exist "PyQt5\qt-plugins\imageformats" (
    del /f /q PyQt5\qt-plugins\imageformats\qtiff.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qicns.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qwbmp.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qtga.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qpdf.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qsvg.dll 2>nul
)

REM Remove SVG iconengine plugin (no SVG icons)
if exist "PyQt5\qt-plugins\iconengines" (
    del /f /q PyQt5\qt-plugins\iconengines\qsvgicon.dll 2>nul
)

REM Remove XDG desktop portal plugin (Linux-only, useless on Windows)
if exist "PyQt5\qt-plugins\platformthemes" (
    del /f /q PyQt5\qt-plugins\platformthemes\qxdgdesktopportal.dll 2>nul
)

REM Remove unnecessary PIL submodules
echo   Cleaning unnecessary PIL submodules...
if exist "PIL" (
    del /f /q PIL\_imagingcms.pyd PIL\_imagingtk.pyd PIL\_imagingmath.pyd 2>nul
)

REM Clean runtime files from config directory
echo   Cleaning runtime files from config directory...
if exist "config" (
    del /f /q config\*.log config\*.log.* 2>nul
    del /f /q config\data.json config\data.json.backup 2>nul
)

REM Remove unnecessary Qt plugins
echo   Removing unnecessary Qt plugins...
if exist "PyQt5\qt-plugins\mediaservice" (
    rmdir /s /q PyQt5\qt-plugins\mediaservice 2>nul
)
if exist "PyQt5\qt-plugins\printsupport" (
    rmdir /s /q PyQt5\qt-plugins\printsupport 2>nul
)
if exist "PyQt5\qt-plugins\platforms\qwebgl.dll" (
    del /f /q PyQt5\qt-plugins\platforms\qwebgl.dll 2>nul
)

REM Remove large Qt runtime folders that are not used by this project
echo   Removing unused Qt runtime folders...
if exist "PyQt5\Qt5\qml" (
    rmdir /s /q PyQt5\Qt5\qml 2>nul
)
if exist "PyQt5\Qt5\translations" (
    rmdir /s /q PyQt5\Qt5\translations 2>nul
)
if exist "PyQt5\Qt5\qsci" (
    rmdir /s /q PyQt5\Qt5\qsci 2>nul
)
if exist "PyQt5\bindings" (
    rmdir /s /q PyQt5\bindings 2>nul
)
if exist "PyQt5\uic" (
    rmdir /s /q PyQt5\uic 2>nul
)

REM Remove metadata and helper directories that are not needed at runtime
echo   Removing runtime metadata...
for /d %%D in (*.dist-info) do @rmdir /s /q "%%D" 2>nul
if exist "Pythonwin" (
    rmdir /s /q Pythonwin 2>nul
)

cd ..\..

REM Rename output folder
ren "dist\main.dist" "QuickLauncher"

REM UPX compression (ultra mode)
echo   UPX compressing executable...
if exist "upx.exe" (
    upx.exe --ultra-brute dist\QuickLauncher\QuickLauncher.exe >nul 2>&1
    upx.exe --best --lzma dist\QuickLauncher\python*.dll >nul 2>&1
    upx.exe --best --lzma dist\QuickLauncher\qt5*.dll >nul 2>&1
    upx.exe --best --lzma dist\QuickLauncher\*.pyd >nul 2>&1
    if exist "dist\QuickLauncher\PyQt5" upx.exe --best --lzma dist\QuickLauncher\PyQt5\*.pyd >nul 2>&1
    if exist "dist\QuickLauncher\PIL" upx.exe --best --lzma dist\QuickLauncher\PIL\*.pyd >nul 2>&1
    if exist "dist\QuickLauncher\psutil" upx.exe --best --lzma dist\QuickLauncher\psutil\*.pyd >nul 2>&1
    if exist "dist\QuickLauncher\win32com\shell" upx.exe --best --lzma dist\QuickLauncher\win32com\shell\*.pyd >nul 2>&1
    echo   [OK] UPX compression completed
) else (
    echo   [Warning] upx.exe not found, skipping compression
)

REM Copy required resources
echo   Copying resource files...
if exist "assets\app.ico" (
    copy /Y "assets\app.ico" "dist\QuickLauncher\" >nul
) else if exist "scripts\app.ico" (
    copy /Y "scripts\app.ico" "dist\QuickLauncher\" >nul
) else (
    echo   [Warning] app.ico not found, skipping copy.
)

echo.
echo [4/4] Generating Win11 installer (Inno Setup)...

set "SETUP_STAGE_DIR=dist\_inno_setup"

REM Switch to scripts directory to match relative paths in installer.iss
cd scripts

if exist "..\%SETUP_STAGE_DIR%" rmdir /s /q "..\%SETUP_STAGE_DIR%" >nul 2>&1
mkdir "..\%SETUP_STAGE_DIR%" >nul 2>&1
if exist "..\dist\QuickLauncher_Setup_%APP_VERSION%.exe" del /f /q "..\dist\QuickLauncher_Setup_%APP_VERSION%.exe" >nul 2>&1

"!ISCC!" /DMyAppName="QuickLauncher" /DMyAppVersion="%APP_VERSION%" /DMyAppFileVersion="%APP_VERSION%" /DMyAppPublisher="%APP_PUBLISHER%" installer.iss
if !ERRORLEVEL! NEQ 0 (
    echo   [!] Setup package generation failed.
    cd ..
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

cd ..

if not exist "%SETUP_STAGE_DIR%\QuickLauncher_Setup_%APP_VERSION%.exe" (
    echo   [!] Setup package was not generated in %SETUP_STAGE_DIR%.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

move /Y "%SETUP_STAGE_DIR%\QuickLauncher_Setup_%APP_VERSION%.exe" "dist\QuickLauncher_Setup_%APP_VERSION%.exe" >nul
if !ERRORLEVEL! NEQ 0 (
    echo   [!] Failed to move setup package into dist\.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

if exist "%SETUP_STAGE_DIR%" rmdir /s /q "%SETUP_STAGE_DIR%" >nul 2>&1

echo.
echo ========================================
echo   [OK] Build successful! (Win11 optimized version)
echo   Installer: dist\QuickLauncher_Setup_%APP_VERSION%.exe
echo ========================================
if "%QL_NO_PAUSE%"=="" pause
