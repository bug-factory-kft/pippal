<p align="center"><img src="pippal_contribute.png" alt="PipPal contribute" width="280"></p>

# Contributing to PipPal

Thanks for taking a look. The codebase is small and intentionally
boring — a new contributor should be productive in about an hour.

## Quick start

```powershell
git clone https://github.com/bug-factory-kft/pippal.git
cd pippal
.\setup.ps1                       # one-shot: piper + default voice
python -m pip install -e ".[dev]" # editable install + dev deps
python -m pytest -q               # 142 tests should pass
ruff check pippal tests
```

Run the app from a working tree:

```powershell
pythonw reader_app.py     # how the autostart launches it
# or
python -m pippal          # canonical CLI form

# Force a Free-only run even if pippal_pro is on the path:
pythonw reader_app_free.py
```

## Layout

```
src/pippal/
├── plugins.py          # registry — engines, hotkeys, cards, tray, defaults
├── _register_free.py   # Free distribution self-registers everything
├── app.py              # main() — composes engine, overlay, tray, hotkeys
├── engine.py           # TTSEngine — orchestration and playback dispatch
├── engines/            # PiperBackend + the TTSBackend ABC
├── ui/                 # Tk widgets (one file per class), dark theme
├── command_server.py   # localhost HTTP for the right-click client
├── tray.py             # tray icon image factory
├── config.py           # layered defaults + user overrides
├── history.py          # JSON persistence for the Recent submenu
├── voices.py           # Piper voice catalogue + helpers
├── ollama_client.py    # tiny stdlib HTTP client (used by pippal_pro)
└── text_utils.py / wav_utils.py / context_menu.py / paths.py / timing.py
tests/                  # pytest, pure-logic only (UI is not unit-tested)
```

The rule of thumb: **one class per file**, behind one clear
responsibility. If a file gets past ~500 lines or mixes two concerns,
split it.

`pippal_pro/` (Pro extensions — Kokoro engine, AI actions, mood
presets, audio export) lives in a separate **private** repo. The
public `pippal` package never imports it; the plugin host wires
things up at runtime via registry lookups.

## Tests

```powershell
python -m pytest -q
```

Pytest only covers pure-logic modules (text utils, WAV utils, voices,
history, config, Ollama client, engine state, plugin host contract).
The UI is intentionally not unit-tested — Tk roots are brittle in
headless CI. UI changes get tested by running the app.

Add a test for any new pure-logic helper. The plugin-host contract
tests (`tests/test_plugin_host.py`) pin the registry shape that
third-party plugins code against — extend them when you change the
public registry API.

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
- One concern per commit. If the diff covers two unrelated refactors,
  split them.
- Don't push to `main` unless CI is green.

## Architecture notes

- The engine talks to UI via duck-typed `_OverlayProto` /
  `_RootProto` so it never imports Tk.
- Backends implement `TTSBackend` ABC. The factory looks up the
  requested engine by name in `pippal.plugins.engines()`; falls back
  to whatever's registered for `"piper"` (which the Free package
  always registers).
- All Tk widget construction is single-class-per-file under
  `src/pippal/ui/`. The dark palette and `make_card` helper live in
  `ui/theme.py`.
- Config is **layered**: `core_defaults + plugin_defaults +
  user_overrides`. Only user overrides land in `config.json`, so
  uninstalling a plugin doesn't strand its defaults on disk.
  Unknown keys (a Pro setting saved while Pro was installed, then Pro
  uninstalled) are preserved verbatim — codex' "don't destroy user
  state when a plugin is absent" principle.

## Adding a new TTS backend

A whole new engine ships as one file plus one registration. Backends
written for the Free repo should be MIT-compatible and shipped in
`src/pippal/engines/`; proprietary engines live in their own package and
register themselves on import.

```python
# pippal/engines/example.py  (or any plugin package's __init__)
from pippal.engines.base import TTSBackend

class ExampleBackend(TTSBackend):
    name = "example"

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, out_path) -> bool:
        # ... write a WAV at out_path ...
        return True
```

Then register it. The Free package does this in
`src/pippal/_register_free.py`; a third-party plugin does it in its own
`__init__.py`:

```python
from pippal import plugins
plugins.register_engine("example", ExampleBackend)
```

The factory will dispatch by name automatically; the Settings →
Voice card will list the new engine in the dropdown.

For a quick test:

```python
# tests/test_engines.py — only if the engine ships in this repo
from pippal.engines import make_backend
def test_example():
    backend = make_backend({"engine": "example"})
    assert backend.name == "example"
```

## Adding a new hotkey-driven action

Use the registry. No file needs to know your action by name except
the one that registers it.

```python
from pippal import plugins

def my_action_handler(engine, action_id):
    # ... do something with engine.config etc. ...
    pass

plugins.register_hotkey_action(
    "my-action",                  # action_id
    "hotkey_my_action",           # config key persisted in config.json
    "My Action",                  # label shown in the Hotkeys settings row
    "windows+shift+m",            # default combo (also seeds defaults registry)
)
plugins.register_ai_action("my-action", my_action_handler)
```

The Settings → Hotkeys card iterates `plugins.hotkey_actions()`, the
app's hotkey binder iterates the same list and looks the handler up
in `plugins.ai_actions()`. No edits required to `app.py`,
`config.py`, or `settings_cards.py`.

## What we won't take

- **New dependencies** without checking how often they'd actually be
  used and whether stdlib will do. We use `urllib.request` not
  `httpx`, `winsound` not `sounddevice`, `wave` for WAV math.
- **A pretty refactor with no test coverage.** Refactor + tests in
  the same PR.
- **Auto-update / telemetry / cloud sync.** PipPal is offline-first
  by design.
- **Pro-feature ports** (Kokoro, AI, mood presets, audio export).
  Those are proprietary and ship in `pippal_pro`. If you'd like to
  contribute a similar feature, build it as a separate plugin package
  using the API documented above.
