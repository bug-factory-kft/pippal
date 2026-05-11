' Launches the PipPal tray app silently from this source checkout.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
reader = fso.BuildPath(scriptDir, "reader_app.py")

sh.CurrentDirectory = scriptDir
sh.Run "pythonw.exe """ & reader & """", 0, False
