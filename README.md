<p align="center">
  <img src="docs/pippal_logo.png" alt="PipPal" width="380">
</p>

<h1 align="center">PipPal</h1>

<p align="center"><i>Your little offline reading buddy.</i></p>

<p align="center">
  Published by <a href="https://pippal.bugfactory.hu"><b>Bug Factory Kft.</b></a>
</p>

<p align="center">
  <video src="https://github.com/bug-factory-kft/pippal/releases/download/v0.2.0-assets/pippal_intro.mp4"
         width="480" autoplay loop muted playsinline></video>
</p>

---

A tray-resident Windows app that reads any selected text aloud with a
local neural TTS. Press a hotkey in **any** program (browser, PDF
reader, Word, terminal — anywhere) and a clean floating panel shows
the sentence with a karaoke-style highlight that follows the voice.

**No cloud. No API keys. No telemetry.** The text never leaves your
machine.

---

## Features

- 🔊 Reads any selected text via a global hotkey, layout-independent.
- 🎙 Local neural TTS via [Piper](https://github.com/rhasspy/piper).
  A built-in Voice Manager installs curated voices from the
  [piper-voices](https://huggingface.co/rhasspy/piper-voices)
  catalogue (currently 18 voices spanning English / German / Spanish
  / French / Italian / Hungarian / Polish / Dutch / Portuguese).
- 📺 Floating reader panel: the sentence sits still, only a thin mint
  underline slides under the spoken word; surrounding words gently fade
  in and out as the cursor passes.
- ⚙ Dark, card-based Settings — voice, speed, variation, hotkeys,
  reader-panel options, Windows context-menu integration.
- 🚀 Tray icon, autostart on login, single tiny process.
- 🔌 **Plugin host** — `pippal.plugins` lets a separate package register
  engines, settings cards, hotkey actions, tray items and config
  defaults without touching the core. The paid build adds Kokoro, AI
  actions and mood presets through this same API.

## Editions

PipPal ships in two editions. The Community edition is this open-source
repo; the Microsoft Store edition adds a few quality-of-life features
on top through a separate proprietary plugin.

| | Community (this repo) | Microsoft Store edition |
|---|---|---|
| Source | MIT, [public](https://github.com/bug-factory-kft/pippal) | Community + the proprietary `pippal_pro` plugin |
| Engine | Piper | Piper + Kokoro |
| Hotkeys | Read / Queue / Pause / Stop | + Summary / Explain / Translate / Define |
| AI | — | Local Ollama (offline LLM) |
| Tray menu | Recent / Settings / Quit | + Mood presets |
| Settings cards | Voice / Speech / Hotkeys / Panel / Integration / About | + AI / Ollama |
| Audio export | — | Save selection as WAV |

The Store edition is the same binary plus one extra Python package
(see [the plugin host architecture](#how-the-plugin-host-works)
below). The Community edition stays fully usable on its own — Piper +
the floating reader panel + the right-click integration are the
backbone, the Store edition layers convenience on top.

## Install (Windows, build from source)

Requires Python 3.11+ on `PATH` (or `pythonw` from the standard
install).

```powershell
git clone https://github.com/bug-factory-kft/pippal.git
cd pippal
.\setup.ps1                       # downloads Piper + default voice + pip deps
pythonw reader_app.py             # tray icon appears
```

To start automatically on login, copy `start_server.vbs` to your
Startup folder:

```powershell
copy start_server.vbs "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\PipPal.vbs"
```

`reader_app.py` works whether or not `pippal_pro` is installed —
without it you get the Community feature set; the Microsoft Store
edition bundles it and lights up the extra features.

## Usage

| Action | Default hotkey |
|---|---|
| Read the currently selected text | `Win+Shift+R` |
| Queue selection (append while reading) | `Win+Shift+Q` |
| Pause / Resume | `Win+Shift+P` |
| Stop reading | `Win+Shift+B` |

All combos are reassignable in Settings → Hotkeys. They use the
Windows-key prefix on purpose: browser shortcuts (Ctrl+Shift+T,
Ctrl+Shift+Q, etc.) and AltGr accented characters never collide with
Win-key combos.

Right-click the tray icon for **Settings…**, **Recent** (replay the
last 10 readings), and **Quit**.

## How the plugin host works

`src/pippal/plugins.py` exposes registries for engines, hotkey
actions, settings cards, tray items, AI handlers and config defaults.
The Community package self-registers Piper + four selection-driven
hotkeys + six settings cards in `src/pippal/_register.py`. A
sibling proprietary package (`pippal_pro`, distributed with the
Microsoft Store edition) adds:

- Kokoro engine
- Four AI actions (Summary / Explain / Translate / Define) over local
  Ollama
- Mood preset tray submenu
- AI / Ollama settings card
- Audio export

Discovery is presence-based: `src/pippal/__init__.py` does
`importlib.util.find_spec("pippal_pro")` then imports it if found.
There is no licence/entitlement check in the source — the Microsoft
Store ships a signed MSIX that bundles both packages.

A third-party plugin (e.g. `pippal-elevenlabs`, `pippal-edge-tts`)
could ship today by registering its engine + voice provider through
the same API. The contract is pinned by `tests/test_plugin_host.py`.

## How a read happens

1. Hotkey fires → app sends `Ctrl+C` to the focused app to copy the
   selection, reads the clipboard, restores the previous clipboard.
   Modifier keys for the configured combo are released first so a
   held-down shortcut doesn't garble the copy.
2. Text is split into sentences. The first sentence is synthesised
   immediately; subsequent ones run in parallel with playback.
3. Each chunk's WAV is played via `winsound`. Word timings inside the
   chunk are estimated from the audio duration plus a syllable-weighted
   model with punctuation pause bonuses.
4. The reader panel is a frameless `tk.Toplevel` that uses a transparent
   colour key for soft rounded corners.

## Stack

- **Python** stdlib for everything that isn't UI or audio:
  `urllib.request`, `wave`, `winsound`, `subprocess`, `threading`,
  `importlib`. No `httpx`, no `sounddevice`.
- **`pystray` + `Pillow`** — tray icon
- **`keyboard`** — global hotkeys via a low-level hook with strict
  per-combo suppression (only swallows the exact registered combo)
- **`pyperclip`** — clipboard
- **`tkinter`** — reader panel and settings UI (dark, card-based ttk theme)
- [**Piper**](https://github.com/rhasspy/piper) — TTS engine, called as a subprocess

## Status

**v0.2.0 — public release.** 142 tests, ruff clean. End-to-end smoke
test of the live app on Windows 11: green. See
[docs/CODEREVIEW.md](docs/CODEREVIEW.md) for the multi-reviewer audit
(codex CLI + independent Claude agent + ruff + mypy) that closed
every HIGH and MEDIUM finding before this release.

## Licence

PipPal source is **MIT-licensed** — see [LICENSE.md](LICENSE.md).
Third-party dependencies and downloaded run-time artefacts (Piper,
voice models) are listed with their respective licences in
[docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).
For privacy and terms see [docs/PRIVACY.md](docs/PRIVACY.md) and
[docs/TERMS.md](docs/TERMS.md).
