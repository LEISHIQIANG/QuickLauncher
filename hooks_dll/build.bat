@echo off
setlocal

echo Checking MSVC environment...

set "VCPATH_E=E:\Visual Studio 2026\VC\Tools\MSVC\14.50.35717"
set "VCPATH_D=D:\Visual Studio3\VC\Tools\MSVC\14.50.35717"

if exist "%VCPATH_E%\bin\Hostx64\x64\cl.exe" (
    set "VCPATH=%VCPATH_E%"
    echo Using MSVC from E drive
) else if exist "%VCPATH_D%\bin\Hostx64\x64\cl.exe" (
    set "VCPATH=%VCPATH_D%"
    echo Using MSVC from D drive
) else (
    echo ERROR: Visual Studio MSVC was not found.
    exit /b 1
)

set "WKPATH=C:\Program Files (x86)\Windows Kits\10"
if not exist "%WKPATH%\Include" (
    set "WKPATH=D:\Windows Kits\10"
)
if not exist "%WKPATH%\Include" (
    echo ERROR: Windows SDK was not found.
    exit /b 1
)

set "SDKVER="
for /f %%i in ('dir /b /ad "%WKPATH%\Include" 2^>nul ^| findstr "10.0"') do set "SDKVER=%%i"

if not defined SDKVER (
    echo ERROR: no valid Windows SDK version was found.
    exit /b 1
)

echo Using SDK: %SDKVER%

set "INCLUDE=%VCPATH%\include;%WKPATH%\Include\%SDKVER%\ucrt;%WKPATH%\Include\%SDKVER%\um;%WKPATH%\Include\%SDKVER%\shared"
set "LIB=%VCPATH%\lib\x64;%WKPATH%\Lib\%SDKVER%\ucrt\x64;%WKPATH%\Lib\%SDKVER%\um\x64"
set "PATH=%VCPATH%\bin\Hostx64\x64;%PATH%"

echo Building hooks.dll...
cl.exe /LD /O2 /EHsc /std:c++17 /utf-8 hooks.cpp /Fe..\hooks\hooks.dll /link /implib:hooks.lib user32.lib kernel32.lib

if errorlevel 1 (
    echo ERROR: build failed.
    exit /b 1
)

del hooks.obj hooks.exp hooks.lib 2>nul
del ..\hooks\hooks.exp ..\hooks\hooks.lib 2>nul

echo Build succeeded: ..\hooks\hooks.dll
exit /b 0
