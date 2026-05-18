# PipPal Tier-2 user-journey E2E (the REAL launched desktop app)

This suite drives the **actually launched PipPal desktop app** — a real
`reader_app_web.py` process whose real pywebview **WebView2** window
appears in the interactive logged-in session — attached to by Playwright
over the Chrome DevTools Protocol and driven with real clicks /
keystrokes on the real window. Each test is a multi-step **user
journey** framed by *why the user activates each control*, asserting a
**real effect** at every step (disk / engine / state / overlay /
history / catalogue) — no mocks of the thing under test,
deadline-polls not fixed sleeps.

## The two-tier model

| | **Tier-1 — `e2e/web`** | **Tier-2 — `e2e/journey` (this)** |
|---|---|---|
| What it drives | the real static UI **served** + **headless Chromium** + the real `/bridge` backend | the **actually launched** desktop app — a real pywebview **WebView2** window |
| Granularity | one focused real-effect test per **control** | multi-step **use-case journeys** ("why the user does this") |
| Lane | **per-PR merge gate** (`ui-web-e2e.yml` → required check *Web UI E2E (served, headless Chromium)*) | **release / journey lane**, run on demand |
| Where it runs | the Session-0 CI runner (no desktop needed) | only the **interactive logged-in user** (a real window must appear) — **NOT** the Session-0 CI runner |
| Status here | unchanged — stays the merge gate | additive — never modifies Tier-1 or any workflow |

Tier-1 stays the authoritative per-PR gate. Tier-2 is the release lane
that proves the *journeys* work on the genuine launched product. The
two are independent; neither touches the other.

## How a journey drives the real window (the technique that works)

1. **Arm CDP on the real window without touching production.**
   `e2e/journey/app_launcher.py` (a test-only shim, never imported by
   the app) sets `webview.settings['REMOTE_DEBUGGING_PORT'] = <free
   port>` (and the `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=
   --remote-debugging-port=<port>` env WebView2 honours) **before**
   `webview.start()`, then calls the **unmodified**
   `pippal.web_ui.app_web.main()`. pywebview's WebView2 backend appends
   `--remote-debugging-port=<port>` to the WebView2
   `AdditionalBrowserArguments` from that setting, so the real desktop
   window exposes a DevTools endpoint.
2. **Launch a fresh real app per journey** (`real_app` fixture in
   `conftest.py`): a fresh isolated `PIPPAL_DATA_DIR` temp profile
   (first-run journeys not pre-seeded; "set up" journeys pre-seeded via
   the real `pippal.onboarding`), a free CDP port, and the
   already-landed opt-in hermetic IPC hooks (`PIPPAL_CMD_SERVER_PORT` /
   `PIPPAL_CMD_SERVER_TOKEN` — production never sets them, so
   `command_server.py` / `open_file.py` behaviour is unchanged). The
   launcher subprocess runs from **this checkout's own `src`**, never a
   globally installed pippal.
3. **Attach Playwright over CDP.** Deadline-poll the WebView2
   `http://127.0.0.1:<port>/json/version` endpoint, then
   `chromium.connect_over_cdp(...)` and attach to the real pywebview
   page.
4. **Prove it is the REAL app, not headless.** Every journey asserts
   the CDP browser build string is **`Edg/<ver>`** (the WebView2
   desktop runtime — a headless Chromium reports `HeadlessChrome`), the
   page URL is the app's `http://127.0.0.1:<bridge>/index.html?view=…`,
   and the live DOM carries the app's `#brand-name` / `data-ready`
   markers.
5. **Follow new real windows.** When the user activates a control that
   opens another surface (e.g. *Open Voice Manager*), the real app
   creates a **second pywebview window** = a new CDP target. Playwright's
   `connect_over_cdp` snapshots targets at connect time, so the fixture
   **re-connects** `connect_over_cdp` (`RealApp._reconnect`) to
   enumerate all current real windows and attaches to the new one. We
   are still driving the genuine pywebview windows — only the
   client-side CDP attachment is refreshed.
6. **Tear down cleanly per journey:** terminate the real app process
   tree, close the Playwright connection, delete the temp profile.

Journeys are independent and order-independent — each is its own fresh
real app instance + fresh profile.

## The journeys

| Journey | Use-case | Real effect asserted at each step |
|---|---|---|
| **J1** `test_j1_first_run_install_voice` | A brand-new user installs a voice so PipPal can read | first launch really shows the setup/onboarding surface · zero voices on disk · clicking *Open Voice Manager* really opens the real Voices window (new CDP target) · clicking *Install* on the smallest catalogue voice (`en_US-kathleen-low`) **really downloads it** — the real `.onnx` (~60 MB) **+** `.onnx.json` land on disk · the running app's live catalogue + `get_installed_voices()` show it installed · reopened Settings offers it and Save records `voice` in `config.json` |
| **J2** `test_j2_read_aloud_speaks` | A set-up user reads text aloud | the running app has the real voice · read triggered through the real UI → the **real Piper engine speaks**: a genuine **RIFF/WAVE** PCM chunk on disk (parsed by stdlib `wave`) · the reader overlay reaches `reading`/`done` and the karaoke cursor (engine `elapsed`) advances · Recent history (live **and** `history.json` on disk) records the text |
| **J3** `test_j3_settings_persist_and_behave` | A user changes a setting and it both persists and behaves | turn *Show panel while reading* OFF + Save → `config.json` on disk shows `show_overlay:false` · reopened Settings still shows it OFF · with it OFF a real read keeps the overlay **idle** (genuine behavioural effect, not just a stored value) · turn it back ON + Save → the running app's live config reads `True` and the `config.json` override is removed (diff-config omits a value back at its default) and a real read **surfaces** the overlay — behaviour flips both ways |
| **J4** `test_j4_onboarding_finish_activates` | A first-run user finishes onboarding | first run with a real engine shows onboarding, no `first_run_activation.json` yet · *Play sample* → the real engine speaks the activation sample · *Finish setup* → the running app reports activation complete **and** `first_run_activation.json` is written complete on disk |
| **J5** `test_j5_view_open_source_notices` | A licence-conscious user checks what is bundled | *View licences…* in Settings really opens the **Notices** window (new CDP target) showing the genuine licences text the backend resolved from disk, matching the backend resolver |

