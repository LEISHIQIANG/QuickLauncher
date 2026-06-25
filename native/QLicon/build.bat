@echo off
setlocal
pushd "%~dp0" || exit /b 1
echo Checking MSVC environment...
set "VCPATH="
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
    for /f "usebackq delims=" %%r in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
        if not defined VCPATH (
            for /f "delims=" %%i in ('dir /b /ad /o-n "%%~r\VC\Tools\MSVC" 2^>nul') do (
                if not defined VCPATH if exist "%%~r\VC\Tools\MSVC\%%i\bin\Hostx64\x64\cl.exe" (
                    set "VCPATH=%%~r\VC\Tools\MSVC\%%i"
                )
            )
        )
    )
    for /f "usebackq delims=" %%r in (`"%VSWHERE%" -latest -products * -property installationPath`) do (
        if not defined VCPATH (
            for /f "delims=" %%i in ('dir /b /ad /o-n "%%~r\VC\Tools\MSVC" 2^>nul') do (
                if not defined VCPATH if exist "%%~r\VC\Tools\MSVC\%%i\bin\Hostx64\x64\cl.exe" (
                    set "VCPATH=%%~r\VC\Tools\MSVC\%%i"
                )
            )
        )
    )
)
for %%r in ("E:\Visual Studio 2026" "D:\Visual Studio3" "C:\Program Files\Microsoft Visual Studio\18\Community" "C:\Program Files\Microsoft Visual Studio\18\BuildTools" "C:\Program Files\Microsoft Visual Studio\2026\Community" "C:\Program Files\Microsoft Visual Studio\2022\Community" "C:\Program Files\Microsoft Visual Studio\2022\BuildTools") do (
    if not defined VCPATH (
        for /f "delims=" %%i in ('dir /b /ad /o-n "%%~r\VC\Tools\MSVC" 2^>nul') do (
            if not defined VCPATH if exist "%%~r\VC\Tools\MSVC\%%i\bin\Hostx64\x64\cl.exe" (
                set "VCPATH=%%~r\VC\Tools\MSVC\%%i"
            )
        )
    )
)
if not defined VCPATH ( echo ERROR: Visual Studio MSVC was not found. && exit /b 1 )
echo Using MSVC: %VCPATH%
set "WKPATH=C:\Program Files (x86)\Windows Kits\10"
if not exist "%WKPATH%\Include" set "WKPATH=D:\Windows Kits\10"
if not exist "%WKPATH%\Include" ( echo ERROR: Windows SDK was not found. && exit /b 1 )
set "SDKVER="
for /f %%i in ('dir /b /ad "%WKPATH%\Include" 2^>nul ^| findstr "10.0"') do set "SDKVER=%%i"
if not defined SDKVER ( echo ERROR: no valid Windows SDK version was found. && exit /b 1 )
echo Using SDK: %SDKVER%
set "INCLUDE=%VCPATH%\include;%WKPATH%\Include\%SDKVER%\ucrt;%WKPATH%\Include\%SDKVER%\um;%WKPATH%\Include\%SDKVER%\shared"
set "LIB=%VCPATH%\lib\x64;%WKPATH%\Lib\%SDKVER%\ucrt\x64;%WKPATH%\Lib\%SDKVER%\um\x64"
set "PATH=%VCPATH%\bin\Hostx64\x64;%PATH%"
echo Building QLicon.dll...
cl.exe /LD /O2 /EHsc /std:c++17 /utf-8 QLicon.cpp /FeQLicon.dll /link /implib:QLicon.lib user32.lib shell32.lib gdi32.lib kernel32.lib
if errorlevel 1 ( echo ERROR: build failed. && exit /b 1 )
del QLicon.obj QLicon.exp QLicon.lib 2>nul
echo Build succeeded: QLicon.dll
popd
exit /b 0

