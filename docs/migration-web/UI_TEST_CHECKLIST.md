# Web UI — per-control test checklist (living tracker)

Authoritative enumeration of **every interactive control / function** of
the migrated PipPal web frontend (`webui/` + `src/pippal/web_ui/`),
cross-checked against the Tk reference (`src/pippal/ui/`, `app.py`,
`tray.py`, `onboarding.py`) so nothing is missed.

**Rule:** one focused, genuine real-effect Playwright test per row. A
real-effect test drives the real served frontend with stable
`data-testid` selectors + Playwright auto-wait (no fixed sleeps, no
mocks/tautologies) and asserts a real backend effect (config.json on
disk, live `TTSEngine` token/state, real voice files, real notices
text). Rows that genuinely cannot be E2E-tested are marked and explained
— not silently skipped.

**Per-test reset:** every test runs against a freshly reset app — a new
isolated `PIPPAL_DATA_DIR` per test, no `config.json` (pure layered
defaults), activation pre-seeded complete, a fresh
engine/overlay/bridge/server per test, and an autouse `assert_fresh_baseline`
guard that fails the test if any state bled in. See the module docstring
of `e2e/web/conftest.py`.

Status: `[x]` covered by a genuine test · `[ ]` not covered · `[~]` not
E2E-testable (reason given).

Test files: `e2e/web/test_web_ui.py` (the original 17, kept, + the
real-WAV path and the hermetic shell-integration round-trip) and
`e2e/web/test_web_ui_controls.py` (the per-control completion suite).

---

## 1. Onboarding / first-run (`renderOnboarding` — activation_panel.py parity)

The surface has three readiness states. `build_activation_readiness`
derives the state from engine + `piper.exe` + installed voices; the
button set differs per state. This checkout has no `piper.exe`, so the
natural served state is `missing_piper`; `missing_voice` and `ready` are
forced by stubbing `piper.exe` / a voice file on the per-test profile so
each state's buttons are driven for real.

| # | Control / function | Playwright test | Status |
|---|---|---|---|
| 1.1 | Title + status render (`onboarding-title`, `onboarding-status`) | `test_onboarding_renders_and_closes` | [x] |
| 1.2 | Local-voice-check card (engine/voice/hotkey rows) | `test_onboarding_ready_state_controls` | [x] |
| 1.3 | "Try it in any app" sample text box (`onboarding-sample`) | `test_onboarding_sample_textbox_holds_sample` | [x] |
| 1.4 | READY: Skip for now (`onboarding-skip`) → close_window | `test_onboarding_ready_skip_closes_window` | [x] |
| 1.5 | READY: Open Settings (`onboarding-open-settings`) → open_settings_window | `test_onboarding_ready_open_settings` | [x] |
| 1.6 | READY: Play sample (`onboarding-play-sample`) → real engine read | `test_read_aloud_drives_real_engine` | [x] |
| 1.7 | READY (incomplete): Finish setup gated until sample played | `test_onboarding_finish_gated_until_sample_played` | [x] |
| 1.8 | READY: Finish setup (`onboarding-finish`) → mark_activation_complete on disk | `test_onboarding_finish_marks_activation_complete` | [x] |
| 1.9 | MISSING_VOICE: Skip for now (`onboarding-skip`) | `test_onboarding_missing_voice_state_buttons` | [x] |
| 1.10 | MISSING_VOICE: Open Voice Manager (`onboarding-open-vm`) | `test_onboarding_missing_voice_state_buttons` | [x] |
| 1.11 | MISSING_VOICE: Install default voice (`onboarding-install-voice`) → real bridge.install_default_voice | `test_onboarding_install_default_voice_real_effect` | [x] |
| 1.12 | MISSING_PIPER: Close (`onboarding-close`) → close_window | `test_onboarding_missing_piper_state_buttons` | [x] |
| 1.13 | MISSING_PIPER: Open Settings (`onboarding-open-settings`) | `test_onboarding_missing_piper_state_buttons` | [x] |
| 1.14 | MISSING_PIPER: Open setup instructions (`onboarding-open-setup`) → open_url | `test_onboarding_missing_piper_open_setup_url` | [x] |

## 2. Settings — the 7 cards + footer (settings_window.py / settings_cards.py parity)

