# Contributing to PipPal

Thanks for taking a look. The codebase is small and intentionally
boring — the goal is for a new contributor to be productive in
about an hour.

## Quick start

```powershell
git clone https://github.com/tigyijanos/pippal.git
cd pippal
.\setup.ps1                       # one-shot: piper + default voice
python -m pip install -e ".[dev]" # editable install + dev deps
python -m pytest -q               # 152 tests should pass
ruff check pippal tests
```

To run the app from a working tree:

```powershell
pythonw reader_app.py     # how the autostart launches it
# or
python -m pippal          # canonical CLI form
```

## Layout

```
pippal/
├── app.py             # main() — wires everything together
├── engine.py          # TTSEngine — orchestration and playback
├── engines/           # PiperBackend, KokoroBackend (one file per class)
├── ui/                # Tk widgets (one file per class)
├── command_server.py  # localhost HTTP for the right-click client
├── tray.py            # tray icon image factory
├── config.py / history.py   # JSON persistence
├── voices.py / moods.py     # catalogues + helpers
└── text_utils.py / wav_utils.py / ollama_client.py / context_menu.py
tests/                  # pytest, pure-logic only (UI is not unit-tested)
```

The rule of thumb: **one class per file**, behind one clear
responsibility. If a file gets past ~500 lines or mixes two
concerns, split it.

## Tests

`pytest` only covers the pure-logic modules (text utils, WAV utils,
voices, moods, history, config, Ollama client, engine state, tray
theme palette). The UI is intentionally not unit-tested — Tk roots
are brittle in headless CI. UI changes get tested by running the
app.

Add a test for any new pure-logic helper.

## Lint and type-check

```powershell
ruff check pippal tests        # zero errors expected
mypy --ignore-missing-imports pippal
```

`mypy` will report ~12 Tk-overload mismatches — those are noise from
the third-party stubs and intentionally left.

## Commits

- Subject ≤ 70 chars, imperative.
- Body: what changed and **why**, not how.
- One concern per commit. If the diff covers two unrelated
  refactors, split them.
- Don't push to `main` unless CI is green.

## Architecture notes

- The engine talks to UI via duck-typed `_OverlayProto` /
  `_RootProto` so it never imports Tk.
- Backends implement `TTSBackend` ABC; `make_backend(config)` is the
  single entry point. Adding a backend = one file under
  `pippal/engines/` plus an entry in `factory.py`.
- All Tk widget construction is single-class-per-file under
  `pippal/ui/`. The dark palette and `make_card` helper live in
  `ui/theme.py`.

## Adding a new hotkey-driven AI action (9th and beyond)

There are three places to touch — single source of truth lives in
`pippal/config.py`:

1. **`pippal/config.py`** — add a row to `HOTKEY_ACTIONS` (action_id,
   hotkey-config-key, settings-row-label) and a default hotkey to
   `DEFAULT_CONFIG`.
2. **`pippal/ollama_client.py`** — add a `PROMPT_<action>` string and
   a `num_predict` row in `AI_NUM_PREDICT`.
3. **`pippal/engine.py`** — add a one-line `speak_<action>_async`
   method that delegates to `ai_runner.run_ai_action(self, "<action>")`,
   and `pippal/app.py` — wire it into `action_handlers`.

`Settings` will pick the new row up automatically (it iterates
`HOTKEY_ACTIONS`). The tray menu reads from `action_handlers`. Tests
in `tests/test_ollama_client.py` enforce that `AI_NUM_PREDICT`
contains the action id.

## Adding a new TTS backend

1. New file `pippal/engines/<name>.py` with a `class XBackend(TTSBackend)`.
2. One row in `pippal/engines/factory.py:make_backend`.
3. One mood preset (or more) in `pippal/moods.py` if it has voices
   worth exposing in the tray.
4. A short test in `tests/test_engines.py` mocking `is_available`.

Don't forget: backends must accept a `config: dict[str, Any]` and read
their parameters from there. Engine passes a fresh dict for translate
voice override, so backends must not mutate `self.config`.

## What we won't take

- Adding a new dependency without checking how often it's needed
  and whether stdlib will do (we use `urllib.request` not
  `httpx`, `winsound` not `sounddevice`, `wave` for WAV math).
- A pretty refactor with no test coverage. Refactor + tests in the
  same PR.
- Auto-update / telemetry / cloud sync. PipPal is offline-first by
  design.
