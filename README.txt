Piper Reader — háttérben futó Windows app
=========================================

System tray alkalmazás. Bárhol a Windowsban (Firefox, Chrome, PDF, Word,
Notepad, akármi) jelölj ki szöveget, és:

  Ctrl + Shift + X   -> felolvassa
  Ctrl + Shift + Z   -> leállítja

Olvasó panel (overlay)
----------------------
Minimalista sötét kártya a képernyő alján középen, csak az aktuális
mondat (chunk) szövegével:
  - thinking…   első mondat szintézise alatt (három pulzáló pont)
  - reading     a teljes mondat statikusan kirajzolva, a kiemelő pille
                csúszik szóról szóra (sorvégen ugrik a következő sorra),
                alatta vékony progress-csík
  - ✓           kész jel, eltűnik kb. 1.5 mp múlva

A panel magassága a mondat hosszához igazodik. Mondat végén a következő
chunk szövege felváltja az előzőt — minden statikus, csak a kiemelés mozog.

A szóidőzítés a hangfájl hosszából van becsülve (Piper nem ad word-level
timestampet), így ~50–150 ms drift előfordulhat. Mondatonként resync.

Jobb gombbal húzva áthelyezhető. ✕ a sarokban (vagy Ctrl+Shift+Z) megáll.
Settingsben kapcsolható ki a szövegkövetés vagy az egész overlay.

Tálcán a "P" ikon: kék = tétlen, piros = éppen olvas. Jobb klikk:
- Read selection
- Stop
- Settings…  (hang, sebesség, hotkey-k, overlay)
- Quit

Settings (jobbklikk a tálcaikonra → Settings…)
----------------------------------------------
- Hang: a telepített hangok közül választható.
- További hangok…: Ryan, LibriTTS-R, HFC Female/Male, Amy, Lessac,
  Alan (UK), Northern English Male (UK), Jenny (UK) — egy kattintással
  letölthetők a Hugging Face-ről.
- Sebesség: 0.6×–1.7×
- Változatosság (noise_scale): élőbb intonációhoz feljebb
- Hotkey-k átállíthatók
- Overlay ki/be, eltűnési idő, függőleges pozíció

Még jobb hangok?
----------------
A Piper-on belül a "ryan-high" és "libritts_r-medium" a két
legtermészetesebb. Ha még ennél is élethűbb kell, a Kokoro TTS
(2024 vége óta) jelenleg vezet a TTS Arena listán — kis modell, CPU-n
fut, de külön telepítés. Ha kell, cserélem a motort.

Autostart
---------
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PiperReader.vbs

Indítás kézzel
--------------
- start_server.vbs   csendben (autostart is ezt használja)
- start_console.bat  látszik a kimenet (debug)

Fájlok
------
reader_app.py          fő app
config.json            felhasználói beállítások (settings ablak menti)
piper\piper.exe        TTS motor
voices\*.onnx          hangmodellek
temp\                  ideiglenes WAV-ok
