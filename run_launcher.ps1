param(
    [switch]$Foreground,
    [switch]$ShowDock,
    [switch]$Restart,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$LauncherArgsFromCommandLine
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Resolve-LauncherBackgroundPython {
    $venvPythonw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
    if (Test-Path $venvPythonw) {
        return $venvPythonw
    }

    $pythonw = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($pythonw) {
        return $pythonw.Source
    }

    $codexPythonw = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
    if (Test-Path $codexPythonw) {
        return $codexPythonw
    }

    return $null
}

function Stop-ProjectPython {
    $venvPythonw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    Get-Process -Name python,pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $venvPythonw -or $_.Path -eq $venvPython } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

function Resolve-LauncherPython {
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @{ Exe = $venvPython; Args = @() }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Exe = $python.Source; Args = @() }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Exe = $py.Source; Args = @("-3") }
    }

    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $codexPython) {
        return @{ Exe = $codexPython; Args = @() }
    }

    throw "Python was not found. Install Python 3.12+ or create .venv in this project."
}

if ($Restart) {
    Stop-ProjectPython
}

$launcherArgs = @("-m", "launcher.app.main")
if (-not $ShowDock) {
    $launcherArgs += "--start-hidden"
}
$launcherArgs += "--show-existing"
$launcherArgs += $LauncherArgsFromCommandLine

if (-not $Foreground) {
    $backgroundPython = Resolve-LauncherBackgroundPython
    if ($backgroundPython) {
        Start-Process -FilePath $backgroundPython -ArgumentList $launcherArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
        return
    }

    $python = Resolve-LauncherPython
    Start-Process -FilePath $python.Exe -ArgumentList @(@($python.Args) + $launcherArgs) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
    return
}

$python = Resolve-LauncherPython
& $python.Exe @($python.Args) @launcherArgs
