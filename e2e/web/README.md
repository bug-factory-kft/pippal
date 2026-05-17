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

## Coverage

```text
test_settings_renders_seven_cards          7 cards + key controls present
test_settings_edit_persists_to_backend     slider + spinbox -> config.json + live config
test_settings_hotkey_edit_rebinds...       hotkey edit -> persisted + host rebind callback fired
test_voice_manager_lists_catalogue         row count == real plugins.voices() catalogue
test_voice_manager_search_filter           "ryan" -> 1 row; nonsense -> empty state
test_voice_manager_status_filter           Installed/Not installed filter vs real disk state
test_read_aloud_drives_real_engine         Play sample / read_text -> engine reacts (is_speaking/overlay)
test_overlay_panel_buttons_call_engine     overlay close -> engine.stop() (token bump)
test_overlay_prev_replay_next_reach_engine prev/replay/next reach engine, stay healthy
test_onboarding_renders_and_closes         first-run window renders + Skip/Close present
test_notices_window_loads_real_text        licences viewer == real notices resolver output
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

Headed (watch it drive the UI): append `--headed`.

## Notes

- These tests do **not** require `PIPPAL_E2E_LIVE=1`; the local
  `conftest.py` overrides the Tk live-desktop gate from
  `e2e/conftest.py` because the web suite is self-contained (no
  `reader_app.py` launch, no tray, no global hotkey hook).
- `test_read_aloud_drives_real_engine` asserts the real engine reacts.
  Without a local Piper engine in the checkout, the read path plays the
  bundled onboarding clip and still flips `is_speaking` / overlay
  state — a real audio/engine effect, not a mock. With Piper + a voice
  installed it exercises real synthesis.
- Physical speaker output is not asserted (that needs a loopback
  capture device); the engine/audio *effect* is.
