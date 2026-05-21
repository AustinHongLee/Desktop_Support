Option Explicit

Dim shell
Dim fso
Dim projectPath
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectPath = fso.GetParentFolderName(WScript.ScriptFullName)
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & projectPath & "\run_launcher.ps1" & Chr(34)

shell.Run command, 0, False
