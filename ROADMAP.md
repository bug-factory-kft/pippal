# PipPal — Roadmap

> Your little offline reading buddy.

PipPal is a tray-resident Windows app that reads selected text aloud,
anywhere in Windows, using a local neural TTS engine. Press a hotkey,
get a clean reader panel with karaoke-style highlighting. No cloud,
no API keys, no telemetry.

This document tracks where we are and where we're heading.

---

## Current state (v0.1)

- Tray app (`pythonw reader_app.py`) with autostart on login.
- Global hotkeys: `Ctrl+Shift+X` read selection, `Ctrl+Shift+Z` stop.
- Capture-via-clipboard (saves and restores user's clipboard).
- TTS engine: **Piper** (`piper.exe` + `.onnx` voice models).
- Sentence-chunked synthesis with prefetch of next chunk during playback.
- Floating reader panel (frameless tk Toplevel with rounded corners via
  `-transparentcolor`):
  - Static text laid out per chunk.
  - Smooth underline marker slides between words on the same line,
    snaps at line breaks.
  - Per-word color fade in/out near the cursor (~0.5 s window).
  - Progress bar + chunk counter (`2/5`).
- Settings window (dark, card-based ttk theme):
  - Voice picker (with download manager for known voices).
  - Speed (length_scale), variation (noise_scale).
  - Hotkey rebind.
  - Overlay options (toggle, karaoke toggle, auto-hide, position).
- Voice manager: one-click install/remove of curated Piper voices
  from huggingface.co/rhasspy/piper-voices.

---

## Tier 1 — Quality leap

The goal: the reading itself feels noticeably more human, and the karaoke
is exact rather than estimated.

### 1.1 Kokoro TTS engine (alternative to Piper) — ✅ done

- Pluggable `TTSBackend` abstraction; `PiperBackend` and `KokoroBackend`
  both live in `reader_app.py`.
- Engine selectable in Settings → Voice card (`piper` / `kokoro`).
- Per-engine voice picker; Kokoro voices use a curated subset
  (`af_bella`, `am_adam`, `bf_emma`, `bm_george`, …).
- Built-in Kokoro installer dialog: pip-installs `kokoro-onnx` +
  `soundfile`, then downloads `kokoro-v1.0.onnx` (~325 MB) and
  `voices-v1.0.bin` (~28 MB) with progress.
- Lazy model load: Kokoro only initialised on first use; model stays
  in memory once loaded.
- `length_scale` is shared between engines (mapped to Kokoro's `speed`
  via 1/x).

### 1.2 Accurate per-word timestamps — partial

- ✅ **Syllable-weighted timing** + a punctuation pause bonus replace the
  earlier character-count heuristic. Words are weighted by their estimated
  syllable count (vowel-group counting with silent-`e` handling), and
  words ending in `.`, `!`, `?`, `,`, `;`, `:`, `—`, `–` get an extra
  fractional weight matching the natural pause length. Accuracy went
  from "follows roughly" to "tracks the spoken word inside its window".
- ⏳ **Real forced alignment** is the remaining work. Piper does emit
  phoneme JSON when invoked the right way; Kokoro's pipeline yields
  phoneme durations natively. A future pass should hook into one of
  these to drop the residual drift on long sentences. A `whisper-cpp`
  / `faster-whisper` post-pass is also an option as an opt-in
  "perfect karaoke" toggle.

### 1.3 Pause / resume — ✅ done

- `Ctrl+Shift+P` toggles pause/resume.
- Pause silences `winsound`, freezes the karaoke timer in the overlay,
  and shows a small `paused` chip near the top of the panel.
- Resume restarts the **current chunk** from its beginning (winsound
  has no sample-accurate seek, so we replay the sentence). Karaoke
  timer is shifted so the highlight resumes from where it froze.
- Tray menu has a Pause / Resume entry too.

A future refinement could swap `winsound` for `sounddevice` to support
true seek-within-chunk; the WAV-cache logic from the mini-player
already keeps chunk audio on disk so the change would be local.

### Done criteria for Tier 1
- Engine choice is persisted and applies on the next read.
- Karaoke underline visually tracks the audio ±1 word boundary.
- Pause/resume works on multi-sentence selections.

---

## Tier 2 — AI integration (Ollama) — ✅ done

Local Ollama hands off selected text and PipPal reads the response aloud,
fully offline.

- **Summary** (`Ctrl+Shift+S`) — 1–2 sentence TL;DR of the selection.
- **Explain** (`Ctrl+Shift+E`) — plain-language explanation (2–4 sentences).
- **Translate** (`Ctrl+Shift+T`) — translates to the configured target
  language (default Hungarian).
- **Define** (`Ctrl+Shift+D`) — short dictionary-style definition with
  a usage example.
- New `OllamaClient` (stdlib only) talks to `/api/tags` and `/api/chat`.
- New AI card in Settings: endpoint URL, model picker (auto-fills from
  installed Ollama models, with Refresh button), translate target.
- The reader panel header shows the action label during AI runs
  (`PipPal · summary`).
- Each AI action runs through the same synthesize-and-play pipeline,
  so karaoke + Kokoro/Piper engine choice all apply.

Caveat: translate is read with the current voice — for non-English
targets, install a matching Piper voice (e.g. `hu_HU-anna-medium`) and
switch in the Voice card. Future improvement: per-language voice routing.

---

## Tier 3 — Convenience

### Done so far

- ✅ **Mini-player controls** in the reader panel: ⏮ prev / ⟲ replay /
  ⏭ next. Click jumps to the previous, current, or next sentence.
  Engine refactored to keep all chunk WAVs around for the duration of
  the read so seeking back is seamless.
- ✅ **Auto translate voice**: when `Ctrl+Shift+T` translates to a
  language other than the current voice, PipPal looks for an installed
  Piper voice matching that locale (`LANG_TO_PIPER` map) and uses it
  for that read only — restoring the previous voice/engine afterward.
- ✅ **Multi-language voice catalogue**: Voice Manager now lists
  Hungarian, German, Spanish, French, Italian, Polish, Portuguese,
  Dutch options alongside the English voices.

- ✅ **Export to WAV**: tray menu **Save selection as audio…** captures
  the current selection, synthesises every sentence, concatenates the
  WAVs, and writes one file at a user-chosen path. Engine-agnostic
  (works with both Piper and Kokoro).

- ✅ **Reading queue**: `Ctrl+Shift+Q` (or tray *Queue selection*) appends
  the current selection to the queue. PipPal reads each in order. The
  panel shows a brief `Queued — N pending` toast on each add. Default
  Read (`Ctrl+Shift+X`) still replaces / clears the queue, so the two
  modes don't surprise each other.
- ✅ **Recent history**: last ~10 readings are persisted in
  `history.json` and exposed via the tray *Recent* submenu. Clicking
  any entry replays it (clears the queue first). Dedupes on add.
  Cleared from the tray menu.

### Still on the list
- **MP3 export**: same as WAV but ffmpeg-encoded, smaller files for
  phone/car listening.
- **PDF / EPUB import**: open a document, read it sentence-by-sentence
  with progress saved across sessions.
- **History**: recent readings, replay any.

---

## Tier 4 — Showcase features

- ✅ **Mood / style presets**: tray *Mood* submenu with curated voice
  bundles — Warm (Bella), Calm (Heart), Bedtime (Nicole), Energetic
  (Puck), Dramatic (Fenrir), News (Michael), British (George/Emma),
  Default (Ryan/Piper). One click swaps engine + voice + speed +
  noise_scale and persists to config.
- ✅ **Right-click "Read with PipPal"** in File Explorer: a small
  HTTP IPC server runs inside PipPal on `127.0.0.1:51677`; a tiny
  `pippal_open.py` client posts the file path; the running app reads
  the file aloud. Settings → *Windows integration* installs/removes
  the registry entries (`HKCU\Software\Classes\SystemFileAssociations\
  .{txt,md}\shell\PipPal\command`). Per-user, no admin needed.

### Still on the list

- **Browser companion**: optional Firefox/Chrome extension for
  reader-mode pages, ad-stripped article reading.
- **Ambient bed**: subtle background music while reading (audiobook
  vibe). Per-voice presets.
- (Voice cloning intentionally dropped — out of scope.)

---

## Architecture notes

- Single-process Python app. No HTTP server, no IPC. The hotkey thread
  hands work to a synthesis thread, which uses an audio-player thread.
  All UI operations are funnelled through `root.after(0, ...)` for
  thread safety.
- `tk.Toplevel` with `overrideredirect(True)` and a transparent colour
  key gives the rounded floating panel without native frame.
- Engine abstraction (Tier 1) will live in `engines/`:
  - `engines/base.py` — `TTSBackend` ABC.
  - `engines/piper.py` — current logic moved here.
  - `engines/kokoro.py` — new.
  - Settings selects by name; config persists.
- For the AI tier, an `ai/ollama.py` thin client (no extra deps; just
  `urllib`) calls `http://localhost:11434/api/chat`.

---

## Non-goals

- No telemetry, no auto-update beacons, no analytics.
- No cloud TTS by default (Edge TTS could be an opt-in engine for
  comparison only).
- No mobile port. Windows-first; Linux/macOS may follow if there's a
  reason.
