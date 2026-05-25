param(
    [switch]$Restart,
    [switch]$NoTail
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Resolve-LauncherPythonw {
    $venvPythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
    if (Test-Path $venvPythonw) {
        return $venvPythonw
    }
    throw "Missing .venv\Scripts\pythonw.exe. Please create or install the project environment first."
}

function Stop-ProjectPython {
    $venvPythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    Get-Process -Name python,pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $venvPythonw -or $_.Path -eq $venvPython } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

$pythonw = Resolve-LauncherPythonw
$stateRoot = if ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "EngineeringLauncher"
} else {
    Join-Path $env:USERPROFILE ".engineering_launcher"
}
$logDir = Join-Path $stateRoot "logs"
$isoLog = Join-Path $logDir "iso_pdf_workbench.log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if (-not (Test-Path $isoLog)) {
    New-Item -ItemType File -Force -Path $isoLog | Out-Null
}

if ($Restart) {
    Write-Host "[debug] Restarting launcher processes from this project..." -ForegroundColor Yellow
    Stop-ProjectPython
}

Write-Host "[debug] Project: $ProjectRoot" -ForegroundColor Cyan
Write-Host "[debug] Pythonw: $pythonw" -ForegroundColor Cyan
Write-Host "[debug] ISO log: $isoLog" -ForegroundColor Cyan

Start-Process -FilePath $pythonw -ArgumentList "-m","launcher.app.main","--show-existing" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
Write-Host "[debug] Launcher started. Open ISO Naming and watch log output below." -ForegroundColor Green

if (-not $NoTail) {
    Write-Host "[debug] Tailing ISO workbench log. Press Ctrl+C to stop watching." -ForegroundColor Green
    Get-Content -Path $isoLog -Wait -Tail 80 -Encoding UTF8
}
