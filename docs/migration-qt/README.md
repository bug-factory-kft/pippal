# PySide6 UI migration spike

A **parallel** PySide6 frontend wired to the existing PipPal backend.
The legacy Tk UI (`pippal.ui`, `reader_app.py`) is left fully intact;
this is a reviewable migration spike, not a destructive rewrite.

## Run the new (Qt) UI

```powershell
py -3.11 -m venv .venv-qt
.\.venv-qt\Scripts\python.exe -m pip install -r e2e\qt\requirements.txt
.\.venv-qt\Scripts\python.exe reader_app_qt.py
```

`python -m pippal.app_qt` works too. The Tk app is unchanged:
`python reader_app.py` / `python -m pippal`.

## Run the tests

```powershell
.\.venv-qt\Scripts\python.exe -m pytest e2e\qt -v
```

See [`e2e/qt/README.md`](../../e2e/qt/README.md). The existing unit
suite (`py -3.11 -m pytest`, 262 tests) and the legacy live-UI harness
are untouched and still green.

## Screenshots (before = Tk, after = Qt)

Captured by `_capture_tk.py` (drives the real Tk app via its command
server) and `_capture_qt_real.py` (renders the real Qt windows).

| Surface | Tk (before) | Qt (after) |
|---|---|---|
| Settings (7 cards + footer) | `tk-settings.png` | `qt-settings.png` |
| Voice Manager | `tk-voice-manager.png` | `qt-voice-manager.png` |
| First-run / onboarding | `tk-activation-panel.png` | `qt-activation-panel.png` |
| Reader overlay (karaoke) | — | `qt-overlay.png` |
| Open-source notices | — | `qt-notices.png` |

### Visual-parity notes

- Same colour palette: `pippal.ui_qt.theme_qt` imports
  `pippal.ui.theme.UI` so the two frontends share **one** source of
  truth for every colour; they cannot drift.
- Same Segoe UI typeface, uppercase section titles, rounded
  `bg_card` panels, accent-green sliders/primary button, danger
  button styling, dark inputs/combos.
- Same chromeless / dark-titlebar feel: `theme_qt` reuses the same
  DWM immersive-dark-mode + rounded-corners calls the Tk
  `theme._apply_native_titlebar` / `apply_rounded_corners` use.
- The reader overlay reuses `pippal.ui.overlay_paint`'s
  `compute_word_layout` and colour-lerp constants verbatim, so the
  karaoke cursor pacing/colour math is identical; only the draw
  backend changed (QPainter vs Tk canvas).
- Minor differences: native Qt combo/spin arrows differ slightly from
  ttk's; window-manager-drawn frames differ from Tk's. These are
  cosmetic and noted in the PR coverage matrix.

## Files

- `LICENSING.md` — MIT app + LGPL Qt compliance summary (read this).
- `qt-*.png` / `tk-*.png` — before/after screenshots.
- `_capture_tk.py`, `_capture_qt_real.py`, `_capture_qt.py`,
  `_smoke_qt_app.py` — the capture/smoke helpers used to produce the
  evidence above (kept for reproducibility).
