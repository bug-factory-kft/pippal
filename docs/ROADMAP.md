# PipPal — Roadmap

> Your little offline reading buddy.

PipPal is a tray-resident Windows app that reads selected text aloud,
anywhere in Windows, using a local neural TTS engine. Press a hotkey,
get a clean reader panel with karaoke-style highlighting. No cloud,
no API keys, no telemetry.

This document tracks the **public Free** roadmap. The paid
Microsoft Store edition adds extra features through a separate
proprietary plugin — those are out of scope for this open-source
project's roadmap.

---

## Current state — Core v0.2.3 (public release, 2026-05-13)

- Tray app (`pythonw reader_app.py`) with autostart on login.
- Plugin-host architecture (`pippal.plugins`) — engines, settings
  cards, hotkey actions, tray items and config defaults all
  pluggable.
- TTS engine: **Piper** (`piper.exe` + `.onnx` voice models),
  registered through the plugin host.
- Global hotkeys (Win+Shift letter scheme, layout-independent,
  low-level hook with strict per-combo suppression so unrelated
  shortcuts like Win+Shift+S aren't accidentally eaten):
  - Read selection
  - Queue selection (append while reading)
  - Pause / Resume
  - Stop
- Sentence-chunked synthesis with prefetch of next chunk during
  playback. Pinned per-text backend so a mid-text plugin reload can't
  swap voices mid-paragraph.
- Floating reader panel (frameless `tk.Toplevel` with rounded corners
  via transparent colour key):
  - Static text laid out per chunk.
  - Smooth underline marker slides between words on the same line,
    snaps at line breaks.
  - Per-word colour fade in/out near the cursor (~0.5 s window).
  - Progress bar + chunk counter (`2/5`).
  - Mini-player controls: ⏮ prev / ⟲ replay / ⏭ next.
- Settings window (dark, card-based ttk theme):
  - Voice picker (with Voice Manager for curated Piper voices).
  - Speed (length_scale), variation (noise_scale).
  - Hotkey rebind with explicit unbind-failure feedback.
  - Reader-panel options (toggle, karaoke toggle, auto-hide,
    position, karaoke offset).
  - Windows context-menu integration for `.txt` and `.md`.
  - Apply / Save / Reset to defaults / Cancel buttons.
- Voice Manager: one-click install/remove of curated Piper voices
  from huggingface.co/rhasspy/piper-voices. 18 voices across 9
  languages (English US/UK, German, Spanish, French, Italian,
  Hungarian, Polish, Dutch, Portuguese).
- Layered config: only user overrides land in `config.json`; plugin
  defaults overlay at runtime. Uninstalling a plugin doesn't strand
  its defaults on disk.
- Right-click integration: Explorer context-menu "Read with PipPal"
  for `.txt` / `.md` files via a localhost IPC server.
- Clean cancel-exit: stop drains in-flight prefetch threads and
  cleans up chunk WAVs before exiting; tray icon flips to idle
  authoritatively.

Current validation should be checked from command output with
`python -m pytest` and `python -m ruff check .`; fixed test counts are
kept out of this roadmap so they do not drift. The historical
multi-reviewer audit is tracked in [CODEREVIEW.md](CODEREVIEW.md).

---

## Next release focus - Core v0.2.4

- First-run activation: make a new Core user hear selected text within
  60 seconds of first launch. The implementation contract, screen
  copy, failure states and acceptance checks are in
  [FIRST_RUN_ACTIVATION.md](FIRST_RUN_ACTIVATION.md).

---

## Open Free roadmap

Things the open-source Free build will pick up next, in roughly the
priority order users have asked about.

### 1. Real per-word forced alignment (replace syllable estimate)

Today's karaoke uses syllable-weighted timing plus a punctuation
pause bonus — accurate within ~1 word boundary on most sentences but
drifts on long ones. Piper can emit phoneme JSON when invoked the
right way; hooking into that drops the residual drift to near-zero.
A `whisper-cpp` / `faster-whisper` post-pass is also an option as an
opt-in "perfect karaoke" toggle.

### 2. PDF / EPUB import

Open a document, read it sentence-by-sentence with progress saved
across sessions. PDF page numbers in the chunk counter, EPUB chapter
boundaries respected. Reader-mode for both.

### 3. Browser companion

Optional Firefox / Chrome extension for reader-mode pages and
ad-stripped article reading. Sends the cleaned text to PipPal's
existing localhost IPC server (already used by the Explorer
right-click helper).

### 4. Linux / macOS port

Windows-first by necessity (`winsound`, `pystray` quirks, the
keyboard-hook semantics). A port would need:
- Replace `winsound.PlaySound` with `simpleaudio` or `sounddevice`.
- Replace `pystray` Win32 path with the Cocoa / X11 / Wayland paths
  it already supports.
- Replace `keyboard` global hooks with platform-specific equivalents
  (`pynput` may suffice).

This is a "if there's clear demand" thing — open an issue if you'd
use it.

### 5. Sample-accurate seek inside a chunk

Currently pause/resume restarts the current sentence from the start
because `winsound` has no sample-accurate seek. Switching to
`sounddevice` (already needed for Linux/macOS) gets us this
naturally.

---

## Non-goals

- No telemetry, no auto-update beacons, no analytics. Ever.
- No cloud TTS in the open-source build. (Edge TTS could be an opt-in
  via a separate plugin if a contributor wants it.)
- No mobile port. PipPal is a desktop reader. A mobile companion
  could exist but it isn't part of this codebase.
- No voice cloning. Out of scope, ethically fraught, not in line with
  the offline-first promise.

---

## Paid edition

The Microsoft Store edition layers extra features on top through a
separate proprietary plugin — see the Store listing for what that
edition includes. Those features are out of scope for this
open-source roadmap.

If those interest you, the paid Microsoft Store build is the way.
The plugin host is also fully public, so a third-party
`pippal-elevenlabs` / `pippal-edge-tts` / `pippal-azure-speech`
plugin could ship today.
