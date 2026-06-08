Option Explicit

Dim shell
Dim fso
Dim shortcutPath
Dim projectPath
Dim launcherScript
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

shortcutPath = fso.GetParentFolderName(WScript.ScriptFullName)
projectPath = fso.GetParentFolderName(fso.GetParentFolderName(shortcutPath))
launcherScript = projectPath & "\scripts\launcher\run_launcher.ps1"
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & launcherScript & Chr(34) & " --context-menu-manager"

shell.Run command, 0, False
