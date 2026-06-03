param(
    [ValidateSet("Release", "Debug")]
    [string]$Configuration = "Release",
    [switch]$SkipNpmInstall,
    [switch]$OpenOutputFolder
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendRoot = Join-Path $ProjectRoot "frontend\tauri-spike"
$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"

if (Test-Path $CargoBin) {
    $env:Path = "$CargoBin;$env:Path"
}

function Require-Command {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Missing command: $Name"
    }
    return $command.Source
}

$npm = Require-Command "npm.cmd"
$null = Require-Command "cargo.exe"

if (-not $SkipNpmInstall -and -not (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
    Push-Location $FrontendRoot
    try {
        & $npm ci
    } finally {
        Pop-Location
    }
}

$tauriArgs = @("run", "tauri", "--", "build")
$profile = "release"
if ($Configuration -eq "Debug") {
    $tauriArgs += "--debug"
    $profile = "debug"
}

Push-Location $FrontendRoot
try {
    & $npm @tauriArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Tauri build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$exe = Join-Path $FrontendRoot "src-tauri\target\$profile\desktop-support-tauri-spike.exe"
if (-not (Test-Path $exe)) {
    throw "Expected exe was not found: $exe"
}

Write-Host "[tauri] Built executable:" -ForegroundColor Green
Write-Host $exe -ForegroundColor Cyan

if ($OpenOutputFolder) {
    Start-Process -FilePath "explorer.exe" -ArgumentList "/select,`"$exe`""
}
