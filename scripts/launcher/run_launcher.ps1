param(
    [switch]$Foreground,
    [switch]$ShowDock,
    [switch]$Restart,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$LauncherArgsFromCommandLine
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Get-LauncherLogPaths {
    $stateRoot = if ($env:LOCALAPPDATA) {
        Join-Path $env:LOCALAPPDATA "EngineeringLauncher"
    } else {
        Join-Path $env:USERPROFILE ".engineering_launcher"
    }
    $logDir = Join-Path $stateRoot "logs"
    New-Item -ItemType Directory -Force -Path $logDir -ErrorAction SilentlyContinue | Out-Null
    $projectLogDir = Join-Path $ProjectRoot "logs"
    New-Item -ItemType Directory -Force -Path $projectLogDir -ErrorAction SilentlyContinue | Out-Null
    return @(
        (Join-Path $logDir "launcher_startup.log"),
        (Join-Path $projectLogDir "launcher_startup.log")
    )
}

function Get-ProjectLogDir {
    $projectLogDir = Join-Path $ProjectRoot "logs"
    New-Item -ItemType Directory -Force -Path $projectLogDir -ErrorAction SilentlyContinue | Out-Null
    return $projectLogDir
}

function Write-LauncherLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    foreach ($path in @(Get-LauncherLogPaths)) {
        try {
            Add-Content -Path $path -Encoding UTF8 -Value "[$stamp] $Message"
            return
        } catch {
            # Startup logging must never become the reason startup fails.
        }
    }
}

function Normalize-ArgumentList {
    param([object[]]$Values)
    $result = @()
    foreach ($value in @($Values)) {
        if ($null -ne $value -and "$value" -ne "") {
            $result += "$value"
        }
    }
    return $result
}

function Resolve-LauncherBackgroundPython {
    $venvPythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
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
    $venvPythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $processes = @(
        Get-Process -Name python,pythonw -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $venvPythonw -or $_.Path -eq $venvPython }
    )
    try {
        $projectNeedle = $ProjectRoot.ToLowerInvariant()
        $processes += @(
            Get-CimInstance Win32_Process -Filter "name='python.exe' or name='pythonw.exe'" -ErrorAction Stop |
            Where-Object {
                $commandLine = "$($_.CommandLine)".ToLowerInvariant()
                $commandLine.Contains("launcher.app.main") -and $commandLine.Contains($projectNeedle)
            } |
            ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        )
    } catch {
        Write-LauncherLog "Process command-line scan skipped: $($_.Exception.Message)"
    }
    $processes = @($processes | Where-Object { $null -ne $_ } | Sort-Object Id -Unique)
    foreach ($process in $processes) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    foreach ($process in $processes) {
        try {
            Wait-Process -Id $process.Id -Timeout 5 -ErrorAction SilentlyContinue
        } catch {
            Write-LauncherLog "Process wait skipped for $($process.Id): $($_.Exception.Message)"
        }
    }
    if ($processes.Count -gt 0) {
        Start-Sleep -Milliseconds 500
    }
}

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

try {
    Write-LauncherLog "Starting launcher. Foreground=$Foreground ShowDock=$ShowDock Restart=$Restart ProjectRoot=$ProjectRoot"

    if ($Restart) {
        Stop-ProjectPython
    }

    $launcherArgs = @("-m", "launcher.app.main")
    if (-not $ShowDock) {
        $launcherArgs += "--start-hidden"
    }
    $launcherArgs += "--show-existing"
    $launcherArgs = Normalize-ArgumentList -Values (@($launcherArgs) + @($LauncherArgsFromCommandLine))

    if (-not $Foreground) {
        $python = Resolve-LauncherPython
        $processArgs = Normalize-ArgumentList -Values (@($python.Args) + @($launcherArgs))
        $process = Start-Process `
            -FilePath $python.Exe `
            -ArgumentList $processArgs `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -PassThru
        Write-LauncherLog "Started background launcher via python. Pid=$($process.Id) Args=$($processArgs -join ' ')"
        return
    }

    $python = Resolve-LauncherPython
    $foregroundArgs = Normalize-ArgumentList -Values (@($python.Args) + @($launcherArgs))
    Write-LauncherLog "Running foreground launcher via $($python.Exe). Args=$($foregroundArgs -join ' ')"
    & $python.Exe @foregroundArgs
} catch {
    Write-LauncherLog "ERROR: $($_.Exception.Message)"
    Write-LauncherLog "STACK: $($_.ScriptStackTrace)"
    if ($Foreground) {
        throw
    }
    exit 1
}
