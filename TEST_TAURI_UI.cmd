@echo off
setlocal

cd /d "%~dp0"

set "TAURI_EXE=%~dp0frontend\tauri-spike\src-tauri\target\release\desktop-support-tauri-spike.exe"
set "BUILD_SCRIPT=%~dp0scripts\tauri\build_desktop_app.ps1"

echo.
echo Desktop Support - Tauri UI test launcher
echo Project: %~dp0
echo.

if exist "%TAURI_EXE%" goto run_tauri

echo New Tauri UI exe was not found:
echo %TAURI_EXE%
echo.

if not exist "%BUILD_SCRIPT%" (
    echo Build script was not found:
    echo %BUILD_SCRIPT%
    echo.
    pause
    exit /b 1
)

choice /m "Build the Tauri release exe now"
if errorlevel 2 exit /b 1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BUILD_SCRIPT%" -Configuration Release
if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

:run_tauri
echo Starting new Tauri dock UI...
echo %TAURI_EXE%
echo.

start "Desktop Support Tauri" /D "%~dp0" "%TAURI_EXE%"
exit /b 0
