@echo off
setlocal EnableDelayedExpansion
set "COPYCMD=/Y"
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"

echo ========================================
echo QuickLauncher Win11 Full Build - Smooth UI Runtime (Nuitka + PyQt5)
echo ========================================
echo.
echo [!] Note: This script is optimized for Windows 10/11
echo [!] Using Nuitka with Win11 smooth-window runtime defaults
echo [!] 64-bit Windows 10/11 only
echo.

REM === Version configuration ===
set "APP_PUBLISHER=Layton"
set "APP_VERSION="
for /f "delims=" %%v in ('python scripts\read_project_version.py version 2^>nul') do set "APP_VERSION=%%v"
for /f "delims=" %%p in ('python scripts\read_project_version.py publisher 2^>nul') do set "APP_PUBLISHER=%%p"
if not defined APP_VERSION (
    echo.
    echo   [ERROR] Unable to read APP_VERSION from core\version.py.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

REM === Build log: wrap with PowerShell Tee-Object to record all output ===
REM Skipped on second entry (QL_LOGGING=1), runs build directly
if not defined QL_LOGGING (
    if not exist "dist\build_logs" mkdir "dist\build_logs" >nul 2>&1
    set "QL_LOGGING=1"
    powershell -NoProfile -Command "$bat='%~f0'; $ts=Get-Date -Format 'yyyyMMdd_HHmmss'; $log='dist\build_logs\build_'+$ts+'.log'; Write-Host \"Build log: $log\"; $env:QL_LOGGING='1'; $env:QL_NO_PAUSE='1'; $env:APP_VERSION='%APP_VERSION%'; $env:APP_PUBLISHER='%APP_PUBLISHER%'; $arg='\"'+$bat+'\" 2>&1'; cmd /c $arg | ForEach-Object { $_ -replace '\u001b\[[0-9;]*[a-zA-Z]', '' } | Tee-Object -FilePath $log; $exitCode=$LASTEXITCODE; Write-Host \"`n[Build log: $log]\"; exit $exitCode"
    if errorlevel 1 (
        echo.
        echo   [!] Build failed. Please check the log above.
        if "%QL_NO_PAUSE%"=="" pause
        exit /b 1
    )
    if exist "dist\QuickLauncher_Setup_%APP_VERSION%.exe" (
        start "" "dist\QuickLauncher_Setup_%APP_VERSION%.exe"
    )
    exit
)

echo.
echo [Build Info]
echo   Publisher: %APP_PUBLISHER%
echo   Version: %APP_VERSION%

if not defined QL_BUILD_PROFILE set "QL_BUILD_PROFILE=smooth"

REM Build profiles:
REM   smooth (default):   performance-first Win10/11 runtime, keep graphics runtime DLLs and qdirect2d plugin.
REM   balanced:           remove unused modules, skip UPX, exclude extra graphics runtimes.
REM   small:              balanced + UPX executable compression.
if /I "%QL_BUILD_PROFILE%"=="small" (
    if not defined QL_UPX_EXE set "QL_UPX_EXE=1"
    if not defined QL_UPX_RUNTIME set "QL_UPX_RUNTIME=0"
    if not defined QL_KEEP_GRAPHICS_RUNTIME set "QL_KEEP_GRAPHICS_RUNTIME=0"
    if not defined QL_KEEP_DIRECT2D set "QL_KEEP_DIRECT2D=0"
) else if /I "%QL_BUILD_PROFILE%"=="smooth" (
    if not defined QL_UPX_EXE set "QL_UPX_EXE=0"
    if not defined QL_UPX_RUNTIME set "QL_UPX_RUNTIME=0"
    if not defined QL_KEEP_GRAPHICS_RUNTIME set "QL_KEEP_GRAPHICS_RUNTIME=1"
    if not defined QL_KEEP_DIRECT2D set "QL_KEEP_DIRECT2D=1"
) else (
    set "QL_BUILD_PROFILE=balanced"
    if not defined QL_UPX_EXE set "QL_UPX_EXE=0"
    if not defined QL_UPX_RUNTIME set "QL_UPX_RUNTIME=0"
    if not defined QL_KEEP_GRAPHICS_RUNTIME set "QL_KEEP_GRAPHICS_RUNTIME=0"
    if not defined QL_KEEP_DIRECT2D set "QL_KEEP_DIRECT2D=0"
)

echo   Build profile: %QL_BUILD_PROFILE%
echo   Size mode: remove unused Qt/Python modules
echo   UPX exe: %QL_UPX_EXE%
echo   Keep graphics runtime DLLs: %QL_KEEP_GRAPHICS_RUNTIME%
echo   Keep qdirect2d platform plugin: %QL_KEEP_DIRECT2D%
echo.
REM ====================

REM 1. Check Python 3.10+ (recommended)
echo [0/4] Stopping any running QuickLauncher process...
REM Stop QuickLauncher only. Programs launched through it must remain independent.
taskkill /IM QuickLauncher.exe /F >nul 2>&1
powershell -NoProfile -Command "Start-Sleep -Seconds 3" >nul 2>&1
taskkill /IM QuickLauncher.exe /F >nul 2>&1
powershell -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1
tasklist /FI "IMAGENAME eq QuickLauncher.exe" 2>nul | find /I "QuickLauncher.exe" >nul
if not errorlevel 1 (
    echo   [!] QuickLauncher.exe is still running. Please close it manually and retry.
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
    echo   Please install Python 3.12 and ensure python.exe or py.exe is available.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

!SELECTOR_PY! scripts\select_build_python.py --min 3.12 --max 3.12 --prefer "3.12" --explain
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo   [ERROR] Nuitka build requires 64-bit CPython 3.12.
    echo   Python 3.11/3.13 are intentionally skipped because plugin-bundled wxPython is cp312.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

for /f "delims=" %%p in ('!SELECTOR_PY! scripts\select_build_python.py --min 3.12 --max 3.12 --prefer "3.12" --executable') do set "PYTHON_CMD=%%p"
if not defined PYTHON_CMD (
    echo   [X] Failed to select Python interpreter.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)
echo       Build command: !PYTHON_CMD!

REM Write version back to source so Nuitka embeds the correct value into the compiled binary
!PYTHON_CMD! -c "import re,pathlib; p=pathlib.Path('core/version.py'); t=p.read_text(encoding='utf-8'); p.write_text(re.sub(r'APP_VERSION\s*=\s*\"[^\"]+\"', 'APP_VERSION = \"%APP_VERSION%\"', t), encoding='utf-8')" 2>nul
echo   [OK] core/version.py updated to %APP_VERSION%

REM Clean PATH to avoid conflicting C compilers (e.g. 32-bit TDM-GCC or mismatched MinGW)
set "PATH=C:\Windows\system32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0\"
for /f "delims=" %%i in ("!PYTHON_CMD!") do (
    set "PY_DIR=%%~dpi"
    if not "!PY_DIR!"=="" set "PATH=!PATH!;!PY_DIR!;!PY_DIR!\Scripts"
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
!PYTHON_CMD! -m pip install --upgrade pip nuitka ordered-set zstandard PyQt5==5.15.11 PyQt5-Qt5==5.15.2 pynput pywin32 psutil pillow watchdog qrcode numpy -q -i https://pypi.tuna.tsinghua.edu.cn/simple


echo.
echo [3/4] Starting Nuitka compilation (max performance mode)...
echo   [!] This may take several minutes, please wait...

!PYTHON_CMD! scripts\check_glass_background.py
if !ERRORLEVEL! NEQ 0 (
    echo   [ERROR] Pure-Python glass renderer validation failed.
    exit /b 1
)

REM Clean all caches (ensure latest code is used)
echo   Cleaning all build caches...
if exist "dist\QuickLauncher" rmdir /s /q "dist\QuickLauncher"
if exist "dist\QuickLauncher" (
    attrib -R "dist\QuickLauncher\*" /S /D >nul 2>&1
    rmdir /s /q "dist\QuickLauncher" >nul 2>&1
)
if exist "dist\QuickLauncher" (
    echo   [X] Failed to remove old dist\QuickLauncher. Close Explorer/antivirus handles and retry.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)
if exist "dist\main.dist" (
    rmdir /s /q "dist\main.dist" >nul 2>&1
)
if exist "dist\main.dist" (
    attrib -R "dist\main.dist\*" /S /D >nul 2>&1
    rmdir /s /q "dist\main.dist" >nul 2>&1
)
if exist "dist\main.dist" (
    echo   [X] Failed to remove old dist\main.dist. Close Explorer/antivirus handles and retry.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)
if exist "dist\main.build" rmdir /s /q "dist\main.build"
if exist "obfuscated_src" rmdir /s /q "obfuscated_src"
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
del /s /q *.pyc >nul 2>&1
REM Preserve the Nuitka download cache so MinGW/GCC is not re-downloaded every build.
echo   Cache cleanup completed

set "QL_GRAPHICS_EXCLUDES=--noinclude-dlls=opengl32.dll,d3dcompiler_*.dll"
set "QL_VC_RUNTIME_EXCLUDES=--noinclude-dlls=mfc140u.dll,mfc140*.dll --noinclude-dlls=msvcp140.dll,msvcp140_1.dll,msvcp140_2.dll --noinclude-dlls=vcruntime140.dll,vcruntime140_1.dll --noinclude-dlls=concrt140.dll,vcomp140.dll --noinclude-dlls=api-ms-win-crt-*.dll,ucrtbase.dll"
if "%QL_KEEP_GRAPHICS_RUNTIME%"=="1" (
    set "QL_GRAPHICS_EXCLUDES="
    set "QL_VC_RUNTIME_EXCLUDES="
)

REM Nuitka build command - small runtime, with first-frame smoothness guarded by
REM no-UPX default and explicit manifest embedding below.
REM
REM Do NOT add http.server to --nofollow-import-to: core/commands_utils.py
REM uses it for the QR file server, and excluding it leaves the shim
REM core/commands.py with an unresolved relative import. That breaks
REM build_builtin_command_definitions() and the Settings -> Built-in Command
REM Management list ends up empty in the packaged build.
!PYTHON_CMD! -m nuitka ^
    --mingw64 ^
    --standalone ^
    --windows-console-mode=disable ^
    --assume-yes-for-downloads ^
    --include-windows-runtime-dlls=no ^
    --lto=yes ^
    --remove-output ^
    --no-pyi-file ^
    --report=dist\nuitka-report.xml ^
    --windows-icon-from-ico="assets\app.ico" ^
    --enable-plugin=pyqt5 ^
    --include-qt-plugins=platforms ^
    --noinclude-qt-translations ^
    !QL_GRAPHICS_EXCLUDES! ^
    --noinclude-dlls=qt5quick*.dll,qt5qml*.dll,qt5multimedia*.dll,qt5webengine*.dll,qt5webchannel*.dll ^
    --noinclude-dlls=qt5dbus.dll,qt53d*.dll,qt5designer*.dll,qt5help.dll,qt5bluetooth.dll,qt5nfc.dll ^
    --noinclude-dlls=qt5location.dll,qt5positioning.dll,qt5sensors.dll,qt5texttospeech.dll,qt5websockets.dll ^
    --noinclude-dlls=qt5serialport.dll,qt5sql.dll,qt5test.dll,qt5xml*.dll,qt5networkauth.dll,qt5purchasing.dll ^
    --noinclude-dlls=qt5remoteobjects.dll,qt5script*.dll,qt5scxml.dll,qt5virtualkeyboard.dll,qt5charts.dll,qt5datavisualization.dll ^
    --noinclude-dlls=qt5printsupport.dll ^
    --noinclude-dlls=qt5pdf.dll,qt6pdf.dll,libeay32.dll,ssleay32.dll ^
    --noinclude-dlls=_sqlite3.pyd,_decimal.pyd,_lzma.pyd,_bz2.pyd,atl140.dll ^
    !QL_VC_RUNTIME_EXCLUDES! ^
    --company-name="%APP_PUBLISHER%" ^
    --product-name="QuickLauncher" ^
    --file-version="%APP_VERSION%" ^
    --product-version="%APP_VERSION%" ^
    --copyright="Copyright (C) %APP_PUBLISHER%" ^
    --output-dir=dist ^
    --include-data-dir=assets=assets ^
    --include-data-files=modules\action_chain\module.json=modules\action_chain\module.json ^
    --include-data-files=hooks\hooks.dll=hooks\hooks.dll ^
    --include-data-files=third_party_licenses.json=third_party_licenses.json ^
    --include-package=application ^
    --include-package=domain ^
    --include-package=extensions ^
    --include-package=infrastructure ^
    --include-package=modules ^
    --include-package=ui ^
    --include-package=core ^
    --include-package=hooks ^
    --include-package=bootstrap ^
    --include-package=services ^
    --include-package=watchdog ^
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
    --include-module=PIL.ImageFilter ^
    --include-module=PIL.ImageDraw ^
    --include-module=PIL.ImageFont ^
    --include-module=PIL.BmpImagePlugin ^
    --include-module=PIL.GifImagePlugin ^
    --include-module=PIL.IcoImagePlugin ^
    --include-module=PIL.JpegImagePlugin ^
    --include-module=PIL.PngImagePlugin ^
    --include-module=PIL.WebPImagePlugin ^
    --include-module=PyQt5.QtSvg ^
    --include-module=qrcode ^
    --include-module=ctypes.wintypes ^
    --include-module=ssl ^
    --include-module=_ssl ^
    --include-module=_hashlib ^
    --nofollow-import-to=pytest,unittest,tkinter,test,setuptools,pip,distutils,IPython,notebook,matplotlib,scipy,pandas,sklearn,tensorflow,torch,cv2,urllib3,requests,asyncio,pypinyin,smtplib,imaplib,poplib,ftplib,telnetlib,xmlrpc,doctest,pdb,profile,cProfile,pstats,trace,pydoc,wave,audioop,chunk,sunau,aifc,sndhdr,colorsys,imghdr,shelve,dbm,gdbm,yaml ^
    --jobs=%NUMBER_OF_PROCESSORS% ^
    --output-filename=QuickLauncher.exe ^
    main.py

if not exist "dist\main.dist\QuickLauncher.exe" (
    echo.
    echo   [!] Compilation failed! Please check the error messages above.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

!PYTHON_CMD! -c "import os; sz=os.path.getsize('dist/main.dist/QuickLauncher.exe'); assert sz > 1048576, 'exe too small'; print(f'  [OK] QuickLauncher.exe size: {sz//1024} KB')"
if !ERRORLEVEL! NEQ 0 (
    echo   [X] Executable verification failed.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

REM Embed the project manifest when mt.exe is available. Nuitka generates its
REM own Windows metadata, but this manifest explicitly requests PerMonitorV2
REM DPI awareness, which keeps popup geometry and DWM composition stable on
REM mixed-DPI Windows 11 desktops.
set "MT_EXE="
for /f "delims=" %%m in ('where mt.exe 2^>nul') do (
    if not defined MT_EXE set "MT_EXE=%%m"
)
if not defined MT_EXE (
    for /d %%d in ("%ProgramFiles(x86)%\Windows Kits\10\bin\10.*") do (
        if exist "%%d\x64\mt.exe" set "MT_EXE=%%d\x64\mt.exe"
    )
)
if not defined MT_EXE (
    for /d %%d in ("%ProgramFiles(x86)%\Windows Kits\10\bin\10.*") do (
        if exist "%%d\x86\mt.exe" set "MT_EXE=%%d\x86\mt.exe"
    )
)
if not defined MT_EXE (
    if exist "%ProgramFiles(x86)%\Windows Kits\10\bin\x64\mt.exe" set "MT_EXE=%ProgramFiles(x86)%\Windows Kits\10\bin\x64\mt.exe"
)
if not defined MT_EXE (
    if exist "%ProgramFiles(x86)%\Windows Kits\10\bin\x86\mt.exe" set "MT_EXE=%ProgramFiles(x86)%\Windows Kits\10\bin\x86\mt.exe"
)
if not defined MT_EXE (
    for /d %%d in ("%ProgramFiles%\Windows Kits\10\bin\10.*") do (
        if exist "%%d\x64\mt.exe" set "MT_EXE=%%d\x64\mt.exe"
    )
)
if not defined MT_EXE (
    for /d %%d in ("%ProgramFiles%\Windows Kits\10\bin\10.*") do (
        if exist "%%d\x86\mt.exe" set "MT_EXE=%%d\x86\mt.exe"
    )
)
if defined MT_EXE (
    if exist "QuickLauncher.manifest" (
        echo   Embedding Windows manifest...
        "!MT_EXE!" -manifest "QuickLauncher.manifest" -outputresource:"dist\main.dist\QuickLauncher.exe;#1" >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            echo   [OK] Manifest embedded
        ) else (
            echo   [Warning] Manifest embedding failed, continuing
        )
    )
) else (
    echo   [Info] mt.exe not found; skipping manifest embedding
)

REM Cleanup temporary build files
if exist "dist\main.build" (
    echo   Cleaning temporary build files...
    rmdir /s /q "dist\main.build" >nul 2>&1
)

REM Runtime DLL policy is controlled by QL_KEEP_GRAPHICS_RUNTIME above.
echo   Runtime DLL cleanup policy applied
cd dist\main.dist

REM Remove unnecessary Qt modules and MFC
echo   Cleaning unnecessary Qt modules and MFC...
del /f /q qt5pdf.dll qt6pdf.dll qt5quick*.dll qt5qml*.dll qt5multimedia*.dll qt5dbus.dll qt53d*.dll 2>nul
del /f /q qt5designer*.dll qt5help.dll qt5location.dll qt5positioning.dll qt5sensors.dll 2>nul
del /f /q qt5serialport.dll qt5sql.dll qt5test.dll qt5xml*.dll qt5xmlpatterns.dll 2>nul
del /f /q qt5webengine*.dll qt5webchannel*.dll qt5websockets.dll qt5bluetooth.dll qt5nfc.dll 2>nul
del /f /q qt5texttospeech.dll qt5networkauth.dll qt5script*.dll qt5virtualkeyboard.dll 2>nul
del /f /q qt5printsupport.dll 2>nul
del /f /q mfc140*.dll atl140.dll 2>nul
del /f /q libeay32.dll ssleay32.dll 2>nul
REM Remove OpenSSL 1.1 leftovers (transitive deps from pynput/urllib3).
REM CPython 3.12 ssl module links libssl-3 only; libssl-1_1 is dead weight.
del /f /q libssl-1_1-x64.dll 2>nul
del /f /q libcrypto-1_1-x64.dll 2>nul
del /f /q _sqlite3.pyd 2>nul
del /f /q _decimal.pyd _lzma.pyd _bz2.pyd 2>nul
REM Python urllib-based URL latency and favicon fetching require OpenSSL.
if exist "_ssl.pyd" (
    if not exist "libssl-3.dll" (
        echo   [X] Missing libssl-3.dll required for HTTPS URL latency.
        cd ..\..
        if "%QL_NO_PAUSE%"=="" pause
        exit /b 1
    )
    if not exist "libcrypto-3.dll" (
        echo   [X] Missing libcrypto-3.dll required for HTTPS URL latency.
        cd ..\..
        if "%QL_NO_PAUSE%"=="" pause
        exit /b 1
    )
)
if exist "PyQt5" (
    del /f /q PyQt5\QtPdf.pyd PyQt5\QtQuick*.pyd PyQt5\QtQml*.pyd PyQt5\QtMultimedia*.pyd 2>nul
    del /f /q PyQt5\QtDesigner*.pyd PyQt5\QtHelp.pyd PyQt5\QtSql.pyd PyQt5\QtTest.pyd PyQt5\QtXml*.pyd 2>nul
    del /f /q PyQt5\QtPrintSupport.pyd 2>nul
)

REM Remove unnecessary platform plugins (keep qwindows only)
echo   Cleaning unnecessary platform plugins...
if exist "PyQt5\qt-plugins\platforms" (
    if not "%QL_KEEP_DIRECT2D%"=="1" del /f /q PyQt5\qt-plugins\platforms\qdirect2d.dll 2>nul
    del /f /q PyQt5\qt-plugins\platforms\qoffscreen.dll 2>nul
    del /f /q PyQt5\qt-plugins\platforms\qminimal.dll 2>nul
)

REM Remove styles plugins (use system default)
if exist "PyQt5\qt-plugins\styles" (
    rmdir /s /q PyQt5\qt-plugins\styles 2>nul
)

REM Remove Qt TLS plugins; URL latency uses Python OpenSSL DLLs above.
if exist "PyQt5\qt-plugins\tls" (
    rmdir /s /q PyQt5\qt-plugins\tls 2>nul
)

REM Remove unnecessary image format plugins (keep ico/png/jpg/gif/webp/bmp/svg)
echo   Cleaning unnecessary image format plugins...
if exist "PyQt5\qt-plugins\imageformats" (
    del /f /q PyQt5\qt-plugins\imageformats\qtiff.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qicns.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qwbmp.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qtga.dll 2>nul
    del /f /q PyQt5\qt-plugins\imageformats\qpdf.dll 2>nul
)

REM Keep SVG runtime/plugins: favicon fallback can render inline SVG logos.

REM Remove XDG desktop portal plugin (Linux-only, useless on Windows)
if exist "PyQt5\qt-plugins\platformthemes" (
    del /f /q PyQt5\qt-plugins\platformthemes\qxdgdesktopportal.dll 2>nul
)

REM Remove unnecessary PIL submodules
echo   Cleaning unnecessary PIL submodules...
if exist "PIL" (
    del /f /q PIL\_avif.pyd PIL\_imagingcms.pyd PIL\_imagingtk.pyd 2>nul
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

REM Remove scipy-openblas runtime; numpy falls back to internal reference BLAS.
REM glass_background.py only uses np.mgrid/clip/asarray/maximum and does not
REM need OpenBLAS; every numpy import is wrapped in try/except with a pure
REM Python fallback, so the visual pipeline is bit-for-bit identical.
REM IMPORTANT: keep numpy.libs/msvcp140-*.dll.  numpy's C extensions
REM (_multiarray_umath.pyd, etc.) link against this hash-suffixed VC++
REM runtime; removing it forces numpy to fall back to a non-SIMD / single-
REM threaded dispatch for ufuncs, and the per-frame saturation + tint ops
REM in glass_background._render_frame drop from ~60 FPS to ~10-15 FPS,
REM which is visible as lag while moving the popup or paging through it.
if exist "numpy.libs\libscipy_openblas64_*.dll" (
    del /f /q "numpy.libs\libscipy_openblas64_*.dll" 2>nul
    echo   [OK] Removed scipy-openblas runtime (~20 MB)
    echo   [OK] Preserved numpy.libs\msvcp140-*.dll to keep numpy SIMD dispatch enabled.
) else (
    echo   [Info] numpy.libs\libscipy_openblas64_*.dll not present, skipping.
)

REM Remove unused yaml runtime (Nuitka may have inlined loader/dumper, but
REM _yaml.pyd can still be present).  Source has 0 import yaml sites.
if exist "yaml" rmdir /s /q "yaml" 2>nul

REM Remove test and debug directories
if exist "lib\test" rmdir /s /q lib\test 2>nul
if exist "lib\unittest" rmdir /s /q lib\unittest 2>nul

cd ..\..
cd /d "%~dp0.."

REM Stage output folder. Copy instead of rename because Nuitka/Defender can
REM briefly keep handles under main.dist, which makes directory rename fail.
set "QL_STAGE_OK="
for /L %%R in (1,1,10) do (
    if not defined QL_STAGE_OK (
        if exist "dist\QuickLauncher" rmdir /s /q "dist\QuickLauncher" >nul 2>&1
        robocopy "dist\main.dist" "dist\QuickLauncher" /MIR /NFL /NDL /NJH /NJS /NP >nul
        if exist "dist\QuickLauncher\QuickLauncher.exe" (
            if !ERRORLEVEL! LSS 8 set "QL_STAGE_OK=1"
        )
        if not defined QL_STAGE_OK powershell -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1
    )
)
if not defined QL_STAGE_OK (
    echo   [X] Failed to stage dist\main.dist into dist\QuickLauncher.
    echo   [X] A file lock or stale dist\QuickLauncher directory is blocking the build.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

REM UPX compression. Disabled by default because UPX decompression can make the
REM first visible Qt/DWM frame noticeably worse in the packaged build.
if not "%QL_UPX_EXE%"=="1" (
    echo   [Info] UPX skipped for smoother popup first-frame rendering. Set QL_UPX_EXE=1 to enable.
    goto :after_upx
)

echo   UPX compressing executable...
if not exist "upx.exe" (
    echo   [Warning] upx.exe not found, skipping compression
    goto :after_upx
)

upx.exe --best --lzma dist\QuickLauncher\QuickLauncher.exe >nul 2>&1
if "%QL_UPX_RUNTIME%"=="1" (
        upx.exe --best --lzma dist\QuickLauncher\python*.dll >nul 2>&1
        upx.exe --best --lzma dist\QuickLauncher\qt5*.dll >nul 2>&1
        upx.exe --best --lzma dist\QuickLauncher\*.pyd >nul 2>&1
        if exist "dist\QuickLauncher\PyQt5" upx.exe --best --lzma dist\QuickLauncher\PyQt5\*.pyd >nul 2>&1
        if exist "dist\QuickLauncher\PIL" upx.exe --best --lzma dist\QuickLauncher\PIL\*.pyd >nul 2>&1
        if exist "dist\QuickLauncher\psutil" upx.exe --best --lzma dist\QuickLauncher\psutil\*.pyd >nul 2>&1
        if exist "dist\QuickLauncher\win32com\shell" upx.exe --best --lzma dist\QuickLauncher\win32com\shell\*.pyd >nul 2>&1
    echo   [OK] UPX compression completed (executable + runtime binaries)
) else (
    echo   [OK] UPX compression completed (executable only)
    echo   [Info] Runtime DLL/PYD UPX skipped for smoother first-use animations. Set QL_UPX_RUNTIME=1 to enable.
)
:after_upx

REM Copy required resources
echo   Copying resource files...
if exist "assets\app.ico" (
    copy /Y "assets\app.ico" "dist\QuickLauncher\" >nul
) else if exist "scripts\app.ico" (
    copy /Y "scripts\app.ico" "dist\QuickLauncher\" >nul
) else (
    echo   [Warning] app.ico not found, skipping copy.
)

if exist "assets\support.webp" (
    if not exist "dist\QuickLauncher\assets" mkdir "dist\QuickLauncher\assets" >nul 2>&1
    copy /Y "assets\support.webp" "dist\QuickLauncher\assets\support.webp" >nul
) else (
    echo   [Warning] assets\support.webp not found, support dialog will use fallback placeholder.
)

REM Remove developer-only markdown from runtime; the source copy under
REM assets/system_icons/README.md stays in the GitHub repo.
if exist "dist\QuickLauncher\assets\system_icons\README.md" del /f /q "dist\QuickLauncher\assets\system_icons\README.md"
if exist "dist\QuickLauncher\PLUGIN_DEV.md" del /f /q "dist\QuickLauncher\PLUGIN_DEV.md"

REM Runtime plugins are installed by users from .qlzip packages. The packaged
REM app ships only an empty plugins directory as the installation target.
echo   Creating empty plugin installation directory...
if exist "dist\QuickLauncher\plugins" rmdir /s /q "dist\QuickLauncher\plugins" >nul 2>&1
mkdir "dist\QuickLauncher\plugins" >nul 2>&1
if not exist "dist\QuickLauncher\plugins" (
    echo   [X] Failed to create plugin installation directory.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)
echo   [OK] Plugin installation directory ready.

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

REM Create portable zip package
echo.
echo [5/5] Creating portable zip package...
set "PORTABLE_NAME=QuickLauncher_Portable_%APP_VERSION%"
if exist "%PORTABLE_NAME%" if not exist "%PORTABLE_NAME%\" (
    del /f /q "%PORTABLE_NAME%" >nul 2>&1
    if exist "%PORTABLE_NAME%" (
        echo   [!] Failed to remove stale root marker %PORTABLE_NAME%.
        if "%QL_NO_PAUSE%"=="" pause
        exit /b 1
    )
)
if exist "dist\%PORTABLE_NAME%\" (
    rmdir /s /q "dist\%PORTABLE_NAME%" >nul 2>&1
    if exist "dist\%PORTABLE_NAME%\" (
        echo   [!] Failed to remove stale portable folder dist\%PORTABLE_NAME%.
        if "%QL_NO_PAUSE%"=="" pause
        exit /b 1
    )
)
if exist "dist\%PORTABLE_NAME%" (
    del /f /q "dist\%PORTABLE_NAME%" >nul 2>&1
    if exist "dist\%PORTABLE_NAME%" (
        echo   [!] Failed to remove stale portable path dist\%PORTABLE_NAME%.
        if "%QL_NO_PAUSE%"=="" pause
        exit /b 1
    )
)
if exist "dist\%PORTABLE_NAME%.zip" (
    del /f /q "dist\%PORTABLE_NAME%.zip" >nul 2>&1
    if exist "dist\%PORTABLE_NAME%.zip" (
        echo   [!] Failed to remove stale portable zip dist\%PORTABLE_NAME%.zip.
        if "%QL_NO_PAUSE%"=="" pause
        exit /b 1
    )
)
ren "dist\QuickLauncher" "%PORTABLE_NAME%"
if !ERRORLEVEL! NEQ 0 (
    echo   [!] Failed to rename dist\QuickLauncher to %PORTABLE_NAME%.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)
echo   [OK] Renamed dist\QuickLauncher -^> %PORTABLE_NAME%

echo   Compressing to %PORTABLE_NAME%.zip (7-Zip LZMA2 if available)...
set "SEVENZIP="
for %%p in ("%ProgramFiles%\7-Zip\7z.exe" "%ProgramFiles(x86)%\7-Zip\7z.exe" "%LocalAppData%\7-Zip\7z.exe") do (
    if not defined SEVENZIP if exist %%~p set "SEVENZIP=%%~p"
)
if defined SEVENZIP (
    "!SEVENZIP!" a -tzip -mm=LZMA2 -mx=9 -mfb=273 -md=64m -mmt=on "dist\%PORTABLE_NAME%.zip" "dist\%PORTABLE_NAME%\*" -r >nul
    if !ERRORLEVEL! NEQ 0 (
        echo   [Warning] 7-Zip LZMA2 failed, falling back to Compress-Archive
        powershell -NoProfile -Command "Compress-Archive -Path 'dist\%PORTABLE_NAME%' -DestinationPath 'dist\%PORTABLE_NAME%.zip' -Force"
    ) else (
        echo   [OK] 7-Zip LZMA2 zip created.
    )
) else (
    echo   [Warning] 7-Zip not found, falling back to Compress-Archive (Deflate)
    powershell -NoProfile -Command "Compress-Archive -Path 'dist\%PORTABLE_NAME%' -DestinationPath 'dist\%PORTABLE_NAME%.zip' -Force"
)
if !ERRORLEVEL! NEQ 0 (
    echo   [!] Failed to create zip package.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)
echo   [OK] Portable zip created: dist\%PORTABLE_NAME%.zip

echo.
echo   Verifying final installer and portable artifacts...
!PYTHON_CMD! scripts\check_release_artifacts.py --version "%APP_VERSION%" --dist-dir "dist\%PORTABLE_NAME%" --installer "dist\QuickLauncher_Setup_%APP_VERSION%.exe" --portable-zip "dist\%PORTABLE_NAME%.zip" --allow-source-runtime-plugins --run-smoke --write-manifest "dist\QuickLauncher_release_%APP_VERSION%.json" --write-installer-sha256 "dist\QuickLauncher_Setup_%APP_VERSION%.sha256" --write-portable-sha256 "dist\%PORTABLE_NAME%.sha256"
if !ERRORLEVEL! NEQ 0 (
    echo   [!] Final release artifact verification failed.
    if "%QL_NO_PAUSE%"=="" pause
    exit /b 1
)

echo.
echo ========================================
echo   [OK] Build successful! (Win11 optimized version)
echo   Installer: dist\QuickLauncher_Setup_%APP_VERSION%.exe
echo   Portable:  dist\%PORTABLE_NAME%.zip
echo ========================================