| # | Control / function | Playwright test | Status |
|---|---|---|---|
| 2.0 | All 7 cards render (Voice/Speech/Hotkeys/Reader panel/Windows integration/Open-source notices/About) | `test_settings_renders_seven_cards` | [x] |
| 2.1 | Voice card — Engine combo (`settings-engine`) persists to live config + disk | `test_settings_engine_and_voice_selection_persists` | [x] |
| 2.2 | Voice card — Voice combo (`settings-voice`) persists (non-default → config.json) | `test_settings_engine_and_voice_selection_persists` | [x] |
| 2.3 | Voice card — Manage…/Install CTA (`settings-manage-voices`) → open_voice_manager_window | `test_settings_manage_voices_opens_vm` | [x] |
| 2.4 | Voice card — empty-install CTA label + disabled voice combo | `test_settings_voice_card_empty_install_state` | [x] |
| 2.5 | Speech — Speed slider (`settings-speed`) value reflects + persists (inverse length_scale) | `test_settings_edit_persists_to_backend` | [x] |
| 2.6 | Speech — Variation slider (`settings-noise`) value reflects + persists (noise_scale) | `test_settings_variation_slider_reflects_and_persists` | [x] |
| 2.7 | Hotkeys — Read selection field (`settings-hotkey_speak`) rebind + persist | `test_settings_hotkey_edit_rebinds_and_persists` | [x] |
| 2.8 | Hotkeys — Queue selection field (`settings-hotkey_queue`) rebind + persist | `test_settings_hotkey_each_field_rebinds_and_persists[hotkey_queue]` | [x] |
| 2.9 | Hotkeys — Pause/Resume field (`settings-hotkey_pause`) rebind + persist | `test_settings_hotkey_each_field_rebinds_and_persists[hotkey_pause]` | [x] |
| 2.10 | Hotkeys — Stop field (`settings-hotkey_stop`) rebind + persist | `test_settings_hotkey_each_field_rebinds_and_persists[hotkey_stop]` | [x] |
| 2.11 | Reader panel — Show panel checkbox (`settings-show_overlay`) persists | `test_settings_checkbox_persists[settings-show_overlay]` | [x] |
| 2.12 | Reader panel — Show text checkbox (`settings-show_text_in_overlay`) persists | `test_settings_checkbox_persists[settings-show_text_in_overlay]` | [x] |
| 2.13 | Reader panel — Auto-hide delay spinbox (`settings-auto_hide_ms`) persists | `test_settings_edit_persists_to_backend` | [x] |
| 2.14 | Reader panel — Distance from taskbar spinbox (`settings-overlay_y_offset`) persists | `test_settings_spinbox_persists[overlay_y_offset]` | [x] |
| 2.15 | Reader panel — Karaoke offset spinbox (`settings-karaoke_offset_ms`) persists | `test_settings_spinbox_persists[karaoke_offset_ms]` | [x] |
| 2.16 | Windows integration — status label (`settings-ctx-status`) reflects real context_menu_status | `test_settings_ctx_status_reflects_backend` | [x] |
| 2.17 | Windows integration — Install (`settings-ctx-install`) → real install_context_menu | `test_settings_ctx_install_real_effect` | [x] |
| 2.18 | Windows integration — Remove (`settings-ctx-remove`) → real remove_context_menu | `test_settings_ctx_remove_real_effect` | [x] |
| 2.19 | Open-source notices — View licences… (`settings-view-licences`) → open_notices_window | `test_settings_view_licences_opens_notices` | [x] |
| 2.20 | About — Website link (`about-website`) → open_url | `test_settings_about_links_open_real_urls` | [x] |
| 2.21 | About — GitHub link (`about-github`) → open_url | `test_settings_about_links_open_real_urls` | [x] |
| 2.22 | About — Licence (MIT) link (`about-licence`) → open_url | `test_settings_about_links_open_real_urls` | [x] |
| 2.23 | About — Privacy link (`about-privacy`) → open_url | `test_settings_about_links_open_real_urls` | [x] |
| 2.24 | About — Terms link (`about-terms`) → open_url | `test_settings_about_links_open_real_urls` | [x] |
| 2.25 | Footer — Reset to defaults (`settings-reset`) confirm modal accept AND cancel | `test_reset_confirm_modal_gates_the_form` | [x] |
| 2.26 | Footer — Cancel (`settings-cancel`) → close_window, no persist | `test_settings_cancel_closes_without_persist` | [x] |
| 2.27 | Footer — Apply (`settings-apply`) persists, stays open | `test_settings_hotkey_edit_rebinds_and_persists` | [x] |
| 2.28 | Footer — Save (`settings-save`) persists; "Saved." toast (see parity note) | `test_settings_save_persists_with_saved_toast` | [x] |
| 2.29 | Title bar — window Close (`window-close`) → close_window | `test_window_close_button_calls_bridge` | [x] |
| 2.30 | Windows integration — registered "Read with PipPal" command round-trip: real HKCU keys created with `%1`, the registered `python -m pippal.open_file` reaches the running instance's IPC and drives the **real** engine, uninstall removes the keys (hermetic: per-test ephemeral port + token, wrong-token refused) | `test_shell_integration_registry_and_command` | [x] |

