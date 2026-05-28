@echo off
setlocal

cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\run_launcher.ps1" -Restart -ShowDock
set "CODE=%ERRORLEVEL%"

if "%CODE%"=="0" exit /b 0

echo.
echo Engineering Launcher failed to start. Startup logs:
echo %LOCALAPPDATA%\EngineeringLauncher\logs\launcher_startup.log
echo %~dp0logs\launcher_startup.log
echo.
if exist "%LOCALAPPDATA%\EngineeringLauncher\logs\launcher_startup.log" (
    type "%LOCALAPPDATA%\EngineeringLauncher\logs\launcher_startup.log"
) else if exist "%~dp0logs\launcher_startup.log" (
    type "%~dp0logs\launcher_startup.log"
) else (
    echo No startup log was found.
)
echo.
pause
exit /b %CODE%
