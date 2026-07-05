' Double-click launcher for non-technical users: starts the app with no
' visible console window, then opens it in the default browser.
'
' To close the app, use the "Quit app" button inside the web page - there
' is no window from this launcher itself to close (it starts the server
' hidden and this script exits as soon as the browser opens).
'
' Requires setup.bat to have been run at least once. If it hasn't, this
' launcher offers to run it for you (a console window will show its
' progress - that one-time step isn't hidden the way normal app runs are).

Option Explicit

Dim fso, shell, scriptDir, pythonw, i, http, started, answer

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

Set shell = CreateObject("WScript.Shell")
pythonw = scriptDir & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    answer = MsgBox( _
        "Setup hasn't been run yet." & vbCrLf & vbCrLf & _
        "Run it now? A window will open showing progress - this only happens once.", _
        vbYesNo + vbQuestion, "Speech To Keyboard")
    If answer = vbNo Then
        WScript.Quit 1
    End If

    shell.CurrentDirectory = scriptDir
    ' windowStyle 1 = normal (visible, so setup progress/errors are visible),
    ' waitOnReturn True = block here until setup.bat finishes.
    shell.Run """" & scriptDir & "\setup.bat""", 1, True

    If Not fso.FileExists(pythonw) Then
        MsgBox "Setup did not finish successfully - see the window that just closed for details.", _
               vbExclamation, "Speech To Keyboard"
        WScript.Quit 1
    End If
End If

shell.CurrentDirectory = scriptDir
' windowStyle 0 = hidden, waitOnReturn False = don't block this script.
shell.Run """" & pythonw & """ -m src.ui.server", 0, False

' Wait for the server to come up (loading the speech model takes a moment),
' then open it in the default browser.
started = False
For i = 1 To 30
    WScript.Sleep 1000
    On Error Resume Next
    Set http = Nothing
    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", "http://127.0.0.1:8765/", False
    http.Send
    If Err.Number = 0 And http.Status = 200 Then
        started = True
    End If
    On Error Goto 0
    If started Then Exit For
Next

If started Then
    shell.Run "http://127.0.0.1:8765"
Else
    MsgBox "The app did not start within 30 seconds." & vbCrLf & _
           "For error details, run this from Command Prompt in this folder:" & vbCrLf & _
           ".venv\Scripts\python.exe -m src.ui.server -v", _
           vbExclamation, "Speech To Keyboard"
End If
