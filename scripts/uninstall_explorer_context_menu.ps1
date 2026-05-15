$ErrorActionPreference = "Stop"

$VerbName = "EngineeringLauncherSetContext"
$Root = [Microsoft.Win32.Registry]::CurrentUser
$Paths = @(
    "Software\Classes\*\shell\$VerbName",
    "Software\Classes\Directory\shell\$VerbName",
    "Software\Classes\Directory\Background\shell\$VerbName",
    "Software\Classes\Drive\shell\$VerbName"
)

foreach ($path in $Paths) {
    try {
        $Root.DeleteSubKeyTree($path, $false)
    } catch {
        throw
    }
}

Write-Host "已移除 Explorer 右鍵選單。"

