function Find-VsWhere {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"),
        (Join-Path $env:ProgramFiles "Microsoft Visual Studio\Installer\vswhere.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Get-VisualStudioPath {
    param([switch]$RequireCpp)

    $vswhere = Find-VsWhere
    if (-not $vswhere) {
        return $null
    }

    $args = @("-latest", "-products", "*", "-property", "installationPath")
    if ($RequireCpp) {
        $args = @("-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath")
    }

    $path = & $vswhere @args
    if ($LASTEXITCODE -ne 0 -or -not $path) {
        return $null
    }

    return $path
}

function Find-VsDevCmd {
    $installPath = Get-VisualStudioPath -RequireCpp
    if (-not $installPath) {
        return $null
    }

    $devCmd = Join-Path $installPath "Common7\Tools\VsDevCmd.bat"
    if (Test-Path $devCmd) {
        return $devCmd
    }

    return $null
}

function Test-VsDevCmdTool {
    param(
        [string]$DevCmd,
        [string]$ToolName
    )

    if (-not $DevCmd) {
        return $false
    }

    $cmdLine = '"{0}" -no_logo -arch=x64 -host_arch=x64 >nul && where.exe {1} >nul 2>nul' -f $DevCmd, $ToolName
    & cmd.exe /d /s /c $cmdLine
    return $LASTEXITCODE -eq 0
}
