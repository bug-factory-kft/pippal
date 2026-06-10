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
| **J6** `test_journey_phase4.py::test_j6_corrupt_config_recovers_to_defaults_and_bak` | A returning user's `config.json` is corrupt; the app must recover | a corrupt `config.json` is pre-written into the fresh profile so the real `load_config` recovery runs at launch · the real app did **not** crash · the real `config.json.bak` is a **byte-for-byte** copy of the user's file · the running app's live `POST /bridge get_config` == the layered defaults · no corrupt config remains (UC-B21) |
| **J7** `test_journey_phase5.py::test_j7_context_menu_install_read_through_it_remove` | A user installs the Windows right-click entry, reads a file **through it**, removes it | the launched app's OWN real `bridge.install_context_menu` does genuine per-user HKCU `reg add` · the real registry keys exist with the real `%1` command · the **exact registered command** (`python -m pippal.open_file <file>`, what Explorer spawns on a real right-click) is run with THIS launched app's hermetic IPC identity → the **real running desktop process's real engine** reads the file (live `engine_state` + Recent history record it) · real `bridge.remove_context_menu` deletes the keys, the real registry is clean. Hermetic: machine-wide registry lock + always-remove teardown; privilege-independent (UC-B11/B13/B12) |
| **J8** `test_journey_phase5.py::test_j8_replay_skip_transport_during_real_read` | A user skips/replays a sentence during a real read | a real **multi-chunk** read (`chunk_total=4`) · `next` / `prev` genuinely move the real `chunk_idx` (0→1→0) on the running process · `replay` is a genuine accepted op + the process stays alive — all driven through the launched app's OWN real `POST /bridge` `overlay_action`, the **exact transport the real desktop overlay window's prev/replay/next buttons use** (UC-D3). *Honest finding:* pause/resume (UC-D5/UC-D10) is **not** a journey leg — the real desktop web overlay has no pause control and the IPC `/pause` route 404s by default; those stay covered by their existing Tier-1 test |

### Genuinely non-journey-able controls (honest notes)

A few primary controls cannot be a meaningful Tier-2 *journey* on this
machine and stay covered by Tier-1's per-control real-effect tests:

- **Native tray menu (`pystray`) clicks and global hotkeys
  (`keyboard`).** These are OS-level (Win32 tray, low-level keyboard
  hook), not DOM controls in the WebView2 window, so CDP cannot drive
  them. Their real effects (open Settings/Voices/onboarding, read/stop/
  pause) are exercised head-less in Tier-1
  (`e2e/web/test_tray_hotkey_integration.py` and, for the repeat-dedup
  / exact-match edge logic, `e2e/web/test_core_phase5.py`) against the
  *same* callables, and J1–J8 reach the same surfaces through the
  in-app buttons / the launched app's own bridge instead.
- **`open_url` (Website / GitHub / Licence / Privacy links and the
  onboarding "setup instructions" button).** These shell out to the OS
  default browser (`webbrowser.open`); asserting it would drive an
  external browser, not PipPal — out of scope for a PipPal journey. The
  bridge call itself is covered in Tier-1.
- **Windows-integration *Install / Remove right-click entry* — now
  Tier-2-journeyed by J7 (Phase-5).** It is a real per-user **HKCU**
  registry mutation, so J7 serialises it under the SAME machine-wide
  registry lock the Tier-1 hermetic shell test uses and ALWAYS removes
  the keys in teardown (even on failure), leaving no machine state and
  not racing other checkouts. J7 adds the genuine value Tier-1 cannot:
  the **real launched desktop process** services the registered command
  end-to-end (Tier-1 only simulates it with a standalone command
  server). Tier-1's hermetic coverage stays the merge-gate row.
