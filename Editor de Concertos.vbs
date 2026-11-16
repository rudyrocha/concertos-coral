Option Explicit

Dim fso, shell, shellApp, base, pythonw, script, installer, source, folder, cmd, rc, startFolder
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
Set shellApp = CreateObject("Shell.Application")

base = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = base & "\.venv\Scripts\pythonw.exe"
script = base & "\coral_editor.py"
installer = base & "\instalar.bat"

If Not fso.FileExists(script) Then
  MsgBox "Aplicativo nao encontrado: " & script, vbCritical, "Editor de Concertos"
  WScript.Quit 1
End If

If Not fso.FileExists(pythonw) Then
  If Not fso.FileExists(installer) Then
    MsgBox "Instalador nao encontrado: " & installer, vbCritical, "Editor de Concertos"
    WScript.Quit 1
  End If
  rc = shell.Run(Chr(34) & installer & Chr(34), 1, True)
  If rc <> 0 Or Not fso.FileExists(pythonw) Then
    MsgBox "Nao foi possivel preparar o ambiente Python do Editor de Concertos.", vbCritical, "Editor de Concertos"
    WScript.Quit 1
  End If
End If

If WScript.Arguments.Count > 0 Then
  source = WScript.Arguments(0)
Else
  startFolder = "D:\OFFline\Videos"
  If fso.FolderExists(startFolder) Then
    Set folder = shellApp.BrowseForFolder(0, "Selecione a pasta do concerto", 0, startFolder)
  Else
    Set folder = shellApp.BrowseForFolder(0, "Selecione a pasta do concerto", 0, 17)
  End If
  If folder Is Nothing Then WScript.Quit 0
  On Error Resume Next
  source = folder.Self.Path
  On Error GoTo 0
End If

If Len(source) = 0 Or Not fso.FolderExists(source) Then
  MsgBox "Selecione uma pasta local valida para o concerto.", vbExclamation, "Editor de Concertos"
  WScript.Quit 2
End If

shell.CurrentDirectory = base
cmd = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & script & Chr(34) & " --source " & Chr(34) & source & Chr(34)
shell.Run cmd, 0, False
