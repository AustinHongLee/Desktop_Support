Option Explicit

Dim shell
Dim fso
Dim projectPath
Dim tauriExe
Dim fallbackScript
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectPath = fso.GetParentFolderName(WScript.ScriptFullName)
tauriExe = projectPath & "\frontend\tauri-spike\src-tauri\target\release\desktop-support-tauri-spike.exe"
fallbackScript = projectPath & "\scripts\launcher\run_launcher.ps1"

If fso.FileExists(tauriExe) Then
    shell.CurrentDirectory = projectPath
    shell.Run Chr(34) & tauriExe & Chr(34), 1, False
ElseIf fso.FileExists(fallbackScript) Then
    command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & fallbackScript & Chr(34) & " -Restart -ShowDock"
    shell.Run command, 0, False
Else
    MsgBox "Desktop Support launcher was not found." & vbCrLf & tauriExe, vbExclamation, "Desktop Support"
End If
