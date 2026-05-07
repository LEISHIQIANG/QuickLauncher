@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."
chcp 65001 >nul
echo ========================================
echo QuickLauncher Win7 兼容版 - 安装包制作
echo ========================================
echo.
echo [!] 注意：此脚本专为 Windows 7/8 优化
echo [!] 必须使用 Python 3.8 + PyQt5 环境
echo.

REM === 版本信息配置 ===
set "APP_PUBLISHER=Layton"
set /p "APP_VERSION=请输入版本号 (默认 2.6.7.5): "
if "%APP_VERSION%"=="" set "APP_VERSION=2.6.7.5"

echo.
echo [信息确认]
echo   公司名称: %APP_PUBLISHER%
echo   软件版本: %APP_VERSION%
echo.
REM ====================

echo 步骤 1: 环境检测与修复
echo.

REM 1. 检测 Python 3.8 (Win7 最后支持的版本)
echo [1/4] 检测 Python 3.8...
set "PYTHON_CMD="

REM 优先尝试 py launcher
py -3.8 --version >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=py -3.8"
    echo   ✓ 发现 Python 3.8 (via py launcher^)
    goto :FoundPython
)

REM 尝试直接查找 python
python --version 2>&1 | findstr " 3.8" >nul
if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=python"
    echo   ✓ 发现 Python 3.8 (当前 PATH)
    goto :FoundPython
)

:NotFoundPython
echo   ✗ 未找到 Python 3.8
echo.
echo   [!] 必须使用 Python 3.8 才能兼容 Windows 7。
echo   [!] 请安装 Python 3.8.10 (勾选 Add to PATH) 后重试。
pause
exit /b 1

:FoundPython

REM 2. 检测 Inno Setup
set "ISCC="
if exist "E:\Inno Setup 6\ISCC.exe" set "ISCC=E:\Inno Setup 6\ISCC.exe"
if exist "D:\Inno Setup 6\ISCC.exe" set "ISCC=D:\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo   ✗ Inno Setup 未安装！无法生成安装包。
    echo   请安装 Inno Setup 6 ^(Unicode^) 后重试。
    pause
    exit /b 1
)
echo   ✓ 发现 Inno Setup: !ISCC!

echo.
echo 步骤 2: 配置 Win7 兼容环境 (PyQt5)
echo.

REM 临时清除代理
REM set "HTTP_PROXY="
REM set "HTTPS_PROXY="

echo [2/4] 安装/修复依赖...
echo   正在更新 pip...
!PYTHON_CMD! -m pip install --upgrade pip -q -i https://pypi.tuna.tsinghua.edu.cn/simple

echo   正在安装 PyQt5 和其他 Win7 兼容依赖...
!PYTHON_CMD! -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
!PYTHON_CMD! -m pip install pyinstaller -q -i https://pypi.tuna.tsinghua.edu.cn/simple


echo.
echo 步骤 3: 编译核心程序 (PyInstaller + PyQt5)
echo.
echo [3/4] PyInstaller 打包中...

REM 清理旧构建
if exist "dist\QuickLauncher" rmdir /s /q "dist\QuickLauncher"
if exist "build" rmdir /s /q "build"

REM PyInstaller 打包 (使用 Win7 兼容参数)
!PYTHON_CMD! -m PyInstaller scripts\QuickLauncher.spec --clean --noconfirm

if not exist "dist\QuickLauncher\QuickLauncher.exe" (
    echo.
    echo   ✗ 打包失败！请检查上方错误信息。
    pause
    exit /b 1
)

echo.
echo 步骤 4: 制作安装包 (Inno Setup)
echo.
echo [4/4] 生成 Win7 安装包...

"!ISCC!" /DMyAppName="QuickLauncher" /DMyAppVersion="%APP_VERSION%" /DMyAppFileVersion="%APP_VERSION%" /DMyAppPublisher="%APP_PUBLISHER%" /DOutputBaseFilename="QuickLauncher_Setup_%APP_VERSION%-Win7" scripts\installer.iss
if !ERRORLEVEL! NEQ 0 (
    echo   ✗ 安装包生成失败。
    pause
    exit /b 1
)

echo.
echo ========================================
echo   ★ 构建成功！(Win7 兼容版)
echo   安装包: dist\QuickLauncher_Setup_%APP_VERSION%-Win7.exe
echo ========================================
pause
exit /b 0

:RestartScript
cls
"%~f0"
exit /b
