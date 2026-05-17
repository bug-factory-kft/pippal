# PipPal web-UI E2E (Playwright)

End-to-end tests for the **migrated web frontend** (`webui/` +
`src/pippal/web_ui/`). They drive the **real** static UI served by the
**real** bridge server wired to the **real** `TTSEngine` and config —
only `PIPPAL_DATA_DIR` is redirected to a throwaway temp profile so a
run never touches your real PipPal state.

This is a true E2E layer: Playwright performs real DOM events
(`fill`, `click`, `select_option`, real `input` events) against stable
`data-testid` selectors, with Playwright auto-waiting (no fixed
sleeps), and every assertion checks an effect on the backend
(config.json on disk, the live `TTSEngine`, the real voice catalogue),
not just rendered text.

## What the served mode is

The same static UI runs in the desktop pywebview window *and* here.
`webui/js/api.js` calls the pywebview bridge object when present and
otherwise falls back to `POST /bridge` on the local server
(`pippal.web_ui.server`). Playwright points Chromium at that server, so
the tests exercise exactly the production frontend code path.

## Human-readable step logging (what each test actually did)

Every test narrates its meaningful actions and assertions through a
small `step` fixture (defined in `conftest.py`) on the Python stdlib
`logging` module:

```python
def test_settings_edit_persists_to_backend(page, app_url, backend, step):
    _goto(page, app_url, "settings", step)
    step("set auto_hide_ms = 2400")          # →  an action
    ...
    step.check("config.json on disk: auto_hide_ms == 2400")   # ✓ a real effect
```

`step("...")` logs an action line (`→`), `step.check("...")` logs an
asserted real effect (`✓`), and `step.group("...")` brackets a
multi-step action. Because it goes through `logging`, pytest captures
it and **`--log-cli-level=INFO` streams it live** while `-rA` prints
the captured step log **for passing tests too** — so a green CI run now
shows exactly what each test did instead of "Passed … no log output
captured".

Sample (one passing test, verbatim CI-style output):

```text
INFO  e2e.web.step:conftest.py:116   start test_settings_renders_seven_cards[chromium]
INFO  e2e.web.step:conftest.py:116   → open 'settings' surface (http://127.0.0.1:.../index.html?view=settings)
INFO  e2e.web.step:conftest.py:116   ✓ surface 'settings' rendered (body[data-ready=settings])
INFO  e2e.web.step:conftest.py:116   ✓ 7 settings cards rendered (.card-title == 7)
INFO  e2e.web.step:conftest.py:116   ✓ engine combo + Save button visible
```

## Run

```powershell
py -3.11 -m venv .venv-web
.\.venv-web\Scripts\python.exe -m pip install -e .
.\.venv-web\Scripts\python.exe -m pip install pywebview
.\.venv-web\Scripts\python.exe -m pip install -r e2e\web\requirements.txt
.\.venv-web\Scripts\python.exe -m playwright install chromium

.\.venv-web\Scripts\python.exe -m pytest e2e\web -q
```

### Run verbose locally (see the steps)

```powershell
# UTF-8 IO so the → / ✓ glyphs render in a cp1252 console.
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
.\.venv-web\Scripts\python.exe -m pytest e2e\web -v -rA --log-cli-level=INFO --browser chromium
```

This is exactly what the `ui-web-e2e.yml` workflow runs (the flags are
passed on the command line, **not** in the root `pytest.ini`, so the
default `python -m pytest` / `tests/` suite is completely unaffected
and `e2e/web` stays excluded from it).

### Watch it live (headed, slow)

```powershell
$env:PYTHONUTF8 = "1"
.\.venv-web\Scripts\python.exe -m pytest e2e\web `
  -k test_read_aloud_full_real_path `
  --headed --slowmo 600 -s --log-cli-level=INFO --browser chromium
```

`--headed` shows the browser, `--slowmo 600` slows each action 600 ms,
`-s` disables output capture so the step lines stream as they happen.

### Open a Playwright trace

A run with `--tracing=on` writes a `trace.zip` per test under the
`--output` dir. Open it in the Playwright trace viewer (DOM snapshots,
network, console, a timeline of every action):

```powershell
.\.venv-web\Scripts\python.exe -m playwright show-trace `
  playwright-report\artifacts\<test-name>-chromium\trace.zip
```

## Playwright artifacts (ALWAYS produced, not only on failure)

The `ui-web-e2e.yml` workflow runs the suite with
`--tracing=on --video=on --screenshot=on --output=playwright-report/artifacts`
and `--html=playwright-report/report.html --self-contained-html`, so
**every** test (even on a fully green run) produces:

| Artifact | Path | Open with |
|---|---|---|
| Trace | `playwright-report/artifacts/<test>/trace.zip` | `playwright show-trace <trace.zip>` |
| Video | `playwright-report/artifacts/<test>/video.webm` | any video player / browser |
| Screenshot | `playwright-report/artifacts/<test>/test-finished-1.png` | any image viewer |
| HTML report | `playwright-report/report.html` | open in a browser |

The workflow uploads the whole `playwright-report/` directory via
`actions/upload-artifact@v4` with `if: always()` under the artifact
name **`web-ui-e2e-playwright-report`** — download it from the GitHub
Actions run page (the *Web UI E2E (served, headless Chromium)* job),
unzip, and open `report.html` or any `trace.zip` as above.

## Notes

- These tests do **not** require `PIPPAL_E2E_LIVE=1`; the local
  `conftest.py` overrides the Tk live-desktop gate from
  `e2e/conftest.py` because the web suite is self-contained (no
  `reader_app.py` launch, no tray, no global hotkey hook).
- `test_read_aloud_drives_real_engine` asserts the real engine reacts.
  Without a local Piper engine in the checkout, the read path plays the
  bundled onboarding clip and still flips `is_speaking` / overlay
  state — a real audio/engine effect, not a mock.
- `test_read_aloud_full_real_path_wav_karaoke_history` (row 4.11)
  deepens that: it registers a **real synth backend** through the
  genuine `plugins.register_engine` extension API (exactly how a
  third-party engine plugin integrates) that writes a valid RIFF/WAVE
  PCM file with the stdlib `wave` module, then drives read-aloud
  through the real served UI and asserts the **full** real path —
  engine becomes `is_speaking`, real per-chunk WAV files on disk
  (RIFF/WAVE, parsed by `wave`), the reader overlay shows and the
  karaoke cursor advances **across** chunks (chunk counter 1/N → 2/N),
  and Recent history records the text. Only the audio *content* is a
  deterministic test tone; the engine, the `pippal.playback` loop, the
  WAV-on-disk, the overlay protocol, the karaoke timing and the history
  round-trip are all unmodified real production code.
- Physical speaker output is not asserted (that needs a loopback
  capture device); the engine/audio *effect* is.
