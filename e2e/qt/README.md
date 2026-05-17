# PipPal PySide6 UI E2E suite

`pytest-qt` end-to-end tests for the migrated PySide6 frontend
(`pippal.ui_qt`). They drive the **real Qt widgets** with **real input
events** (`qtbot.mouseClick`, `qtbot.keyClicks`) and **explicit waits**
(`qtbot.waitUntil`, `qtbot.waitExposed`, `waitSignal`) — there are no
fixed `sleep`s. The backend is the real PipPal backend (config,
engine, voices, history, playback); only the data directory is
isolated to `tmp_path`, and the read-aloud test substitutes an
in-process fake TTS backend that still writes a genuine RIFF/WAVE file
so the assertion is on the real engine effect, not a mock.

## What it covers

| Test | Exercises |
|---|---|
| `test_settings_edit_spinbox_persists_to_config_json` | Edit a real setting widget → click real **Save** → assert `config.json` on disk + `load_config()` |
| `test_settings_edit_hotkey_lineedit_with_real_keystrokes` | `qtbot.keyClicks` into the hotkey `QLineEdit` → **Apply** → assert persisted, window stays open |
| `test_settings_cancel_does_not_persist` | **Cancel** discards edits, nothing saved |
| `test_settings_has_all_seven_card_keys` | Config-key parity with the 7 Tk cards |
| `test_voice_manager_search_filter_and_close` | Open Voice Manager, type in Search, real catalogue narrows, real **Close** click |
| `test_voice_manager_status_filter_changes_rows` | Status filter (Installed/Any) re-renders the real row list |
| `test_read_aloud_drives_engine_and_writes_real_wav` | `read_text_async` → real engine pipeline → real RIFF/WAVE chunk on disk while `is_speaking`, correct backend class, history recorded |
| `test_read_aloud_no_voice_plays_onboarding_overlay` | No ready backend → real onboarding fallback drives the overlay into `reading` |
| `test_reader_panel_buttons_invoke_engine` | Real mouse clicks on the prev/replay/next/close hit-rects call the engine |
| `test_reader_panel_respects_show_overlay_off` | `show_overlay=False` keeps the panel hidden (same gate as Tk) |
| `test_reader_panel_shows_for_active_states[thinking/reading]` | Panel shows for active states |

## Run it

From a fresh clone (Windows; uses the real `py -3.11`, the
Microsoft-Store `python` stub will not work):

```powershell
py -3.11 -m venv .venv-qt
.\.venv-qt\Scripts\python.exe -m pip install -r e2e\qt\requirements.txt
.\.venv-qt\Scripts\python.exe -m pytest e2e\qt -v
```

Headless / CI (no display) — Qt's offscreen platform plugin works and
the suite still passes:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv-qt\Scripts\python.exe -m pytest e2e\qt -v
```

The suite is independent of the legacy live-UI harness: `e2e/qt`'s
own `conftest.py` shadows the parent `e2e/conftest.py` session gate,
so you do **not** need `PIPPAL_E2E_LIVE` or a launched desktop app.

## Last run

```
12 passed
```

(real Qt platform and `QT_QPA_PLATFORM=offscreen` both green;
`PySide6 6.11.1`, `pytest 9.0.3`, `pytest-qt 4.x`, Python 3.11.9)
