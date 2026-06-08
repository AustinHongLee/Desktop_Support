function Get-CargoBinPath {
    return (Join-Path $env:USERPROFILE ".cargo\bin")
}

function Test-PathListContains {
    param(
        [string]$PathList,
        [string]$Needle
    )

    if (-not $PathList -or -not $Needle) {
        return $false
    }

    $resolvedNeedle = $Needle.TrimEnd("\")
    foreach ($entry in ($PathList -split ";")) {
        if ($entry.TrimEnd("\") -ieq $resolvedNeedle) {
            return $true
        }
    }

    return $false
}

function Get-CargoPathStatus {
    $cargoBin = Get-CargoBinPath
    return [pscustomobject]@{
        CargoBin = $cargoBin
        UserPathHasCargoBin = Test-PathListContains -PathList ([Environment]::GetEnvironmentVariable("Path", "User")) -Needle $cargoBin
        MachinePathHasCargoBin = Test-PathListContains -PathList ([Environment]::GetEnvironmentVariable("Path", "Machine")) -Needle $cargoBin
        ProcessPathHasCargoBin = Test-PathListContains -PathList $env:Path -Needle $cargoBin
    }
}

function Add-CargoBinToProcessPath {
    $cargoBin = Get-CargoBinPath
    if ((Test-Path $cargoBin) -and -not (Test-PathListContains -PathList $env:Path -Needle $cargoBin)) {
        $env:Path = "$cargoBin;$env:Path"
    }
}

function Add-CargoBinToUserPath {
    $cargoBin = Get-CargoBinPath
    if (-not (Test-Path $cargoBin)) {
        return
    }

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (Test-PathListContains -PathList $userPath -Needle $cargoBin) {
        return
    }

    if ([string]::IsNullOrWhiteSpace($userPath)) {
        $newPath = $cargoBin
    }
    else {
        $newPath = "$userPath;$cargoBin"
    }

    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Add-CargoBinToProcessPath
    Write-Host "[dev-env] Added $cargoBin to the user PATH. Open a new PowerShell to inherit it." -ForegroundColor Green
}
