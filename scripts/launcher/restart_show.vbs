Option Explicit

Dim shell
Dim fso
Dim launcherPath
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

launcherPath = fso.GetParentFolderName(WScript.ScriptFullName)
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & launcherPath & "\run_launcher.ps1" & Chr(34) & " -Restart -ShowDock"

shell.Run command, 0, False
