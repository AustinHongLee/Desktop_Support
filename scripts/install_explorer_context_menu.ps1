$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $Pythonw)) {
    throw "找不到 $Pythonw。請先執行 .\run_launcher.ps1 建立/確認專案 venv。"
}

$CommandPrefix = "`"$Pythonw`" -m launcher.app.main --show-existing --context-source explorer.menu --set-context"
$VerbName = "EngineeringLauncherSetContext"
$VerbTitle = "送到工程工具列"
$Root = [Microsoft.Win32.Registry]::CurrentUser

function Set-Verb {
    param(
        [Parameter(Mandatory=$true)][string]$BaseSubKey,
        [Parameter(Mandatory=$true)][string]$ArgumentToken
    )

    $verbKey = $Root.CreateSubKey("$BaseSubKey\$VerbName")
    $verbKey.SetValue("MUIVerb", $VerbTitle, [Microsoft.Win32.RegistryValueKind]::String)
    $verbKey.SetValue("Icon", $Pythonw, [Microsoft.Win32.RegistryValueKind]::String)
    $verbKey.SetValue("MultiSelectModel", "Player", [Microsoft.Win32.RegistryValueKind]::String)
    $commandKey = $verbKey.CreateSubKey("command")
    $commandKey.SetValue("", "$CommandPrefix `"$ArgumentToken`"", [Microsoft.Win32.RegistryValueKind]::String)
    $commandKey.Close()
    $verbKey.Close()
}

Set-Verb -BaseSubKey "Software\Classes\*\shell" -ArgumentToken "%1"
Set-Verb -BaseSubKey "Software\Classes\Directory\shell" -ArgumentToken "%1"
Set-Verb -BaseSubKey "Software\Classes\Directory\Background\shell" -ArgumentToken "%V"
Set-Verb -BaseSubKey "Software\Classes\Drive\shell" -ArgumentToken "%1"

Write-Host "已安裝 Explorer 右鍵選單：$VerbTitle"
Write-Host "範圍：檔案、資料夾、資料夾背景、磁碟機"
