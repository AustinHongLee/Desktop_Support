@echo off
setlocal

for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

echo TEST_TAURI_UI.cmd is a compatibility shortcut.
echo This starts the Tauri dev/test UI for PyQt-to-Tauri migration work.
echo Canonical test entry:
echo powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\scripts\test.ps1" -Suite tauri-ui
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\scripts\test.ps1" -Suite tauri-ui
exit /b %ERRORLEVEL%
