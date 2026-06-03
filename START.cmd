@echo off
setlocal

cd /d "%~dp0"

set "TAURI_EXE=%~dp0frontend\tauri-spike\src-tauri\target\release\desktop-support-tauri-spike.exe"

if exist "%TAURI_EXE%" (
    wscript.exe "%~dp0START.vbs"
    exit /b 0
)

echo.
echo Desktop Support Tauri exe was not found:
echo %TAURI_EXE%
echo.
echo Build it first:
echo powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\tauri\build_desktop_app.ps1" -Configuration Release
echo.
pause
exit /b 1
