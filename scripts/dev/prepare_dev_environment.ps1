param(
    [switch]$InstallMissing,
    [switch]$AssumeYes,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$SharedRoot = Join-Path $ProjectRoot "scripts\_shared"

. (Join-Path $SharedRoot "path_utils.ps1")
. (Join-Path $SharedRoot "vs_env.ps1")

$CargoPathStatus = Get-CargoPathStatus
$CargoBin = $CargoPathStatus.CargoBin
$UserPathHasCargoBin = $CargoPathStatus.UserPathHasCargoBin
$MachinePathHasCargoBin = $CargoPathStatus.MachinePathHasCargoBin
$ProcessPathHadCargoBin = $CargoPathStatus.ProcessPathHasCargoBin
Add-CargoBinToProcessPath

function Find-Tool {
    param([string[]]$Names)

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }

    return $null
}

function Add-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Detail,
        [string]$Fix
    )

    [pscustomobject]@{
        name = $Name
        ok = $Ok
        detail = $Detail
        fix = $Fix
    }
}

function Invoke-Installer {
    param(
        [string]$Label,
        [string]$Exe,
        [string[]]$Arguments
    )

    Write-Host "[dev-env] Installing $Label..." -ForegroundColor Cyan
    & $Exe @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0 -and $exitCode -ne 3010) {
        throw "$Label installer failed with exit code $exitCode"
    }
    if ($exitCode -eq 3010) {
        Write-Host "[dev-env] $Label installed, but Windows reported that a restart is required." -ForegroundColor Yellow
    }
}

function Invoke-ElevatedInstaller {
    param(
        [string]$Label,
        [string]$Exe,
        [string]$ArgumentString
    )

    Write-Host "[dev-env] Installing $Label with elevation..." -ForegroundColor Cyan
    $process = Start-Process -FilePath $Exe -ArgumentList $ArgumentString -Verb RunAs -Wait -PassThru
    $exitCode = $process.ExitCode
    if ($exitCode -ne 0 -and $exitCode -ne 3010) {
        throw "$Label installer failed with exit code $exitCode"
    }
    if ($exitCode -eq 3010) {
        Write-Host "[dev-env] $Label installed, but Windows reported that a restart is required." -ForegroundColor Yellow
    }
}

