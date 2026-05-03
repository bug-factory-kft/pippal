' Launches the Piper Reader tray app silently (no console window).
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\tigyi\piper-reader"
sh.Run """C:\Python314\pythonw.exe"" ""C:\Users\tigyi\piper-reader\reader_app.py""", 0, False
