# Web-based UI migration (spike)

A **parallel** web frontend for PipPal. The Tkinter UI
(`src/pippal/ui/`, `reader_app.py`) is left fully intact — this spike
*adds* a second frontend, it does not replace or rewrite anything.

## Stack

- **pywebview** (BSD-3) hosts a local HTML/CSS/JS UI in a native
  WebView2 window (Chromium on Windows).
- A thin Python bridge (`src/pippal/web_ui/bridge.py`) calls the
  **existing** backend — `engine`, `config`, `voices`, `onboarding`,
  `context_menu`, `notices` — with **no backend behaviour change**.
- System tray (**pystray**) and global hotkeys (**keyboard**) stay
  **native**: `app_web.py` uses the exact same `HotkeyManager` and
  `pystray.Icon` code paths as `pippal.app`. Only the windows became
  web.

## Layout

```
webui/                      static frontend (no build step)
  index.html                one shell; ?view= selects the surface
  css/theme.css             palette ported 1:1 from ui/theme.py UI{}
  js/api.js                 transport seam: pywebview bridge OR /bridge HTTP
  js/components.js          card/row builders mirroring make_card()
  js/app.js                 renders each surface, wires it to the bridge
src/pippal/web_ui/
  bridge.py                 JS<->Python facade over the existing backend
  server.py                 static + POST /bridge (desktop host & E2E)
  windows.py                pywebview window lifecycle (chromeless/topmost)
  overlay_state.py          tk-free overlay state the engine drives
  app_web.py                composition (= pippal.app, web windows)
reader_app_web.py           entry shim (parallel to reader_app.py)
e2e/web/                    Playwright (Apache-2.0, test-only)
```

The frontend is intentionally framework-free: the surface is small and
parity-driven, so plain DOM keeps `css/theme.css` a literal port of the
Tk `theme.UI` dict and the `clam`-style widget styling.

## Run the web UI

```powershell
py -3.11 -m venv .venv-web
.\.venv-web\Scripts\python.exe -m pip install -e .
.\.venv-web\Scripts\python.exe -m pip install pywebview
.\.venv-web\Scripts\python.exe reader_app_web.py
```

It behaves like the Tk app: single-instance tray app, left-click tray =
Settings, "First-run check", Recent, Quit; global hotkeys
(Win+Shift+R/Q/P/B) work the same; the right-click "Read with PipPal"
IPC port is still owned.

The Tk app is unchanged: `py -3.11 reader_app.py` still runs the
original.

## Run the tests

See [`e2e/web/README.md`](../../e2e/web/README.md). Summary:

```powershell
.\.venv-web\Scripts\python.exe -m pip install -r e2e\web\requirements.txt
.\.venv-web\Scripts\python.exe -m playwright install chromium
.\.venv-web\Scripts\python.exe -m pytest e2e\web -q
```

Last local run: **11 passed** (Chromium), ~13 s.

## Visual parity

`before-*.png` are the Tk windows; `after-*.png` are the web
equivalents at the same window sizes. The CSS reuses the exact
`theme.py` palette (`#13151c` bg, `#1a1d28` cards, `#6dd9b8` accent,
`#1f2230` inputs), Segoe UI / Segoe UI Semibold, uppercase dim section
headers, rounded cards, a custom chromeless title bar with the PipPal
logo, and the same footer button order
(Reset · Cancel · Apply · Save).

Practical-parity notes / known cosmetic gaps:

- The native title bar is replaced by an in-page chromeless bar (the Tk
  app already paints its own dark caption via DWM — same intent).
- Karaoke colour-bleed: the Tk overlay lerps each word's RGB toward
  white over a 0.5 s window; the web overlay uses the same per-word
  timings (shared `text_utils` weights) but a simpler 3-state
  (past/cur/future) CSS transition. Cadence matches; the gradient bleed
  is approximated.
- Tk messageboxes (confirm/info/error) are replaced by an in-page
  toast; destructive confirms (voice remove) currently act without a
  modal confirm in the web UI — see "Not done" in the PR.
- `before-*.png` were grabbed from a live multi-window desktop so other
  windows bleed into the screen capture; they are reference shots, not
  pixel baselines.
