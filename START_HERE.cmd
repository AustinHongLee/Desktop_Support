@echo off
setlocal

cd /d "%~dp0"

echo.
echo Desktop Support
echo ===============
echo.
echo 1. Start Desktop Support
echo 2. Debug startup
echo 3. Right-click menu manager
echo 4. Run unit tests
echo 5. Tauri dev/test UI
echo 6. Check dev environment
echo Q. Quit
echo.

choice /C 123456Q /N /M "Choose an action: "
set "CHOICE_CODE=%ERRORLEVEL%"

if "%CHOICE_CODE%"=="1" goto start_app
if "%CHOICE_CODE%"=="2" goto debug_app
if "%CHOICE_CODE%"=="3" goto right_click
if "%CHOICE_CODE%"=="4" goto run_tests
if "%CHOICE_CODE%"=="5" goto tauri_ui
if "%CHOICE_CODE%"=="6" goto dev_env

exit /b 0

:start_app
wscript.exe "%~dp0scripts\shortcuts\start_desktop.vbs"
exit /b 0

:debug_app
call "%~dp0scripts\shortcuts\start_debug.cmd"
exit /b %ERRORLEVEL%

:right_click
wscript.exe "%~dp0scripts\shortcuts\right_click_manager.vbs"
exit /b 0

:run_tests
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test.ps1" -Suite unit
exit /b %ERRORLEVEL%

:tauri_ui
call "%~dp0scripts\shortcuts\test_tauri_ui.cmd"
exit /b %ERRORLEVEL%

:dev_env
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test.ps1" -Suite env
set "DEV_ENV_ERROR=%ERRORLEVEL%"
echo.
pause
exit /b %DEV_ENV_ERROR%