## 3. Voice Manager (`renderVoiceManager` — voice_manager.py parity)

| # | Control / function | Playwright test | Status |
|---|---|---|---|
| 3.1 | Catalogue renders all registered voices | `test_voice_manager_lists_catalogue` | [x] |
| 3.2 | Language filter (`vm-language`) | `test_voice_manager_language_filter` | [x] |
| 3.3 | Quality filter (`vm-quality`) | `test_voice_manager_quality_filter` | [x] |
| 3.4 | Status filter (`vm-status`) | `test_voice_manager_status_filter` | [x] |
| 3.5 | Search (`vm-search`) debounce + match | `test_voice_manager_search_filter` | [x] |
| 3.6 | Search empty state (`vm-empty`) | `test_voice_manager_search_filter` | [x] |
| 3.7 | Per-row Install (`vm-action-<id>`) → real bridge.install_voice on disk | `test_voice_manager_row_install_real_effect` | [x] |
| 3.8 | Per-row Remove (`vm-action-<id>`) confirm accept → real file deletion | `test_voice_remove_confirm_modal_gates_deletion` | [x] |
| 3.9 | Per-row Remove confirm cancel → files untouched | `test_voice_remove_confirm_modal_gates_deletion` | [x] |
| 3.10 | Close (window-close in voices surface) → close_window | `test_voice_manager_close_button_calls_bridge` | [x] |

## 4. Reader overlay (`renderOverlay` — overlay.py / overlay_paint.py parity)

| # | Control / function | Playwright test | Status |
|---|---|---|---|
| 4.1 | prev (`overlay-prev`) reaches engine during playback | `test_overlay_transport_buttons_reach_engine_during_playback` | [x] |
| 4.2 | replay (`overlay-replay`) bumps engine.token during playback | `test_overlay_transport_buttons_reach_engine_during_playback` | [x] |
| 4.3 | next (`overlay-next`) reaches engine during playback | `test_overlay_transport_buttons_reach_engine_during_playback` | [x] |
| 4.4 | close (`overlay-close`) → engine.stop (token bump) | `test_overlay_panel_buttons_call_engine` | [x] |
| 4.5 | progress bar advances against real audio | `test_overlay_reflects_live_reading_session` | [x] |
| 4.6 | chunk counter renders | `test_overlay_reflects_live_reading_session` | [x] |
| 4.7 | karaoke cursor advances over time | `test_overlay_karaoke_cursor_advances` | [x] |
| 4.8 | paused chip (`overlay-paused`) shows on pause during a real read | `test_overlay_paused_chip_shows_on_pause` | [x] |
| 4.9 | auto-hide actually hides the panel | `test_overlay_auto_hide_actually_hides` | [x] |
| 4.10 | drag-to-reposition (right-button drag offsets the panel) | `test_overlay_drag_repositions_panel` | [x] |
| 4.11 | FULL real read-aloud path: real synth backend (registered via the real `plugins.register_engine`) → real per-chunk **RIFF/WAVE PCM on disk** + engine `is_speaking` + reader overlay shows + karaoke cursor advances **across** chunks (chunk counter 1/N→2/N) + Recent history records the text | `test_read_aloud_full_real_path_wav_karaoke_history` | [x] |

## 5. Tray + global hotkeys (native — `app_web.py` / `tray.py`)

