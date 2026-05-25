$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Resolve-LauncherPython {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
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

$python = Resolve-LauncherPython
& $python.Exe @($python.Args) -m launcher.app.main --self-test
