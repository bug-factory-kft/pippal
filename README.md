<p align="center">
  <img src="docs/pippal_logo.png" alt="PipPal" width="380">
</p>

<h1 align="center">PipPal</h1>

<p align="center"><i>Your little offline reading buddy.</i></p>

---

A tray-resident Windows app that reads any selected text aloud with
a local neural TTS. Press `Ctrl+Shift+X` in **any** program (browser,
PDF reader, Word, terminal — anywhere) and a clean floating panel shows
the sentence with a karaoke-style highlight that follows the voice.

No cloud. No API keys. No telemetry. The text never leaves your machine.

---

## Features

- 🔊 Reads selected text from any application via a global hotkey.
- 🎙 Local neural TTS via [Piper](https://github.com/rhasspy/piper)
  (`en_US-ryan-high` by default; a built-in Voice Manager downloads
  more voices from the Piper voices catalogue).
- 📺 Floating reader panel: the sentence sits still, only a thin mint
  underline slides under the spoken word; surrounding words gently fade
  in and out as the cursor passes.
- ⚙ Settings window with voice, speed, variation, hotkeys, and reader-
  panel options. Dark, card-based design.
- 🚀 Background process. Autostarts on login. Tiny tray icon.

## Installation (Windows)

Requires Python 3.11+ on `PATH` (or `pythonw` from Python's install).

```powershell
git clone https://github.com/<you>/pippal.git
cd pippal
.\setup.ps1                       # downloads Piper + default voice + pip deps
pythonw reader_app.py             # run once to confirm; tray icon appears
```

To start automatically on login, copy `start_server.vbs` to your
Startup folder:

```powershell
copy start_server.vbs "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\PipPal.vbs"
```

## Usage

| Action | Default hotkey |
|---|---|
| Read the currently selected text | `Ctrl+Shift+X` |
| Stop reading | `Ctrl+Shift+Z` |

Right-click the tray icon for **Settings…** (voice, speed, hotkeys,
panel options, voice manager).

## How it works

1. Hotkey fires → app sends `Ctrl+C` to the focused app to copy the
   selection, reads the clipboard, restores the previous clipboard.
2. Text is split into sentences. The first sentence is synthesised
   immediately; subsequent ones run in parallel with playback.
3. Each chunk's WAV is played via `winsound`. Word timings inside the
   chunk are estimated from the audio duration so the karaoke
   underline tracks the voice (Tier 1 of [ROADMAP.md](ROADMAP.md) will
   replace this with real per-word timestamps).
4. The reader panel is a frameless tk Toplevel that uses a transparent
   colour key for soft rounded corners.

See [ROADMAP.md](ROADMAP.md) for what's coming.

## Stack

- Python (single-file app — `reader_app.py`)
- `pystray` + Pillow — tray icon
- `keyboard` — global hotkeys
- `pyperclip` — clipboard
- `tkinter` — reader panel and settings UI
- `winsound` — playback (Windows-only stdlib)
- [Piper](https://github.com/rhasspy/piper) — TTS engine

## Status

Early. Working day-to-day. See ROADMAP for known gaps and planned work.

## Licence

PipPal source is **MIT-licensed** — see [LICENSE](LICENSE).
Third-party dependencies and downloaded run-time artefacts (Piper,
voice models, Kokoro) are listed with their respective licences in
[THIRD_PARTY.md](THIRD_PARTY.md).