The tray (pystray) and global hotkeys (keyboard) are deliberately kept
**native and unchanged** by this migration — the web frontend only
replaces the *windows*. They have no served DOM, but every tray menu
callback and the hotkey-dispatch handler are plain Python callables, so
they get **real headless-safe integration tests** in
`e2e/web/test_tray_hotkey_integration.py` (picked up by the same
`ui-web-e2e.yml` workflow that runs `python -m pytest e2e/web`). The
pystray menu is built by the *exact same* code path the running web app
uses (`pippal.web_ui.app_web.build_tray_menu`, extracted verbatim from
`main`); a `pystray.MenuItem` is callable, so `item(icon)` is precisely
the dispatch a real tray click performs (`self._action(icon, self)`).
The global hotkey is driven through the real `HotkeyManager` (a real
low-level keyboard hook is installed on the runner) and dispatched via
the manager's own stored handler — exactly what
`HotkeyManager._safe_call` invokes when the physical combo fires. The
ONLY thing not covered is the OS rendering the menu's pixels and the OS
physically routing a keystroke into the hook ("testing Windows, not
PipPal") — and even then the underlying callable is `[x]`.

| # | Control / function | Test / coverage | Status |
|---|---|---|---|
| 5.1 | Tray "Recent" submenu + Clear history | `test_tray_recent_submenu_and_clear_real_effect` (drives the *actual* pystray Recent submenu the web app builds: real `pippal.history` round-trip → submenu re-enumerates `engine.get_history()` → invoking the real "Clear history" item empties memory **and** `history.json` on disk). Also `test_history_clear_real_effect` (bridge get/clear). | [x] |
| 5.2 | Tray "Settings…" item | `test_tray_settings_item_opens_settings_surface` — invokes the real pystray "Settings…" item as a click does; asserts it requests the Settings surface (the contract `app_web` wires to `WebWindowManager.open`) **and** that surface renders through the same served bridge (7 cards). | [x] |
| 5.3 | Tray "First-run check" item | `test_tray_first_run_item_opens_onboarding_surface` — invokes the real pystray "First-run check" item; asserts it requests the onboarding surface **and** that surface renders through the served bridge (title/status/skip). | [x] |
| 5.4 | Tray "Quit" item | `test_tray_quit_item_runs_full_teardown_sequence` — invokes the real `quit_action` with the icon-stop / window-manager boundary stubbed; asserts the documented teardown ran for real: `engine.stop()` (token++ + not speaking), the **real** `HotkeyManager` unhooked + handlers cleared, `icon.stop()` + `windows.shutdown()` called — and pytest is NOT killed. | [x] |
| 5.5 | Tray icon idle↔speaking swap (`make_tray_icon`) | `tests/test_tray.py::TestMakeTrayIcon` (existing unit suite: returns 64×64 RGBA, speaking variant differs visibly from idle, per-state cache). The callable is fully `[x]`; only the OS painting that image into the tray (Windows, not PipPal) is uncovered. | [x] |
| 5.6 | Global hotkeys (keyboard lib) | `test_global_hotkey_speak_dispatch_drives_real_engine` — registers the configured "speak" action on the **real** `HotkeyManager` as `app_web.bind_hotkeys` does, then dispatches via the manager's own stored handler (the exact callable `_safe_call` runs); asserts a real engine effect (token bump / speaking). Only the OS delivering the physical keystroke to the hook is uncovered. The rebind path is also covered (`test_settings_hotkey_*`). | [x] |

---

## Tally

| Section | Rows | `[x]` covered | `[~]` not-E2E (reason) | `[ ]` uncovered |
|---|---|---|---|---|
| §1 Onboarding | 14 | 14 | 0 | 0 |
| §2 Settings | 31 | 31 | 0 | 0 |
| §3 Voice Manager | 10 | 10 | 0 | 0 |
| §4 Reader overlay | 11 | 11 | 0 | 0 |
| §5 Tray / hotkeys | 6 | 6 | 0 | 0 |
| **Total** | **72** | **72** | **0** | **0** |

- **Total enumerated interactive rows:** 72
- **Covered by a genuine real-effect test (`[x]`):** 72
- **Not-testable function exemptions (`[~]`):** 0 — every PipPal
  callable, including the native pystray menu callbacks, the tray icon
  factory and the global-hotkey dispatch handler, has a real test.
- **Uncovered (`[ ]`):** 0

> **Zero function exemptions.** §5's tray/hotkey rows are no longer an
> exemption: §5.1–5.4 and 5.6 are real headless-safe pytest integration
> tests in `e2e/web/test_tray_hotkey_integration.py` that build the
> *actual* pystray menu the web app ships (`app_web.build_tray_menu`)
> and invoke each item's callable exactly as a real tray click does, and
> drive the real `HotkeyManager`'s own stored handler exactly as the
> hook thread does; §5.5 is the existing `tests/test_tray.py` unit
> suite. The migration keeps tray/hotkeys native and *unchanged* — these
> tests exercise that unchanged code for real. The ONLY remaining
> non-coverage is the OS's own native-menu pixel rendering and the OS
> physically delivering a keystroke into the hook — i.e. testing
> Windows itself, not PipPal — and even there the underlying PipPal
> callable is `[x]`.

## Honest parity notes (behaviour that differs from the Tk reference)

These are real, observed differences in the migrated web frontend,
surfaced here rather than hidden so the checklist reflects reality:

1. **Footer Save does not itself close the window.** Tk's
   `SettingsWindow._save` persists *and* destroys the dialog. The web
   `btn-save` handler calls `persist(true)` → `save_config(values,
   close=True)` and toasts "Saved.", but neither `app.js` nor
   `bridge.save_config` invokes `close_window`, so the window stays
   open. **Cancel** and the title-bar **✕** *do* close (real
   `close_window`). Row 2.28 therefore asserts the real served effect
   (persisted config + the distinct "Saved." vs Apply's "Applied."
   toast), not a window close. This is a genuine migration gap, not a
   test weakness.
2. **`read_text` does not record Recent history in a no-`piper.exe`
   build.** With no engine ready it routes through the onboarding clip
   (bumping `engine.token`, setting `is_speaking`) and returns before
   `_remember`. Rows 5.1 / 5.6 therefore assert the genuine engine
   contract that DOES occur here — for 5.1 a real `pippal.history`
   round-trip driven through the *actual* pystray Recent submenu (the
   submenu re-enumerates `engine.get_history()`, the real "Clear
   history" item empties memory *and* `history.json` on disk); for 5.6
   the real token bump / `is_speaking` flip the onboarding route
   produces — instead of asserting a Recent entry that would never
   appear here (which would be a false positive).
3. **Window placement / "remember last position"** is not ported
   (documented already in the PR body); cosmetic, no behaviour change.

## Per-test reset mechanism (how a fresh state is guaranteed)

Implemented in `e2e/web/conftest.py` (full rationale in its module
docstring). Per test:

1. `fresh_profile` makes a brand-new empty temp dir, sets
   `PIPPAL_DATA_DIR`, and re-points **every** bound path constant — both
   the module-level `from ..paths import …` copies (`pippal.paths`,
   `config`, `voices`, `history`, `onboarding`, `playback`,
   `web_ui.bridge`, `ui.voice_manager`, `engines.piper`) **and** the
   default-argument slots that captured a path at `def` time
   (`load_config`/`save_config`/`load_history`/`save_history`/
   `activation_state_path`/`build_activation_readiness`/
   `is_default_engine_ready`/`install_piper_voice` via `__defaults__` /
   `__kwdefaults__` rewrite). The previous test's temp dir is removed.
2. The profile is pre-seeded: `first_run_activation.json` written
   *complete* (deterministic onboarding "ready"); **no** `config.json`
   (pure layered defaults — a known baseline).
3. `backend` builds a **fresh** `TTSEngine` + `WebOverlay` +
   `PipPalBridge` + `start_web_ui_server` (new OS port) from that clean
   profile; torn down (`engine.stop()`, `server.shutdown()`) at test end.
4. `assert_fresh_baseline` (autouse) asserts at the START of every test:
   active data root == this temp profile · no `config.json` on disk · no
   installed voices · live config == layered defaults for every mutated
   key · engine idle, `token == 0`, history & queue empty · overlay
   idle · activation pre-seeded complete. Any bleed ⇒ the test ERRORS
   here instead of passing on stale state — the structural defence
   against the false-positive class this suite previously suffered.

Order-independence verified: swapped file order, and a hand-shuffled
cross-file subset (a voice-install test immediately followed by a
"no voices installed" test) — both green because each test gets its own
profile.

## Test inventory & local run record

- Files: `e2e/web/test_web_ui.py` (19 — the 17 original kept + the
  real-WAV `test_read_aloud_full_real_path_wav_karaoke_history` (row
  4.11) + the hermetic `test_shell_integration_registry_and_command`
  (row 2.30)) + `e2e/web/test_web_ui_controls.py` (35, incl.
  parametrized) + `e2e/web/test_tray_hotkey_integration.py` (5 — the §5
  tray / hotkey headless-safe integration tests that close the last
  function exemptions).
- **Hermetic shell-integration harness:** the `cmd_server_identity`
  fixture (`e2e/web/conftest.py`) exports the production-safe, opt-in
  core env hooks `PIPPAL_CMD_SERVER_PORT=0` (OS-assigned ephemeral
  port, written back by `start_command_server`) + a 128-bit per-test
  `PIPPAL_CMD_SERVER_TOKEN` (server requires the `X-PipPal-Token`
  header, `python -m pippal.open_file` sends it). Row 2.30 binds the
  IPC command server through it, so each run targets THIS test's
  instance — a stale/`TIME_WAIT` listener on the fixed 51677 from a
  prior test physically cannot answer (different port AND no token).
  Production never sets the vars, so `command_server.py` /
  `open_file.py` behaviour is byte-for-byte unchanged there.
- **Cross-process registry isolation (second root cause).** The IPC
  port+token make the *network* side per-test hermetic, but
  `install_context_menu`/`uninstall_context_menu` mutate **per-user
  HKCU** keys — global, not per-process. On the shared self-hosted
  Windows runner the merge-required job uses, another PipPal checkout /
  overlapping CI job / local audit loop running *this same test* at the
  same instant could delete the keys this run just wrote (observed
  directly on the dev box: a sibling `actions-runner` worker + a local
  venv running the identical test concurrently). Row 2.30 therefore
  serializes its install→verify→uninstall section with a machine-wide
  named file lock (`_global_registry_lock`) and bounded
  read-after-write polls (`_wait_ctx_status`) for the `reg.exe`
  visibility lag. Pure test-harness isolation — no production code
  changes, and the IPC assertions stay fully per-test regardless.
- Every test narrates its meaningful actions/assertions through the
  `step` fixture (`e2e/web/conftest.py`) on the stdlib `logging`
  module, so a PASSING CI run shows exactly what each test did instead
  of "Passed … no log output captured". The `ui-web-e2e.yml` workflow
  runs the suite with `-v -rA --log-cli-level=INFO` (the flags live in
  the workflow command, **not** the root `pytest.ini`, so the default
  `python -m pytest` (`tests/`) suite is unaffected and `e2e/web` stays
  excluded from it).
- Playwright artifacts are emitted for **every** test (not only on
  failure): `--tracing=on --video=on --screenshot=on` →
  per-test `trace.zip` + `.webm` video + screenshot under
  `playwright-report/artifacts`, plus a self-contained `report.html`;
  all uploaded by the always() `upload-artifact@v4` step. See
  `e2e/web/README.md`.
- **Local headless run: 59 passed** (Chromium, served + headless).
  Stability proven on the final code: the full `e2e/web` suite was run
  **12 consecutive times — 4 in definition order, 3 reversed
  (`pytest-reverse`), 5 with randomized seeds (`pytest-randomly`
  seeds 7/42/1337/90909/2024) — all 12 green (59/59 each, 0
  failures)**, and the shell-integration test was tight-looped **50×
  alone, 50/50 pass, 0 fail, on 50 *distinct* OS-assigned ephemeral
  ports (range 49918–65496), zero on the fixed 51677** — proving no
  run depended on the fixed port and the hermetic mechanism works.
  (`pytest-reverse`/`pytest-randomly` are local-only stability tools,
  not added to `e2e/web/requirements.txt`; CI runs definition order.)
  Honest caveat: an earlier double-loaded run (full suite *concurrent*
  with the tight-loop, plus a sibling `actions-runner` worker on the
  shared self-hosted box) exposed a *second*, registry-only flake
  (`context_menu_status` read-after-write under extreme cross-process
  HKCU contention) — fixed by the `_global_registry_lock` + bounded
  `_wait_ctx_status` polls above; after that fix the 12+50 clean run
  was 100 % green.
- `py -3.11 -m pytest -q` → **266 passed** (unit suite unaffected;
  additive only — the hermetic harness uses the already-landed opt-in
  env hooks and the new test is excluded from the default suite).
  `ruff check src/pippal tests e2e/web` → clean.
- `e2e/web` stays excluded from the default `pytest` (`testpaths =
  tests`): `pytest --collect-only` collects exactly 266, zero from
  `e2e/web`.

---

## Tier-2 — user-journey suite on the REAL launched desktop app (`e2e/journey`)

Everything above is **Tier-1**: per-control real-effect E2E in
**served / headless** mode — the **per-PR merge gate**
(`ui-web-e2e.yml` → required check *Web UI E2E (served, headless
Chromium)*). It stays exactly that and is **not** modified.

**Tier-2** is a *second*, additive lane: genuine **use-case journeys**
on the **actually launched desktop app** — a real `reader_app_web.py`
process whose real pywebview **WebView2** window appears in the
interactive logged-in session, attached to by Playwright over CDP and
driven with real clicks/keystrokes on the real window. It is the
**release / journey lane**, run on demand by the logged-in user via
`e2e/journey/run-journey.ps1` (or a user-session scheduled task) — it
**cannot** run on the Session-0 CI runner (no visible desktop), so it
is *not* a CI gate and does *not* touch branch protection. Tier-1
remains the merge gate; Tier-2 proves the journeys work end-to-end on
the genuine product. See `e2e/journey/README.md` for the
launch/attach technique and evidence layout.

Each journey step asserts a **real effect** on the running process
(disk / engine / overlay / history / catalogue), deadline-polled, no
mocks of the thing under test. Every journey first proves it is
attached to the **real** app (CDP build string `Edg/<ver>` — the
WebView2 runtime, *not* `HeadlessChrome` — plus the app's own
`#brand-name` / `data-ready` DOM markers).

| # | Journey (use-case) | Test | Real effect asserted per step | Status |
|---|---|---|---|---|
| J1 | First-run user installs a voice so PipPal can read | `test_j1_first_run_install_voice` | first launch really shows the setup/onboarding surface · zero voices on disk · *Open Voice Manager* opens the **real** Voices window (new CDP target) · *Install* on the smallest catalogue voice (`en_US-kathleen-low`) **really downloads** the real `.onnx` (~60 MB) **+** `.onnx.json` to disk · running app's live catalogue + `get_installed_voices()` show it installed · reopened Settings offers it, Save records `voice` in `config.json` | [x] |
| J2 | Set-up user reads text aloud | `test_j2_read_aloud_speaks` | running app has the real voice · read via the real UI → **real Piper engine speaks**: genuine **RIFF/WAVE** chunk on disk (stdlib `wave`) · overlay reaches `reading`/`done`, karaoke cursor (`elapsed`) advances · Recent history (live **and** `history.json`) records the text | [x] |
| J3 | User changes a setting; it persists *and* behaves | `test_j3_settings_persist_and_behave` | *Show panel* OFF + Save → `config.json` `show_overlay:false` · reopen still OFF · OFF → a real read keeps overlay **idle** (genuine behavioural effect) · back ON + Save → live config `True`, the `config.json` override removed (diff-config omits a default-valued key) and a real read **surfaces** the overlay — flips both ways | [x] |
| J4 | First-run user finishes onboarding | `test_j4_onboarding_finish_activates` | first run, no `first_run_activation.json` · *Play sample* → real engine speaks the activation sample · *Finish setup* → running app reports activation complete **and** `first_run_activation.json` written complete on disk | [x] |
| J5 | Licence-conscious user checks bundled licences | `test_j5_view_open_source_notices` | *View licences…* opens the **real** Notices window (new CDP target) with the genuine resolved licences text, matching the backend resolver | [x] |

### Tier-2 non-journey-able controls (honest notes)

- **Native tray (`pystray`) clicks + global hotkeys (`keyboard`)** —
  OS-level, not DOM in the WebView2 window, so CDP cannot drive them.
  Already covered head-less in Tier-1
  (`e2e/web/test_tray_hotkey_integration.py`, §5) against the same
  callables; J1–J5 reach the same surfaces via in-app buttons.
- **`open_url`** (About links, onboarding "setup instructions") —
  shells out to the OS browser; driving it would test the browser, not
  PipPal. Bridge call covered in Tier-1.
- **Windows-integration Install/Remove right-click entry** — global
  per-user HKCU mutation; a journey would leave machine state and race
  other checkouts. Tier-1 covers it hermetically.
- **Physical speaker output** — needs a loopback capture device this
  host lacks; J2/J4 assert the engine *effect* (real RIFF/WAVE +
  overlay/karaoke/history), only the acoustic capture is out of scope.

### Tier-2 local run record (this machine)

- Technique proven: `webview.settings['REMOTE_DEBUGGING_PORT']` set by
  the test-only `e2e/journey/app_launcher.py` **before** the unmodified
  `app_web.main()` runs `webview.start()` → the real WebView2 window
  exposes a CDP endpoint; Playwright `connect_over_cdp` attaches and
  drives the real window. Proof it is the real app, not headless: CDP
  `/json/version` → `"Browser": "Edg/148.0.3967.70"` (WebView2 runtime;
  headless would be `HeadlessChrome`), real per-journey window
  screenshots captured under the evidence dir. A second pywebview
  window (e.g. Voices) is a new CDP target the initial connection does
  not auto-surface; the fixture **reconnects** `connect_over_cdp` to
  discover and drive it.
- `e2e\journey\run-journey.ps1 -Runs 2` → **both runs 5/5 passed, 0
  failures, 0 errors, 0 skipped** (full suite J1–J5). Evidence bundle
  (log + JUnit + JSON summary + HTML report + per-journey
  real-window screenshot/app-log/CDP-build + per-journey **recordings**)
  written under `.e2e\evidence\journey-<UTC stamp>\`.

### Tier-2 two-tier evidence model + recordings (how to get the artifact)

Tier-1 uploads its Playwright report as a CI artifact because it runs
on the Session-0 runner. Tier-2 **cannot** run there (it needs a
visible desktop), so its evidence becomes a downloadable artifact via
an additive, two-step flow:

- **Recordings per journey** (`e2e/journey/_recording.py`): a
  scrubbable Playwright **`trace.zip`** (works over
  `connect_over_cdp`; open with `playwright show-trace`) **plus** a
  real screen/window **`.mp4`** via `ffmpeg -f gdigrab` of the visible
  desktop — or, when ffmpeg is absent, a periodic `page.screenshot`
  grab assembled into a `.mp4` (if ffmpeg later resolves) and always a
  dense **`.frames.png`** contact-sheet + numbered frames.
  **Honest caveat:** Playwright's *native* video (`record_video_dir` /
  `--video`) does **not** work over `connect_over_cdp` because the
  browser was launched by pywebview/WebView2, not Playwright — hence
  the trace + out-of-band screen capture. Every capture path is
  best-effort/non-fatal (a recording failure never fails a journey).
- **Stage + publish:** `run-journey.ps1` copies the whole bundle
  (report, junit, summary, step logs, screenshots, `trace.zip`, the
  `.mp4`/contact-sheet, app/cdp proof, a `tier2-evidence-manifest.json`)
  to a fixed per-user host path
  `%LOCALAPPDATA%\pippal-tier2-evidence\latest\` (+ a timestamped
  copy), then best-effort `gh workflow run tier2-evidence-publish.yml`.
- **`Tier-2 Evidence Publish`**
  (`.github/workflows/tier2-evidence-publish.yml`) is
  **`workflow_dispatch` only** — a single job on the same self-hosted
  Windows host that runs **no journey** (no desktop), only reads the
  staged dir and `actions/upload-artifact@v4`s it as
  **`tier2-journey-evidence`**. It is **not** a required check and does
  **not** interfere with the Tier-1 merge gate. Download the artifact
  from that workflow run in the Actions tab. To get it: run
  `e2e\journey\run-journey.ps1` as the logged-in user → it stages +
  triggers publish → download `tier2-journey-evidence`.
- J1 does a **genuine** download of the smallest catalogue voice
  (`en_US-kathleen-low`, ~60 MB on this machine, completes in a few
  seconds; assertion deadline-polls ≤180 s). J2/J4 reuse a
  locally-cached real `en_US-ryan-high` voice + the cached real
  `piper.exe` so they exercise a real synth without a download every
  run — J1 alone proves the real download path end-to-end.
- Additive only: `e2e/journey` is **excluded from the default
  `pytest`** (`testpaths = tests`) and from Tier-1 `e2e/web`;
  `command_server.py` / `open_file.py`, `ci.yml` / `e2e-windows.yml` /
  `bench-baseline.yml` / `ui-web-e2e.yml`, and branch protection are
  untouched. `ruff check src/pippal tests e2e/web e2e/journey` → clean;
  `py -3.11 -m pytest -q` still collects exactly the unit suite (zero
  from `e2e/journey`).
