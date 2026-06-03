param(
    [switch]$DryRun,
    [switch]$KillSafe,
    [switch]$KillAllProjectOwned,
    [switch]$JsonReport,
    [switch]$MockShutdownEvent
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

if ($KillAllProjectOwned) {
    Write-Host "KillAllProjectOwned only stops process trees whose command line contains this project root."
    Write-Host "Dangerous / Unknown blockers may be force-stopped. Check outputs, databases, downloads, and temp files first."
    $Confirm = Read-Host "Type KILL PROJECT OWNED to continue"
    if ($Confirm -ne "KILL PROJECT OWNED") {
        Write-Host "Cancelled."
        exit 1
    }
}

$ArgsList = @("-m", "launcher.app.shutdown_safety_inspector")
if ($DryRun) { $ArgsList += "--dry-run" }
if ($KillSafe) { $ArgsList += "--kill-safe" }
if ($KillAllProjectOwned) { $ArgsList += "--kill-all-project-owned" }
if ($JsonReport) { $ArgsList += "--json-report" }
if ($MockShutdownEvent) { $ArgsList += "--mock-shutdown-event" }

Push-Location $ProjectRoot
try {
    & $Python @ArgsList
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
