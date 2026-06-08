@echo off
setlocal

for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\scripts\launcher\run_launcher.ps1" -ShowDock
exit /b %ERRORLEVEL%
