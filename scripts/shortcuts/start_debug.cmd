@echo off
setlocal

for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

echo Engineering Launcher debug startup
echo Project: %CD%
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\scripts\launcher\run_launcher.ps1" -Foreground -Restart -ShowDock
set "CODE=%ERRORLEVEL%"

echo.
echo Launcher process exited with code %CODE%.
echo Startup log:
echo %LOCALAPPDATA%\EngineeringLauncher\logs\launcher_startup.log
echo %PROJECT_ROOT%\logs\launcher_startup.log
echo.
if exist "%LOCALAPPDATA%\EngineeringLauncher\logs\launcher_startup.log" (
    type "%LOCALAPPDATA%\EngineeringLauncher\logs\launcher_startup.log"
) else if exist "%PROJECT_ROOT%\logs\launcher_startup.log" (
    type "%PROJECT_ROOT%\logs\launcher_startup.log"
) else (
    echo No startup log was found.
)
echo.
pause
exit /b %CODE%