function Install-Rustup {
    $winget = Find-Tool @("winget.exe")
    if (-not $winget) {
        throw "winget.exe was not found. Install Rust manually from https://rustup.rs/."
    }

    Invoke-Installer `
        -Label "Rustup" `
        -Exe $winget `
        -Arguments @(
            "install",
            "--id", "Rustlang.Rustup",
            "--exact",
            "--source", "winget",
            "--accept-source-agreements",
            "--accept-package-agreements"
        )
}

function Install-VisualStudioCppTools {
    $setup = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\setup.exe"
    $existingInstall = Get-VisualStudioPath

    if ($existingInstall -and (Test-Path $setup)) {
        $argumentString = 'modify --installPath "{0}" --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive --norestart' -f $existingInstall
        Invoke-ElevatedInstaller `
            -Label "Visual Studio C++ build tools" `
            -Exe $setup `
            -ArgumentString $argumentString
        return
    }

    $winget = Find-Tool @("winget.exe")
    if (-not $winget) {
        throw "winget.exe was not found. Install Visual Studio Build Tools manually with Desktop development with C++."
    }

    Invoke-Installer `
        -Label "Visual Studio Build Tools with C++" `
        -Exe $winget `
        -Arguments @(
            "install",
            "--id", "Microsoft.VisualStudio.2022.BuildTools",
            "--exact",
            "--source", "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--override", "--wait --passive --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
        )
}

function Confirm-InstallMissing {
    if ($AssumeYes) {
        return $true
    }

    Write-Host ""
    Write-Host "[dev-env] This can install or modify Rustup and Visual Studio Build Tools C++ components." -ForegroundColor Yellow
    Write-Host "[dev-env] Visual Studio C++ tools and Windows SDK can be several GB and may require UAC." -ForegroundColor Yellow
    $answer = Read-Host "Continue? (y/N)"
    return $answer -in @("y", "Y", "yes", "YES")
}

$node = Find-Tool @("node.exe", "node.cmd", "node")
$npm = Find-Tool @("npm.cmd", "npm.exe", "npm")
$python = Find-Tool @("python.exe", "py.exe", "python", "py")
$pyinstaller = Find-Tool @("pyinstaller.exe", "pyinstaller")
$cargo = Find-Tool @("cargo.exe", "cargo")
$rustup = Find-Tool @("rustup.exe", "rustup")
$winget = Find-Tool @("winget.exe", "winget")
$vswhere = Find-VsWhere
$vsAny = Get-VisualStudioPath
$vsCpp = Get-VisualStudioPath -RequireCpp
$vsDevCmd = Find-VsDevCmd
$linkInPath = Find-Tool @("link.exe")
$rcInPath = Find-Tool @("rc.exe")
$linkViaDevCmd = Test-VsDevCmdTool -DevCmd $vsDevCmd -ToolName "link.exe"
$rcViaDevCmd = Test-VsDevCmdTool -DevCmd $vsDevCmd -ToolName "rc.exe"

$checks = @()
$checks += Add-Check -Name "Node.js" -Ok ([bool]$node) -Detail ($(if ($node) { $node } else { "missing" })) -Fix "Install Node.js LTS."
$checks += Add-Check -Name "npm" -Ok ([bool]$npm) -Detail ($(if ($npm) { $npm } else { "missing" })) -Fix "Install Node.js LTS."
$checks += Add-Check -Name "Python" -Ok ([bool]$python) -Detail ($(if ($python) { $python } else { "missing" })) -Fix "Install Python 3.12."
$checks += Add-Check -Name "PyInstaller" -Ok ([bool]$pyinstaller) -Detail ($(if ($pyinstaller) { $pyinstaller } else { "missing" })) -Fix "Install Python dev dependencies."
$checks += Add-Check -Name "Rust cargo" -Ok ([bool]$cargo) -Detail ($(if ($cargo) { $cargo } else { "missing" })) -Fix "Install Rustup."
$checks += Add-Check -Name "Rustup" -Ok ([bool]$rustup) -Detail ($(if ($rustup) { $rustup } else { "missing" })) -Fix "Install Rustup."
$checks += Add-Check -Name "Cargo PATH" -Ok ([bool]($UserPathHasCargoBin -or $MachinePathHasCargoBin -or $ProcessPathHadCargoBin)) -Detail ($(if ($UserPathHasCargoBin) { "user PATH includes $CargoBin" } elseif ($MachinePathHasCargoBin) { "machine PATH includes $CargoBin" } elseif ($ProcessPathHadCargoBin) { "current process PATH includes $CargoBin" } elseif (Test-Path $CargoBin) { "$CargoBin exists but is not in persistent PATH" } else { "missing" })) -Fix "Add %USERPROFILE%\.cargo\bin to user PATH."
$checks += Add-Check -Name "Visual Studio Build Tools" -Ok ([bool]$vsAny) -Detail ($(if ($vsAny) { $vsAny } else { "missing" })) -Fix "Install Visual Studio Build Tools 2022."
$checks += Add-Check -Name "Visual Studio C++ workload" -Ok ([bool]$vsCpp) -Detail ($(if ($vsCpp) { $vsCpp } else { "missing" })) -Fix "Install Desktop development with C++."
$checks += Add-Check -Name "MSVC linker" -Ok ([bool]($linkInPath -or $linkViaDevCmd)) -Detail ($(if ($linkInPath) { $linkInPath } elseif ($linkViaDevCmd) { "available through $vsDevCmd" } else { "missing" })) -Fix "Install MSVC v143 build tools."
$checks += Add-Check -Name "Windows SDK resource compiler" -Ok ([bool]($rcInPath -or $rcViaDevCmd)) -Detail ($(if ($rcInPath) { $rcInPath } elseif ($rcViaDevCmd) { "available through $vsDevCmd" } else { "missing" })) -Fix "Install Windows SDK."
$checks += Add-Check -Name "winget" -Ok ([bool]$winget) -Detail ($(if ($winget) { $winget } else { "missing" })) -Fix "Install App Installer from Microsoft Store."

if ($Json) {
    [pscustomobject]@{
        projectRoot = $ProjectRoot
        nativeTauriReady = [bool]($cargo -and ($linkInPath -or $linkViaDevCmd) -and ($rcInPath -or $rcViaDevCmd))
        checks = $checks
    } | ConvertTo-Json -Depth 4
}
else {
    Write-Host ""
    Write-Host "Desktop Support dev environment" -ForegroundColor Cyan
    Write-Host "================================"
    Write-Host ""

    foreach ($check in $checks) {
        $prefix = if ($check.ok) { "[OK]" } else { "[MISSING]" }
        $color = if ($check.ok) { "Green" } else { "Yellow" }
        Write-Host ("{0} {1}: {2}" -f $prefix, $check.name, $check.detail) -ForegroundColor $color
        if (-not $check.ok) {
            Write-Host ("     fix: {0}" -f $check.fix) -ForegroundColor DarkYellow
        }
    }

    Write-Host ""
    if ($cargo -and ($linkInPath -or $linkViaDevCmd) -and ($rcInPath -or $rcViaDevCmd)) {
        Write-Host "[dev-env] Native Tauri dev/build prerequisites look ready." -ForegroundColor Green
    }
    else {
        Write-Host "[dev-env] Browser UI fallback is usable, but native Tauri needs the missing items above." -ForegroundColor Yellow
        Write-Host "[dev-env] To install missing native tools, run:" -ForegroundColor Cyan
        Write-Host "          .\scripts\dev\prepare_dev_environment.ps1 -InstallMissing"
    }
}

if ($InstallMissing) {
    if (-not (Confirm-InstallMissing)) {
        Write-Host "[dev-env] Installation cancelled." -ForegroundColor Yellow
        exit 1
    }

    if (-not $cargo -or -not $rustup) {
        Install-Rustup
    }

    Add-CargoBinToUserPath

    if (-not $vsCpp -or -not ($linkInPath -or $linkViaDevCmd) -or -not ($rcInPath -or $rcViaDevCmd)) {
        Install-VisualStudioCppTools
    }

    Write-Host ""
    Write-Host "[dev-env] Installation step finished. Open a new PowerShell, then run:" -ForegroundColor Green
    Write-Host "          .\scripts\dev\prepare_dev_environment.ps1"
    Write-Host "          .\scripts\tauri\run_dev_app.ps1 -NativeOnly"
}
