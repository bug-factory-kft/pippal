<!-- Absolute URL because GitHub's "Community" tab (?tab=contributing-ov-file)
     resolves relative image paths against the repo root rather than the
     file's actual directory, hiding the image there. The blob view of
     docs/CONTRIBUTING.md handles a relative path fine on its own. -->
<p align="center"><img src="https://raw.githubusercontent.com/bug-factory-kft/pippal/main/docs/pippal_contribute.png" alt="PipPal contribute" width="280"></p>

# Contributing to PipPal

Thanks for taking a look. The codebase is small and intentionally
boring — a new contributor should be productive in about an hour.

## Quick start

```powershell
git clone https://github.com/bug-factory-kft/pippal.git
cd pippal
.\setup.ps1                       # one-shot: piper + default voice
python -m pip install -e ".[dev]" # editable install + dev deps
python -m pytest -p no:cacheprovider # current Core unit suite should pass
python -m ruff check .
```

Run the app from a working tree:

```powershell
pythonw reader_app.py     # how the autostart launches it
# or
python -m pippal          # canonical CLI form
```

## Layout

```
src/pippal/
├── plugins.py          # registry — engines, hotkeys, cards, tray, defaults
├── _register.py        # core self-registers piper / hotkeys / cards
├── app.py              # main() — composes engine, overlay, tray, hotkeys
├── engine.py           # TTSEngine — orchestration and playback dispatch
├── engines/            # PiperBackend + the TTSBackend ABC
├── ui/                 # Tk widgets (one file per class), dark theme
├── command_server.py   # localhost HTTP for the right-click client
├── tray.py             # tray icon image factory
├── config.py           # layered defaults + user overrides
├── history.py          # JSON persistence for the Recent submenu
├── voices.py           # Piper voice catalogue + helpers
└── text_utils.py / wav_utils.py / context_menu.py / paths.py / timing.py / onboarding.py
tests/                  # pytest, pure-logic only (UI is not unit-tested)
```

The rule of thumb: **one class per file**, behind one clear
responsibility. If a file gets past ~500 lines or mixes two concerns,
split it.

The paid Microsoft Store edition adds a separate proprietary plugin
package. The public `pippal` package never imports it by name; the
plugin host wires things up at runtime via registry lookups.

## Tests

```powershell
python -m pytest -p no:cacheprovider
```

Pytest only covers pure-logic modules (text utils, WAV utils, voices,
history, config, engine state, plugin host contract).
The UI is intentionally not unit-tested — Tk roots are brittle in
headless CI. UI changes get tested by running the app.

Add a test for any new pure-logic helper. The plugin-host contract
tests (`tests/test_plugin_host.py`) pin the registry shape that
third-party plugins code against — extend them when you change the
public registry API.

`pytest.ini` is the single pytest configuration source. Do not mirror
the same options in `pyproject.toml`; pytest ignores that block when
`pytest.ini` exists and prints a release-gate warning.

## Benchmarks

Microbenchmarks for the latency-sensitive helpers live under
`tests/benchmarks/` and are skipped from the default `pytest` run
so the unit suite stays fast and deterministic. Run them explicitly:

```powershell
python -m pytest tests/benchmarks --benchmark-only
```

To save a baseline and compare later runs against it:

```powershell
python -m pytest tests/benchmarks --benchmark-only --benchmark-save=baseline
# … hack the code …
python -m pytest tests/benchmarks --benchmark-only --benchmark-compare=baseline
```

Coverage groups:

- `hotkey` — LL-hook dispatch latency. Must stay well under the
  Windows 1 s `LowLevelHooksTimeout`. Pass-through (~400 ns) and
  repeat-suppress (~360 ns) are the keystroke-by-keystroke paths;
  the match-and-dispatch path is dominated by `threading.Thread.start()`
  (~70 µs) — still cheap relative to the timeout but the obvious
  thing to optimise if it ever matters.
- `text_utils` — sentence splitting + word iteration + karaoke
  layout, run per synthesis chunk. Article-sized text splits in
  ~15 µs.
- `voices` — catalogue lookups + the on-disk glob; the latter is
  the disk-bound floor for `Settings → Voice` populating its combo.
- `plugins` — registry hot-path lookups (engine, voice, hotkey).
  All under 250 ns, so 1000s of dispatches per second is easy.
- `io` — config / history JSON round-trip, WAV duration + concat,
  tray-icon factory first-paint and cache-hit. The atomic
  `save_config` lands around 600 µs; the cache-hit `make_tray_icon`
  is ~60 ns (matters because the tray-tick fires every 400 ms).

## Lint and type-check

```powershell
python -m pytest -p no:cacheprovider # zero failures and no pytest config warning expected
python -m ruff check .              # zero errors expected
```

`mypy` is advisory for the Core package on this branch, not a blocking
release gate. The current typed surface still reports Tk/Pillow/UI
attribute debt under Python 3.14. Use this command when reviewing type
drift, and split a follow-up before promoting it to a release gate:

```powershell
python -m mypy --ignore-missing-imports --cache-dir "$env:TEMP\pippal-mypy" src\pippal
```

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

Then register it. The built-in package does this in
`src/pippal/_register.py`; a third-party plugin does it in its own
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
plugins.register_plugin_action("my-action", my_action_handler)
```

The Settings → Hotkeys card iterates `plugins.hotkey_actions()`, the
app's hotkey binder iterates the same list and looks the handler up
in `plugins.plugin_actions()`. No edits required to `app.py`,
`config.py`, or `settings_cards.py`.

## What we won't take

- **New dependencies** without checking how often they'd actually be
  used and whether stdlib will do. We use `urllib.request` not
  `httpx`, `winsound` not `sounddevice`, `wave` for WAV math.
- **A pretty refactor with no test coverage.** Refactor + tests in
  the same PR.
- **Auto-update / telemetry / cloud sync.** PipPal is offline-first
  by design.
- **Re-implementations of paid-edition features.** Those ship in a
  separate proprietary plugin. If you'd like to contribute a similar
  feature, build it as a separate plugin package using the API
  documented above.