- **Reader-transport *pause / resume* (UC-D5/UC-D10).** Honestly **not**
  a Tier-2 journey leg (verified product fact): the real desktop web
  overlay window has **no pause control** (only prev/replay/next/close),
  the web `/bridge` has no `pause` method, and the only genuine pause
  paths are the global hotkey (an OS keystroke boundary CDP cannot
  drive) and the IPC `/pause` *control route* which `command_server`
  gates behind `control_routes_enabled` (default `False`;
  `app_web.main` never enables it) so `POST /pause` genuinely 404s on
  the real launched process. J8 covers the genuinely-reachable UC-D3
  transport; UC-D5/UC-D10 stay covered by their existing Tier-1 test.
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
| **Per-journey real-window proof** | `playwright-artifacts\journey-windows\<test>.png` (a screenshot of the live desktop window), `<test>.app.log` (the launched app's own stdout), `<test>.cdp.json` (the CDP build string — proves `Edg/…`, not headless), `<test>.recording.txt` (exactly what the recorder captured + how) |
| **Per-journey recordings** | `playwright-artifacts\journey-recordings\<test>.trace.zip` (scrubbable Playwright trace), `<test>.mp4` (real screen/window video), and — only on the no-ffmpeg fallback — `<test>.frames\` (numbered PNG frames) + `<test>.frames.png` (dense contact-sheet) |

`journey-gate-summary.json` reviewer rule: a journey pass requires
`status=pass, exit_code=0, tests>0, failures=0, errors=0, skipped=0,
runs>=2`.

## Recordings (and the honest `connect_over_cdp` caveat)

A journey attaches to an **already-running** WebView2 window with
Playwright `chromium.connect_over_cdp`. We did **not** launch that
browser (the real `app_web.main()` / pywebview / WebView2 did), so
Playwright's **native** recording knobs do **not** work here:
`record_video_dir` / the pytest-playwright `--video` flag only record
contexts/pages **Playwright itself launched**. Over a foreign
`connect_over_cdp` attach there is no Playwright-owned context to hang
a video sink on, so a native `.webm` is **never** produced. This is a
real, documented limitation of the CDP-attach mode — not something a
flag fixes. So the suite produces the two recordings that *do* work
over a foreign-CDP attach (`e2e/journey/_recording.py`):

1. **Playwright trace, per journey** — `context.tracing.start(
   screenshots=True, snapshots=True)` is wrapped around the journey
   body and `tracing.stop(path=<test>.trace.zip)` writes a fully
   scrubbable recording: a timeline of every action with a DOM
   snapshot + screenshot at each step. Tracing **does** work over
   `connect_over_cdp` (it instruments the page via CDP; it does not
   need a Playwright-launched browser). Open it with:

   ```powershell
   py -3.11 -m playwright show-trace <test>.trace.zip
   ```

   This is the closest thing to a true "recording" the CDP-attach
   mode allows.

   *Honest sub-caveat:* journeys that follow the user opening a
   **second** real window (J1 → Voices, J5 → Notices) call
   `RealApp.reattach_page`, which **re-`connect_over_cdp`s** (closing
   the old client browser) to enumerate the new window. That closes
   the context tracing was started on, so for those journeys
   `tracing.stop` may not produce a `trace.zip` (the recorder logs a
   non-fatal `trace: stop failed` note in `<test>.recording.txt`) —
   the **screen/window video below still covers the whole journey**,
   and single-window journeys (e.g. J3) still get a full trace. This
   is the reconnect technique interacting with CDP tracing, not an app
   bug; the windows driven are the genuine app windows.

2. **A real screen/window video, per journey** — captured **out of
   band** from Playwright:
   - **Preferred:** `ffmpeg -f gdigrab` records the visible desktop
     (the real PipPal WebView2 window is the foreground app on the
     interactive session), started before the journey body and stopped
     after → one genuine `<test>.mp4`.
   - **Fallback (no ffmpeg on the host):** a background thread grabs
     frames via `page.screenshot` at a fixed cadence for the whole
     journey. If ffmpeg is present they are muxed into `<test>.mp4`;
     otherwise the numbered frames are kept **and** assembled into a
     single dense contact-sheet `<test>.frames.png` so there is still
     a visual time-lapse recording.

   The exact mechanism actually used for each journey is recorded in
   `<test>.recording.txt`.

Every capture path is **best-effort and non-fatal**: a recording
failure is swallowed and can never fail the journey under test.

## Getting the Tier-2 evidence as a downloadable GitHub artifact

Tier-1 uploads its Playwright report as a CI artifact because it runs
on the Session-0 runner. Tier-2 **cannot** run there (it needs a
visible desktop), so the evidence becomes a downloadable artifact via
a two-step, additive flow:

1. **Run the journeys as the logged-in interactive user**:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File e2e\journey\run-journey.ps1 -Runs 2
   ```

   On finish, `run-journey.ps1` **stages** the whole evidence bundle
   (report.html, junit, summary json, step logs, per-journey
   screenshots, `trace.zip`, the `.mp4` / contact-sheet recordings,
   app/cdp proof + a `tier2-evidence-manifest.json`) to a fixed
   per-user host path:

   ```
   %LOCALAPPDATA%\pippal-tier2-evidence\latest\
   ```

   (plus a timestamped sibling), then **best-effort triggers**
   `gh workflow run tier2-evidence-publish.yml`. Pass `-NoPublish` to
   stage only; `-StageRoot <path>` to override the staging root.

2. **The `Tier-2 Evidence Publish` workflow**
   (`.github/workflows/tier2-evidence-publish.yml`,
   **`workflow_dispatch` only**) runs a single job on the same
   self-hosted Windows host. It runs **no journey** (no desktop
   needed) — it only reads `%LOCALAPPDATA%\pippal-tier2-evidence\
   latest\` and `actions/upload-artifact@v4`s it as
   **`tier2-journey-evidence`** (14-day retention) plus a job summary.
   Download that artifact from the **Tier-2 Evidence Publish** workflow
   run in the Actions tab.

It is `workflow_dispatch` **only**, so it is **not** a required check
and cannot interfere with the Tier-1 merge gate. If `gh` is missing
or the trigger fails the bundle is still staged — dispatch *Tier-2
Evidence Publish* manually from the Actions tab.

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
- **Recordings:** native Playwright video does not work over
  `connect_over_cdp` (we did not launch the browser); the suite ships
  a per-journey **trace.zip** (works over CDP) + a real screen/window
  **.mp4** via `ffmpeg gdigrab` (or a screenshot-grab + contact-sheet
  fallback when ffmpeg is absent). See *Recordings* above. The
  staging + `tier2-evidence-publish.yml` (`workflow_dispatch` only)
  flow is purely additive and never gates the Tier-1 merge check.
