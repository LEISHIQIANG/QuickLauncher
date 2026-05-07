@echo off
chcp 65001 >nul
echo 检测编译环境...

:: 检测当前电脑的 MSVC 路径
set "VCPATH_E=E:\Visual Studio 2026\VC\Tools\MSVC\14.50.35717"
set "VCPATH_D=D:\Visual Studio3\VC\Tools\MSVC\14.50.35717"

if exist "%VCPATH_E%\bin\Hostx64\x64\cl.exe" (
    set "VCPATH=%VCPATH_E%"
    echo 使用 E 盘 Visual Studio
) else if exist "%VCPATH_D%\bin\Hostx64\x64\cl.exe" (
    set "VCPATH=%VCPATH_D%"
    echo 使用 D 盘 Visual Studio
) else (
    echo 错误: 未找到 Visual Studio
    pause
    exit /b 1
)

:: 检测 Windows SDK
set "WKPATH=C:\Program Files (x86)\Windows Kits\10"
if not exist "%WKPATH%\Include" (
    set "WKPATH=D:\Windows Kits\10"
)
if not exist "%WKPATH%\Include" (
    echo 错误: 未找到 Windows SDK
    pause
    exit /b 1
)

:: 查找 SDK 版本
for /f %%i in ('dir /b /ad "%WKPATH%\Include" 2^>nul ^| findstr "10.0"') do set "SDKVER=%%i"

if not defined SDKVER (
    echo 错误: 未找到有效的 SDK 版本
    pause
    exit /b 1
)

echo 使用 SDK: %SDKVER%
echo.

:: 设置环境变量
set "INCLUDE=%VCPATH%\include;%WKPATH%\Include\%SDKVER%\ucrt;%WKPATH%\Include\%SDKVER%\um;%WKPATH%\Include\%SDKVER%\shared"
set "LIB=%VCPATH%\lib\x64;%WKPATH%\Lib\%SDKVER%\ucrt\x64;%WKPATH%\Lib\%SDKVER%\um\x64"
set "PATH=%VCPATH%\bin\Hostx64\x64;%PATH%"

echo 编译中...
cl.exe /LD /O2 /EHsc /std:c++17 /DHOOKS_EXPORTS hooks.cpp /Fe..\hooks\hooks.dll /link user32.lib kernel32.lib

if errorlevel 1 (
    echo.
    echo 编译失败
    pause
    exit /b 1
)

del hooks.obj hooks.exp hooks.lib 2>nul
echo.
echo ========================================
echo 编译成功！hooks.dll 已生成
echo ========================================
pause
