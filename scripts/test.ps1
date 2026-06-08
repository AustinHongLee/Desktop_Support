param(
    [ValidateSet("env", "smoke", "unit", "shutdown", "frontend", "tauri-ui", "all")]
    [string]$Suite = "unit",
    [switch]$BuildTauri,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Resolve-ProjectPython {
    $candidates = @()

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $candidates += @{ Exe = $venvPython; Args = @() }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $candidates += @{ Exe = $python.Source; Args = @() }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $candidates += @{ Exe = $py.Source; Args = @("-3") }
        $candidates += @{ Exe = $py.Source; Args = @("-3.12") }
    }

    foreach ($candidate in $candidates) {
        $checkArgs = @($candidate.Args) + @("-c", "import pytest")
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $candidate.Exe @checkArgs *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }

    throw "pytest was not found in .venv, python, or py. Install dev dependencies or run with a Python that has pytest."
}

function Invoke-PythonTests {
    param([string[]]$Paths)

    $python = Resolve-ProjectPython
    $pytestArgs = @($python.Args) + @("-m", "pytest") + @($Paths)
    if (-not $ExtraArgs -or $ExtraArgs.Count -eq 0) {
        $pytestArgs += "-q"
    } else {
        $filteredExtraArgs = @($ExtraArgs | Where-Object { $_ -ne "--" })
        $pytestArgs += $filteredExtraArgs
    }

    Write-Host "[test] python $($pytestArgs -join ' ')" -ForegroundColor Cyan
    & $python.Exe @pytestArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Invoke-FrontendBuild {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) {
        throw "npm.cmd was not found. Install Node.js or skip the frontend suite."
    }

    $frontendRoot = Join-Path $ProjectRoot "frontend\tauri-spike"
    Push-Location $frontendRoot
    try {
        Write-Host "[test] npm run build" -ForegroundColor Cyan
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-DevEnvironmentCheck {
    $devEnvScript = Join-Path $ProjectRoot "scripts\dev\prepare_dev_environment.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $devEnvScript
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Start-TauriUi {
    $tauriExe = Join-Path $ProjectRoot "frontend\tauri-spike\src-tauri\target\release\desktop-support-tauri-spike.exe"
    $buildScript = Join-Path $ProjectRoot "scripts\tauri\build_desktop_app.ps1"
    $devScript = Join-Path $ProjectRoot "scripts\tauri\run_dev_app.ps1"

    if (-not $BuildTauri) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $devScript
        exit $LASTEXITCODE
    }

    Get-Process -Name "desktop-support-tauri-spike" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300

    if ($BuildTauri) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildScript -Configuration Release
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    if (-not (Test-Path $tauriExe)) {
        Write-Host "Tauri release exe was not found:" -ForegroundColor Yellow
        Write-Host $tauriExe
        Write-Host ""
        Write-Host "Build and launch it with:"
        Write-Host ".\scripts\test.ps1 -Suite tauri-ui -BuildTauri"
        exit 1
    }

    $tauriExe = (Resolve-Path $tauriExe).Path
    Write-Host "[test] starting Tauri UI" -ForegroundColor Cyan
    Start-Process -FilePath $tauriExe -WorkingDirectory $ProjectRoot
}

switch ($Suite) {
    "env" {
        Invoke-DevEnvironmentCheck
    }
    "smoke" {
        Invoke-PythonTests -Paths @("tests/test_smoke.py")
    }
    "unit" {
        Invoke-PythonTests -Paths @("tests")
    }
    "shutdown" {
        Invoke-PythonTests -Paths @(
            "tests/test_shutdown_safety.py",
            "tests/test_shutdown_safety_dialog.py",
            "tests/test_dock_window.py"
        )
    }
    "frontend" {
        Invoke-FrontendBuild
    }
    "tauri-ui" {
        Start-TauriUi
    }
    "all" {
        Invoke-PythonTests -Paths @("tests")
        Invoke-FrontendBuild
    }
}
