param(
    [switch]$SkipNpmInstall,
    [switch]$NativeOnly,
    [switch]$NoAutoOpenBrowser
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendRoot = Join-Path $ProjectRoot "frontend\tauri-spike"
$FallbackUrl = "http://127.0.0.1:1420/?surface=dock"
$SharedRoot = Join-Path $ProjectRoot "scripts\_shared"

. (Join-Path $SharedRoot "path_utils.ps1")
. (Join-Path $SharedRoot "vs_env.ps1")
Add-CargoBinToProcessPath

function Invoke-NpmInstallIfNeeded {
    if ($SkipNpmInstall -or (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
        return
    }

    Push-Location $FrontendRoot
    try {
        & $npm.Source ci
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}

function Start-BrowserFallback {
    param([string]$Reason)

    if ($NativeOnly) {
        throw $Reason
    }

    Write-Host "[tauri-dev] Native Tauri cannot start: $Reason" -ForegroundColor Yellow
    Write-Host "[tauri-dev] Starting browser fallback for the React/Tauri migration UI." -ForegroundColor Yellow
    Write-Host "[tauri-dev] Open: $FallbackUrl" -ForegroundColor Cyan
    Write-Host "[tauri-dev] Native tray/window APIs still require the Visual Studio C++ toolchain." -ForegroundColor Yellow
    if (-not $NoAutoOpenBrowser) {
        $openCommand = "Start-Sleep -Seconds 2; Start-Process '$FallbackUrl'"
        Start-Process -FilePath powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $openCommand) -WindowStyle Hidden | Out-Null
        Write-Host "[tauri-dev] Browser fallback will open automatically." -ForegroundColor Cyan
    }

    Push-Location $FrontendRoot
    try {
        & $npm.Source run dev
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

$npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
if (-not $npm) {
    throw "Missing command: npm.cmd. Install Node.js before running the Tauri dev UI."
}

Invoke-NpmInstallIfNeeded

$cargo = Get-Command "cargo.exe" -ErrorAction SilentlyContinue
if (-not $cargo) {
    Start-BrowserFallback "cargo.exe was not found. Install Rust to run the native Tauri shell."
}

$link = Get-Command "link.exe" -ErrorAction SilentlyContinue
$rc = Get-Command "rc.exe" -ErrorAction SilentlyContinue
$vsDevCmd = $null

if (-not $link -or -not $rc) {
    $vsDevCmd = Find-VsDevCmd
}

if ((-not $link -or -not $rc) -and -not $vsDevCmd) {
    $missingTools = @()
    if (-not $link) {
        $missingTools += "link.exe"
    }
    if (-not $rc) {
        $missingTools += "rc.exe"
    }

    Start-BrowserFallback ("missing {0}. Install Visual Studio Build Tools with Desktop development with C++, MSVC, and Windows SDK, or run from a Developer PowerShell." -f ($missingTools -join ", "))
}

Get-Process -Name "desktop-support-tauri-spike" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

$env:DESKTOP_SUPPORT_PROJECT_ROOT = $ProjectRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Push-Location $FrontendRoot
try {
    Write-Host "[tauri-dev] Starting Tauri dev UI. Press Ctrl+C in this window to stop it." -ForegroundColor Cyan
    if ($vsDevCmd) {
        $cmdLine = '"{0}" -no_logo -arch=x64 -host_arch=x64 && "{1}" run tauri -- dev' -f $vsDevCmd, $npm.Source
        & cmd.exe /d /s /c $cmdLine
    }
    else {
        & $npm.Source run tauri -- dev
    }
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
