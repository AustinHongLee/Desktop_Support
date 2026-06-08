Option Explicit

Dim shell
Dim fso
Dim shortcutPath
Dim projectPath
Dim fallbackScript
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

shortcutPath = fso.GetParentFolderName(WScript.ScriptFullName)
projectPath = fso.GetParentFolderName(fso.GetParentFolderName(shortcutPath))
fallbackScript = projectPath & "\scripts\launcher\run_launcher.ps1"

If fso.FileExists(fallbackScript) Then
    command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & fallbackScript & Chr(34) & " -ShowDock"
    shell.Run command, 0, False
Else
    MsgBox "Desktop Support launcher was not found." & vbCrLf & fallbackScript, vbExclamation, "Desktop Support"
End If
