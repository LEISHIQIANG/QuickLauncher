@echo off
cd /d "%~dp0.."

echo.
echo ========================================
echo   Clean Build Cache
echo ========================================
echo.

REM Clean Python bytecode cache
echo [1/7] Cleaning Python bytecode cache...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc >nul 2>&1
echo   Done

REM Clean obfuscated output
echo [2/7] Cleaning obfuscated output...
if exist "obfuscated_src" rd /s /q "obfuscated_src"
echo   Done

REM Clean Nuitka cache
echo [3/7] Cleaning Nuitka cache...
if exist "dist\main.build" rd /s /q "dist\main.build"
if exist "dist\main.dist" rd /s /q "dist\main.dist"
echo   Done

REM Clean old build output
echo [4/7] Cleaning old build output...
if exist "dist\QuickLauncher" rd /s /q "dist\QuickLauncher"
if exist "build" rd /s /q "build"
if exist "scripts\dist" rd /s /q "scripts\dist"
if exist "scripts\build" rd /s /q "scripts\build"
echo   Done

REM Clean hook DLL intermediate files
echo [5/7] Cleaning hook DLL intermediates...
if exist "hooks_dll\hooks.obj" del /f /q "hooks_dll\hooks.obj" 2>nul
if exist "hooks_dll\hooks_build.dll" del /f /q "hooks_dll\hooks_build.dll" 2>nul
if exist "hooks_dll\hooks_build.exp" del /f /q "hooks_dll\hooks_build.exp" 2>nul
if exist "hooks_dll\hooks_build.lib" del /f /q "hooks_dll\hooks_build.lib" 2>nul
echo   Done

REM Clean temporary reports
echo [6/7] Cleaning temporary reports...
if exist "nuitka-crash-report.xml" del /f /q "nuitka-crash-report.xml" 2>nul
echo   Done

REM Clean Nuitka global cache (optional)
echo [7/7] Cleaning Nuitka global cache...
if exist "%LOCALAPPDATA%\Nuitka\Nuitka\Cache" (
    rd /s /q "%LOCALAPPDATA%\Nuitka\Nuitka\Cache" 2>nul
    echo   Done
) else (
    echo   Not found
)

echo.
echo ========================================
echo   Clean Complete!
echo ========================================
echo.
echo Now you can run build_encrypted.bat or build_win11_setup.bat
echo.
pause