### Genuinely non-journey-able controls (honest notes)

A few primary controls cannot be a meaningful Tier-2 *journey* on this
machine and stay covered by Tier-1's per-control real-effect tests:

- **Native tray menu (`pystray`) clicks and global hotkeys
  (`keyboard`).** These are OS-level (Win32 tray, low-level keyboard
  hook), not DOM controls in the WebView2 window, so CDP cannot drive
  them. Their real effects (open Settings/Voices/onboarding, read/stop/
  pause) are exercised head-less in Tier-1
  (`e2e/web/test_tray_hotkey_integration.py`) against the *same*
  callables `app_web.build_tray_menu` wires, and J1–J5 reach the same
  surfaces through the in-app buttons instead.
- **`open_url` (Website / GitHub / Licence / Privacy links and the
  onboarding "setup instructions" button).** These shell out to the OS
  default browser (`webbrowser.open`); asserting it would drive an
  external browser, not PipPal — out of scope for a PipPal journey. The
  bridge call itself is covered in Tier-1.
- **Windows-integration *Install / Remove right-click entry*.** A real
  per-user **HKCU** registry mutation; doing it inside a journey would
  leave global machine state and races with other checkouts. Tier-1
  covers it hermetically (machine-wide lock + bounded read-after-write
  poll). A journey would add no use-case value over that.
- **Physical speaker output.** Asserting audible sound needs a loopback
  capture device this machine has none of. J2/J4 assert the engine
  *effect* (real RIFF/WAVE on disk, overlay/karaoke/history) instead —
  the audio path is real, only the acoustic capture is not.

## Run it (as the logged-in interactive user)

This must be run by the **logged-in interactive user** (or a
user-session scheduled task). It launches a **real PipPal window** that
appears on your desktop and is driven automatically. It will **NOT**
work from the Session-0 CI runner (no visible desktop).

```powershell
# Real Python on this machine is py -3.11 (the `python` alias is the
# MS Store stub). The runner builds its own isolated venv.
powershell -NoProfile -ExecutionPolicy Bypass -File e2e\journey\run-journey.ps1 -Runs 2
```

Useful switches:

```powershell
# A single journey:
... -File e2e\journey\run-journey.ps1 -K test_j1_first_run_install_voice

# A custom evidence dir:
... -File e2e\journey\run-journey.ps1 -EvidenceDir C:\path\to\evidence
```

Run directly under pytest (the conftest skips unless
`PIPPAL_JOURNEY_LIVE=1`):

```powershell
$env:PYTHONUTF8="1"; $env:PIPPAL_JOURNEY_LIVE="1"
py -3.11 -m pytest e2e\journey -v -rA --log-cli-level=INFO
```

## Evidence

`run-journey.ps1` mirrors `e2e/run-local.ps1`'s status / exit-code
contract and writes, under
`.e2e\evidence\journey-<UTC stamp>\` (or `-EvidenceDir`):

| Artifact | File |
|---|---|
| Human step log (UTF-8) | `pytest-journey.log` (+ `pytest-journey.run<N>.log` per run) |
| JUnit XML | `pytest-journey.junit.xml` |
| JSON summary (gate status/counts/command) | `journey-gate-summary.json` |
| Command/context | `journey-gate-command.txt` |
| Self-contained HTML report | `report.html` |
| **Per-journey real-window proof** | `playwright-artifacts\journey-windows\<test>.png` (a screenshot of the live desktop window), `<test>.app.log` (the launched app's own stdout), `<test>.cdp.json` (the CDP build string — proves `Edg/…`, not headless) |

`journey-gate-summary.json` reviewer rule: a journey pass requires
`status=pass, exit_code=0, tests>0, failures=0, errors=0, skipped=0,
runs>=2`.

## Notes / caveats

- The J1 voice download is a **genuine** HTTP download of the smallest
  catalogue voice (`en_US-kathleen-low`, labelled *small/fast*). On
  this machine it is ~60 MB and completes in a few seconds; the
  assertion deadline-polls up to 180 s. J2/J4 reuse a locally-cached
  real `en_US-ryan-high` voice + the cached real `piper.exe` (copied
  once into this checkout's `piper/`) so they exercise a real synth
  without paying a download every run — J1 alone proves the real
  download path end-to-end.
- These journeys are **excluded from the default `pytest`**
  (`testpaths = tests`) and from Tier-1 `e2e/web`. They never modify
  `command_server.py` / `open_file.py`, `ci.yml` / `e2e-windows.yml` /
  `bench-baseline.yml` / `ui-web-e2e.yml`, or branch protection.
- A second pywebview window = a new CDP target the initial
  `connect_over_cdp` does not auto-surface; the fixture reconnects to
  discover it (see the technique above). This is a Playwright-CDP
  client behaviour, not an app behaviour — the windows driven are the
  genuine app windows.
