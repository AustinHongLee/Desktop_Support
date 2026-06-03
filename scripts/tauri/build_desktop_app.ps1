param(
    [ValidateSet("Release", "Debug")]
    [string]$Configuration = "Release",
    [switch]$SkipNpmInstall,
    [switch]$SkipBackendBuild,
    [string]$TargetTriple = "x86_64-pc-windows-msvc",
    [switch]$OpenOutputFolder
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendRoot = Join-Path $ProjectRoot "frontend\tauri-spike"
$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
$TauriRoot = Join-Path $FrontendRoot "src-tauri"
$BackendName = "desktop-support-backend"
$SidecarName = "$BackendName-$TargetTriple.exe"
$BackendDist = Join-Path $TauriRoot "backend-dist"
$BackendWork = Join-Path $TauriRoot "backend-build"
$BackendSpec = Join-Path $BackendWork "spec"
$BackendBinaries = Join-Path $TauriRoot "binaries"

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

function Build-PythonBackend {
    if ($SkipBackendBuild) {
        return
    }

    $pyinstaller = Require-Command "pyinstaller.exe"
    $entrypoint = Join-Path $ProjectRoot "launcher\app\tauri_backend.py"
    New-Item -ItemType Directory -Force -Path $BackendDist, $BackendWork, $BackendSpec, $BackendBinaries | Out-Null

    & $pyinstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name $BackendName `
        --distpath $BackendDist `
        --workpath $BackendWork `
        --specpath $BackendSpec `
        --paths $ProjectRoot `
        $entrypoint
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller backend build failed with exit code $LASTEXITCODE"
    }

    $builtBackend = Join-Path $BackendDist "$BackendName.exe"
    if (-not (Test-Path $builtBackend)) {
        throw "Expected backend sidecar was not found: $builtBackend"
    }

    Copy-Item -LiteralPath $builtBackend -Destination (Join-Path $BackendBinaries $SidecarName) -Force
    Copy-Item -LiteralPath $builtBackend -Destination (Join-Path $BackendBinaries "$BackendName.exe") -Force
}

Build-PythonBackend

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

$sidecar = Join-Path $BackendBinaries $SidecarName
if (-not (Test-Path $sidecar)) {
    throw "Expected sidecar was not found: $sidecar"
}

$exeFolder = Split-Path -Parent $exe
Copy-Item -LiteralPath $sidecar -Destination (Join-Path $exeFolder "$BackendName.exe") -Force
Copy-Item -LiteralPath $sidecar -Destination (Join-Path $exeFolder $SidecarName) -Force

Write-Host "[tauri] Built executable:" -ForegroundColor Green
Write-Host $exe -ForegroundColor Cyan
Write-Host "[tauri] Bundled backend sidecar:" -ForegroundColor Green
Write-Host (Join-Path $exeFolder "$BackendName.exe") -ForegroundColor Cyan

if ($OpenOutputFolder) {
    Start-Process -FilePath "explorer.exe" -ArgumentList "/select,`"$exe`""
}
