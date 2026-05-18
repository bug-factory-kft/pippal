# PipPal (Core) — Use-Case / User-Journey Coverage Backlog

Authoritative, exhaustive enumeration of **every user-facing use-case**
in the public MIT core (`src/pippal/`), mapped against current automated
coverage, with a prioritized phased implementation plan.

This is a **doc-only** planning artifact. It changes no code, no
`e2e/**` tests, no workflows, no branch protection. It is the
companion of `docs/migration-web/UI_TEST_CHECKLIST.md` (the per-control
checklist) — that file enumerates *controls*; this file enumerates
*use-cases* (why a user activates a surface) plus their **error / edge /
recovery variants**, which the per-control checklist mostly does not.

## How coverage is graded

Two tiers, exactly as the codebase defines them:

- **Tier-1** = `e2e/web/` per-control real-effect Playwright E2E,
  served + headless, the per-PR merge gate
  (`.github/workflows/ui-web-e2e.yml`). Tests:
  `e2e/web/test_web_ui.py`, `e2e/web/test_web_ui_controls.py`,
  `e2e/web/test_tray_hotkey_integration.py`.
- **Tier-2** = `e2e/journey/` real-launched-pywebview-window
  user-journeys J1–J5 (`e2e/journey/test_journeys.py`,
  runner `e2e/journey/run-journey.ps1`). Release / journey lane,
  not a CI gate.

Status values:

- **covered** — a genuine real-effect test exercises this exact
  use-case (test named, tier given).
- **partial** — the happy-path or only some variants are tested; named
  error/edge/recovery variants are NOT.
- **missing** — no test exercises this use-case at all.

`file:line` evidence is to the **product code** that implements the
use-case (so the gap is verifiable), plus the covering test where one
exists.

> **Scope note.** The task brief listed a `pronunciation.py` /
> pronunciation-rules surface. **It does not exist in this codebase** at
> `feat/web-ui-migration` (`git ls-files` shows no `pronunciation*`, no
> pronunciation UI in `webui/js/app.js`, no `get_pronunciation*` bridge
> method). It is therefore **not a current use-case** and is excluded
> from the tally; it is recorded as a "not-a-feature" line in the Honest
> Gaps section so the omission is explicit, not silent.

---

## A. Onboarding / first-run (`onboarding.py`, `webui/js/app.js` `renderOnboarding`, `bridge.get_readiness`)

`build_activation_readiness` (`src/pippal/onboarding.py:249`) derives one
of three states from engine + `piper.exe` + installed voices; the button
set differs per state.

| id | Surface / control | Use-case (why the user activates it) | Happy-path journey | Error / edge / recovery variants | Status + evidence |
|---|---|---|---|---|---|
| UC-A1 | Onboarding READY state renders | New user wants to confirm PipPal can read on this PC | App auto-opens onboarding (`app_web.py:261`); title/status/voice-check card show "ready" | n/a (render) | **covered** Tier-1 `test_onboarding_renders_and_closes`, `test_onboarding_ready_state_controls`; Tier-2 indirectly via J4 |
| UC-A2 | READY → Play sample | User wants to actually hear PipPal before trusting it | `onboarding-play-sample` → `bridge.play_sample` → real engine read (`bridge.py:288`) | No-voice build routes through onboarding clip not Piper synth — still a real engine effect | **covered** Tier-1 `test_read_aloud_drives_real_engine`; Tier-2 `test_j4_onboarding_finish_activates` (real Piper synth) |
| UC-A3 | READY → Finish setup (gated) | User confirms they heard the sample and finishes | Play sample first → `onboarding-finish` enabled → `mark_activation_complete("sample")` writes `first_run_activation.json` (`onboarding.py:155`) | **Finish before sample played** → status nags, stays gated (`app.js:401`) | **covered** Tier-1 `test_onboarding_finish_gated_until_sample_played`, `test_onboarding_finish_marks_activation_complete`; Tier-2 `test_j4_onboarding_finish_activates` |
| UC-A4 | READY → Skip for now | User trusts it / will set up later | `onboarding-skip` → `close_window` (`app.js:395`) | n/a | **covered** Tier-1 `test_onboarding_ready_skip_closes_window` |
| UC-A5 | READY → Open Settings | User wants to change voice/speed before testing | `onboarding-open-settings` → `open_settings_window` | n/a | **covered** Tier-1 `test_onboarding_ready_open_settings` |
| UC-A6 | READY (already complete) re-entry | Returning user re-opens first-run check; sees "Close"/"Play sample again" | `get_activation_state.is_complete` true → finish button becomes "Close", play becomes "Play sample again" (`app.js:399,413`) | **is_complete branch** of the finish/play handlers | **partial** — render path covered by `test_onboarding_renders_and_closes`; the *already-complete* finish="Close" / play-again copy branch (`app.js:399-422`) is not asserted. Code: `app.js:399` |
| UC-A7 | MISSING_VOICE → Install default voice | First user has no voice; wants the one-click path to a working read | `onboarding-install-voice` → `bridge.install_default_voice` downloads default ~120 MB voice, sets `config["voice"]` (`bridge.py:237`) | **No network / interrupted / disk full** during the ~120 MB download → `install_piper_voice` raises, JS `fail()` toasts, status stuck on "Installing…" | **partial** — happy path **covered** Tier-1 `test_onboarding_install_default_voice_real_effect`; Tier-2 J1 does a real ~60 MB download. **No-network / interrupted / disk-full failure variant: missing.** Code: `bridge.py:237` |
| UC-A8 | MISSING_VOICE → Open Voice Manager | User wants to choose a non-default voice/language | `onboarding-open-vm` → `open_voice_manager_window` | n/a | **covered** Tier-1 `test_onboarding_missing_voice_state_buttons` |
| UC-A9 | MISSING_VOICE → Skip | User defers voice install | `onboarding-skip` → `close_window` | n/a | **covered** Tier-1 `test_onboarding_missing_voice_state_buttons` |
| UC-A10 | MISSING_PIPER → Open setup instructions | Dev/repair user with no `piper.exe` wants the setup docs | `onboarding-open-setup` → `open_url(github#readme)` (`app.js:379`) | n/a (external browser is OS) | **covered** Tier-1 `test_onboarding_missing_piper_open_setup_url` |
| UC-A11 | MISSING_PIPER → Open Settings / Close | Repair user switches engine or dismisses | `onboarding-open-settings` / `onboarding-close` | n/a | **covered** Tier-1 `test_onboarding_missing_piper_state_buttons` |
| UC-A12 | "Try it in any app" sample box | User reads the suggested sample / pastes their own to test | `onboarding-sample` textarea holds `activation_sample_text(hotkey_label)` (`onboarding.py:214`) | n/a | **covered** Tier-1 `test_onboarding_sample_textbox_holds_sample` |
| UC-A13 | Auto-open on first run / missing piper | App decides to nag the user with onboarding at startup | `should_show_activation_panel()` or `_selected_piper_missing` → `windows.open("onboarding")` (`app_web.py:261`) | **All-3-states startup decision**; the *startup auto-open trigger logic itself* is only exercised indirectly | **partial** — onboarding surfaces are covered, but the **startup-decision branch** (`app_web.py:38-40, 261`) that decides *whether* to auto-open is not asserted in either tier (tests open the surface directly). Code: `app_web.py:261` |
| UC-A14 | Selected-text activation completion | User completes activation by actually reading a real selection (not the sample) | First successful `speak` of a real selection while pending → `_mark_activation_selected_text_complete()` writes `completed_with="selected_text"` (`engine.py:390`) | **Capture failure records `last_failure`** (`engine.py:381`), surfaced by `activation_failure_recovery_message` (`onboarding.py:218`) | **missing** — neither the `selected_text` completion path (`engine.py:390`) nor the capture-failure recovery message (`onboarding.py:218`) is exercised by any Tier-1/Tier-2 test (selection capture is an OS boundary on the headless runner, but the activation bookkeeping around it is pure logic and untested). |

---

## B. Settings — 7 cards + footer (`webui/js/app.js` `renderSettings`, `bridge.save_config`)

| id | Surface / control | Use-case | Happy-path journey | Error / edge / recovery variants | Status + evidence |
|---|---|---|---|---|---|
| UC-B1 | Settings opens & renders 7 cards | User wants to configure PipPal | Tray "Settings…" / onboarding → 7 cards render | n/a | **covered** Tier-1 `test_settings_renders_seven_cards` |
| UC-B2 | Voice card — Engine select | User switches TTS engine | `settings-engine` → persists `engine` to disk + live config (`bridge.py:120`) | **Switch to engine with missing piper** — `build_activation_readiness` returns `missing_piper`; engine falls back. Switch path persists but readiness/fallback consequence not asserted | **partial** — persistence **covered** Tier-1 `test_settings_engine_and_voice_selection_persists`; the **engine-switch-with-missing-piper** consequence (fallback + readiness change) is **missing** |
| UC-B3 | Voice card — Voice select | User picks a different installed voice | `settings-voice` non-default → written to `config.json` | **Empty install state** — no voices → combo disabled, CTA reads "Install voices…" | **covered** Tier-1 `test_settings_engine_and_voice_selection_persists`, `test_settings_voice_card_empty_install_state` |
| UC-B4 | Voice card — Manage…/Install CTA | User wants to add/remove voices | `settings-manage-voices` → `open_voice_manager_window` | n/a | **covered** Tier-1 `test_settings_manage_voices_opens_vm` |
| UC-B5 | Speech — Speed slider | User finds default pace too slow/fast | `settings-speed` live value + persists inverse `length_scale` (`app.js:65`) | n/a | **covered** Tier-1 `test_settings_edit_persists_to_backend`; Tier-2 indirectly via J3 |
| UC-B6 | Speech — Variation slider | User wants livelier/flatter intonation | `settings-noise` → `noise_scale` persists | n/a | **covered** Tier-1 `test_settings_variation_slider_reflects_and_persists` |
| UC-B7 | Hotkeys — rebind each of 4 fields | User's default combo clashes with another app | `settings-hotkey_speak/queue/pause/stop` → rebind + persist + `bind_hotkeys()` re-registers (`bridge.py:149`) | **Invalid combo** (`parse_combo` → None, `hotkey.py:126`) → `hotkey_failures` returned, toast "some hotkeys could not be bound" (`app.js:263`). **Duplicate combo** (`duplicate_combo_failures`, `hotkey.py:148`) → that action skipped | **partial** — happy rebind **covered** Tier-1 `test_settings_hotkey_edit_rebinds_and_persists`, `test_settings_hotkey_each_field_rebinds_and_persists[*]`. **Invalid-combo and duplicate-combo failure paths (`hotkey.py:126,148`, `bridge.py:152`) are MISSING** — no test feeds a bad/duplicate combo and asserts the failure surfacing |
| UC-B8 | Reader panel — Show panel / Show text checkboxes | User wants a quieter screen / no karaoke text | `settings-show_overlay`, `settings-show_text_in_overlay` persist; `show_overlay=False` actually suppresses the panel on a real read (`overlay_state.py:69`) | n/a | **covered** Tier-1 `test_settings_checkbox_persists[*]`; Tier-2 `test_j3_settings_persist_and_behave` proves the behavioural effect (overlay stays idle) |
| UC-B9 | Reader panel — Auto-hide / Distance / Karaoke offset spinboxes | User tunes how long the panel lingers / where it sits / lip-sync | `settings-auto_hide_ms`, `settings-overlay_y_offset`, `settings-karaoke_offset_ms` persist | n/a | **covered** Tier-1 `test_settings_edit_persists_to_backend`, `test_settings_spinbox_persists[*]` |
| UC-B10 | Windows integration — status reflects reality | User wants to know if the right-click entry is installed | `settings-ctx-status` reflects `context_menu_status()` all/partial/none (`context_menu.py:33`) | **partial** install state shows "⚠ Partial — re-run Install" | **covered** Tier-1 `test_settings_ctx_status_reflects_backend` (the partial-state copy branch in `app.js:235` is rendered from real status) |
| UC-B11 | Windows integration — Install | User wants "Read with PipPal" on .txt/.md | `settings-ctx-install` → real HKCU keys created (`context_menu.py:59`) | **Registry write fails** → `RuntimeError`, JS `fail()` toast (`context_menu.py:76`) | **partial** — install **covered** Tier-1 `test_settings_ctx_install_real_effect`. **Registry-write-failure path (`context_menu.py:75-77`) is missing** |
| UC-B12 | Windows integration — Remove | User no longer wants the Explorer entry | `settings-ctx-remove` → keys deleted (`context_menu.py:87`) | n/a | **covered** Tier-1 `test_settings_ctx_remove_real_effect` |
| UC-B13 | Windows integration — invoke the registered command | The whole point: right-click a file → PipPal reads it | Registered `python -m pippal.open_file "%1"` POSTs to running IPC server → real `engine.read_text_async` (`open_file.py:13`, `command_server.py:222`) | **Second instance / stale port** — hermetic per-test ephemeral port + token guards it; **wrong token refused** | **covered** Tier-1 `test_shell_integration_registry_and_command` (full registry→command→engine round-trip, hermetic) |
| UC-B14 | Open-source notices — View licences | Licence-conscious user inspects bundled licences | `settings-view-licences` → `open_notices_window`; notices surface shows resolved text (`bridge.py:348`) | **Notices file missing** → fallback "reinstall" copy (`bridge.py:352`) | **partial** — open + real text **covered** Tier-1 `test_settings_view_licences_opens_notices`, `test_notices_window_loads_real_text`; Tier-2 `test_j5_view_open_source_notices`. **Notices-file-missing fallback (`bridge.py:352-357`) is missing** |
| UC-B15 | About — 5 external links | User wants website/source/licence/privacy/terms | `about-website/github/licence/privacy/terms` → `open_url` (`bridge.py:92`) | n/a (external browser OS-bound) | **covered** Tier-1 `test_settings_about_links_open_real_urls` |
| UC-B16 | Footer — Apply (persist, stay open) | User saves but keeps tweaking | `settings-apply` → `save_config(close=False)`, re-renders, "Applied." toast | n/a | **covered** Tier-1 `test_settings_hotkey_edit_rebinds_and_persists` (Apply path) |
| UC-B17 | Footer — Save (persist) | User is done configuring | `settings-save` → `save_config(close=True)`, "Saved." toast | **Parity gap:** web Save does NOT close the window (Tk did) — documented in checklist | **covered** Tier-1 `test_settings_save_persists_with_saved_toast` (asserts the real persisted effect + the honest non-close parity) |
| UC-B18 | Footer — Cancel (no persist) | User changed their mind | `settings-cancel` → `close_window`, nothing written | n/a | **covered** Tier-1 `test_settings_cancel_closes_without_persist` |
| UC-B19 | Footer — Reset to defaults (confirm modal) | User wants a clean slate | `settings-reset` → confirm modal; **Accept** resets fields, **Cancel** leaves them (`app.js:283`) | **Cancel** path = no change | **covered** Tier-1 `test_reset_confirm_modal_gates_the_form` (both accept and cancel) |
| UC-B20 | Title-bar ✕ window close | User dismisses Settings via the chrome button | `window-close` → `close_window` | n/a | **covered** Tier-1 `test_window_close_button_calls_bridge` |
| UC-B21 | Config recovery from a corrupt config.json | User's config file got corrupted; app should not lose all settings | `load_config` renames bad file to `.bak`, returns layered defaults (`config.py:88`) | This is the recovery path itself | **missing** — `config.py:88` corrupt-config `.bak`-rename recovery has no Tier-1/Tier-2 test (it has unit coverage in `tests/`, but no user-journey/E2E test; flagged as a journey gap, not a unit gap) |

---

## C. Voice Manager (`webui/js/app.js` `renderVoiceManager`, `bridge.get_voice_catalogue`)

| id | Surface / control | Use-case | Happy-path journey | Error / edge / recovery variants | Status + evidence |
|---|---|---|---|---|---|
| UC-C1 | Catalogue lists every registered voice | User browses available voices | `get_voice_catalogue` → all 18 core voices with installed flags (`bridge.py:180`) | n/a | **covered** Tier-1 `test_voice_manager_lists_catalogue` |
| UC-C2 | Language filter | User only cares about their language | `vm-language` filters rows (`app.js:497`) | n/a | **covered** Tier-1 `test_voice_manager_language_filter` |
| UC-C3 | Quality filter | User wants high/medium/low quality | `vm-quality` filters | n/a | **covered** Tier-1 `test_voice_manager_quality_filter` |
| UC-C4 | Status filter | User wants to see only installed / not-installed | `vm-status` filters vs real disk state | n/a | **covered** Tier-1 `test_voice_manager_status_filter` |
| UC-C5 | Search (debounced) + empty state | User types a name to find a voice fast | `vm-search` 180 ms debounce; `vm-empty` shown when no match (`app.js:467`) | **No-match empty state** | **covered** Tier-1 `test_voice_manager_search_filter` (both the match and empty-state) |
| UC-C6 | Per-row Install | User installs a chosen voice | `vm-action-<id>` → `bridge.install_voice` writes `.onnx`+`.onnx.json`, resets backend (`bridge.py:209`) | **Network/disk failure** → `install_voice` raises, row shows "failed", button re-enabled (`app.js:539`) | **partial** — install success **covered** Tier-1 `test_voice_manager_row_install_real_effect`; Tier-2 J1 (real ~60 MB download). **Per-row install-failure UI path (`app.js:539-544`) is missing** |
| UC-C7 | Per-row Remove + confirm | User frees disk / removes an unwanted voice | `vm-action-<id>` (installed) → confirm modal → `remove_voice` deletes files (`bridge.py:221`) | **Confirm Cancel** → files untouched | **covered** Tier-1 `test_voice_remove_confirm_modal_gates_deletion` (accept AND cancel) |
| UC-C8 | Close Voice Manager | User is done managing voices | `window-close` in voices surface → `close_window` | n/a | **covered** Tier-1 `test_voice_manager_close_button_calls_bridge` |
| UC-C9 | Voice Manager opened from first-run with install callback | First-run user installs from VM and onboarding refreshes | Tk path wires `on_installed=panel.apply_installed_voice` (`app.py:574`) | The web path has no equivalent first-run→VM→refresh wiring | **missing** — the first-run-launched-VM install-callback flow (`app.py:574-583`, the Tk-only `_open_voice_manager_from_first_run`) has **no web equivalent and no test**; an honest parity gap (web onboarding "Open Voice Manager" just opens VM with no install-completion callback). |

---

## D. Reader overlay (`webui/js/app.js` `renderOverlay`, `overlay_state.py`, `playback.py`)

| id | Surface / control | Use-case | Happy-path journey | Error / edge / recovery variants | Status + evidence |
|---|---|---|---|---|---|
| UC-D1 | Live reading session reflected | User watches progress while PipPal reads | Real read → overlay `reading`/`done`, progress bar advances, chunk counter (`overlay_state.py:190`) | n/a | **covered** Tier-1 `test_overlay_reflects_live_reading_session`; Tier-2 `test_j2_read_aloud_speaks` |
| UC-D2 | Karaoke cursor advances | User follows along word-by-word | `start_chunk` weights words via `text_utils`; cursor advances over time (`overlay_state.py:211`) | n/a | **covered** Tier-1 `test_overlay_karaoke_cursor_advances`; Tier-2 J2 |
| UC-D3 | prev / replay / next during playback | User skips/replays a sentence while reading | `overlay-prev/replay/next` → `engine.seek` (`engine.py:202`) during a real read | n/a | **covered** Tier-1 `test_overlay_transport_buttons_reach_engine_during_playback` |
| UC-D4 | Close button stops reading | User wants to stop now | `overlay-close` → `engine.stop` (token bump, `engine.py:154`) | n/a | **covered** Tier-1 `test_overlay_panel_buttons_call_engine` |
| UC-D5 | Paused chip on pause | User pauses and sees it's paused | Pause during a real read → `overlay-paused` chip shows (`app.js:714`) | n/a | **covered** Tier-1 `test_overlay_paused_chip_shows_on_pause` |
| UC-D6 | Auto-hide after reading | Panel disappears on its own when done | `set_state("done")` arms `threading.Timer(max(OVERLAY_HIDE_MIN_MS, auto_hide_ms))` → panel hides (`overlay_state.py:95`) | **A new read cancels a pending hide** (`_cancel_hide_locked`, `overlay_state.py:151`) | **partial** — auto-hide-then-hidden **covered** Tier-1 `test_overlay_auto_hide_actually_hides`. The **cancel-pending-hide-on-new-read** generation-guard branch (`overlay_state.py:151,176`) is not directly asserted |
| UC-D7 | Drag-to-reposition | User moves the panel out of the way | Right-button drag offsets the panel via transform (`app.js:633`) | n/a | **covered** Tier-1 `test_overlay_drag_repositions_panel` |
| UC-D8 | Full real read-aloud path (synth → WAV → karaoke → history) | The core product: select text, hear it, see karaoke, find it in Recent | Real synth backend → RIFF/WAVE PCM per chunk + `is_speaking` + overlay + Recent records text (`playback.py:59`) | **Synthesis failure** → `ov.show_message("Synthesis failed")` (`playback.py:166`) | **partial** — full real path **covered** Tier-1 `test_read_aloud_full_real_path_wav_karaoke_history`; Tier-2 J2. **The "Synthesis failed" overlay-message failure branch (`playback.py:166-168`) is MISSING in core** (pro covers an analogous path; core does not) |
| UC-D9 | One-shot overlay message ("No text selected" / "Queued — N pending") | User gets feedback when a hotkey action has nothing/queued | `show_message` sets `done` + arms `OVERLAY_MESSAGE_MS` self-dismiss (`overlay_state.py:105`); engine emits these (`engine.py:472,498`) | **Message auto-dismiss timing** | **missing** — no Tier-1/Tier-2 test drives a `show_message` and asserts the user-visible banner + its `OVERLAY_MESSAGE_MS` self-dismiss for the core "No text selected"/"Queued" cases (`engine.py:472,498`; `overlay_state.py:105`). Pro asserts an analogous notice; core does not. |
| UC-D10 | Pause/resume mid-chunk audio behaviour | User pauses, audio silences, resumes from chunk start | `pause_toggle` purges audio + freezes overlay; resume replays chunk from start (`playback.py:282`) | **Seek while paused** hands the seek back without restarting (`playback.py:316`) | **missing** — the pause→silence→resume-replays-from-start and seek-while-paused behaviours (`playback.py:305-333`) have no Tier-1/Tier-2 journey test (paused *chip* is covered, the *audio/seek behaviour* is not) |

---

## E. Tray + global hotkeys (native — `app_web.py build_tray_menu`, `tray.py`, `hotkey.py`)

| id | Surface / control | Use-case | Happy-path journey | Error / edge / recovery variants | Status + evidence |
|---|---|---|---|---|---|
| UC-E1 | Tray Recent submenu + replay an item | User re-reads something they read earlier | Tray "Recent" re-enumerates `engine.get_history()`; clicking an item → `engine.replay_text` (`app_web.py:79`) | **Empty history** → "(empty)" disabled item (`app_web.py:82`) | **partial** — Recent submenu + Clear **covered** Tier-1 `test_tray_recent_submenu_and_clear_real_effect`, `test_history_clear_real_effect`. **Replaying a specific Recent item (`replay_handler`, `app_web.py:76`) and the empty-state item are not individually asserted** |
| UC-E2 | Tray Clear history | User wipes recent list | "Clear history" item → `engine.clear_history` empties memory + `history.json` (`engine.py:247`) | n/a | **covered** Tier-1 `test_tray_recent_submenu_and_clear_real_effect` |
| UC-E3 | Tray Settings… | User opens Settings from the tray | "Settings…" item → `windows.open("settings")` (`app_web.py:99`) | n/a | **covered** Tier-1 `test_tray_settings_item_opens_settings_surface` |
| UC-E4 | Tray First-run check | User re-runs onboarding | "First-run check" → `windows.open("onboarding")` (`app_web.py:97`) | n/a | **covered** Tier-1 `test_tray_first_run_item_opens_onboarding_surface` |
| UC-E5 | Tray Quit | User exits PipPal cleanly | "Quit" → `engine.stop` + hotkey unhook + `icon.stop` + `windows.shutdown` (`app_web.py:63`) | n/a | **covered** Tier-1 `test_tray_quit_item_runs_full_teardown_sequence` |
| UC-E6 | Tray icon idle↔speaking swap | User sees at a glance whether PipPal is talking | `make_tray_icon(speaking)` red badge; `tray_poll` swaps it (`tray.py:23`, `app_web.py:239`) | **Asset missing** → programmatic fallback icon (`tray.py:75`) | **partial** — `make_tray_icon` **covered** by `tests/test_tray.py` unit suite (incl. fallback). The **`tray_poll` live idle↔speaking swap during a real read** (`app_web.py:239-244`) has no E2E/journey test |
| UC-E7 | Global hotkey: Read selection | User presses Win+Shift+R anywhere to read selected text | `HotkeyManager` dispatches the stored `speak` handler → `engine.speak_selection_async` → capture + read (`app_web.py:140`) | **Held-key repeat de-dup** (`hotkey.py:331`); **secure-desktop ghost-modifier guard** (`hotkey.py:96`) | **partial** — handler dispatch → real engine **covered** Tier-1 `test_global_hotkey_speak_dispatch_drives_real_engine`. **The repeat-dedup and physical-modifier (`GetAsyncKeyState`) edge logic (`hotkey.py:293-358`) is not journey-tested** (has unit coverage; OS keystroke delivery is an OS boundary) |
| UC-E8 | Global hotkey: Queue / Pause / Stop | User queues another selection / pauses / stops via hotkey | `queue`/`pause`/`stop` handlers → `engine.queue_selection_async`/`pause_toggle`/`stop` (`app_web.py:142-145`) | **Queue while idle** behaves like Read; **queue while speaking** appends + "Queued — N pending" (`engine.py:481`) | **missing** — only `speak` is hotkey-dispatch-tested; **queue/pause/stop hotkey dispatch and the queue-while-speaking vs queue-while-idle branch (`engine.py:481-509`) have no Tier-1/Tier-2 test** |
| UC-E9 | Single-instance gate | User accidentally launches PipPal twice | `start_command_server` can't bind → "PipPal is already running" MessageBox, exit (`app_web.py:208`) | This is the gate itself | **missing** — the second-instance MessageBox + `SystemExit` gate (`app_web.py:208-221`, `app.py:382`) has no Tier-1/Tier-2 test |

---

## F. Command server / IPC text-read (`command_server.py`)

| id | Surface / control | Use-case | Happy-path journey | Error / edge / recovery variants | Status + evidence |
|---|---|---|---|---|---|
| UC-F1 | Read a file via IPC | The shell entry / a helper asks the running app to read a file | `POST /read-file` → size/extension/binary guards → `engine.read_text_async` (`command_server.py:222`) | **Too large / wrong extension / binary / missing** → 413/415/404 (`command_server.py:231-251`) | **partial** — the happy round-trip is **covered** by `test_shell_integration_registry_and_command` (Tier-1). **The 413/415/404 reject branches are not exercised by any Tier-1/Tier-2 test** (unit-tested only) |
| UC-F2 | Read arbitrary text via IPC | A helper hands text directly | `POST /read` → `engine.read_text_async` (`command_server.py:256`) | **Empty / too large** → 400/413 | **missing** — `/read` route + its reject branches (`command_server.py:256-265`) have no Tier-1/Tier-2 test |

> `command_server.py` and `open_file.py` are protected — they are
> **not modified** by this backlog; the gaps above are recorded for the
> test-writing phases only.

---

## Totals tally (Core)

Use-cases enumerated from the real code, excluding the non-existent
pronunciation surface (recorded separately as a not-a-feature note).

| Area | Use-cases | covered | partial | missing |
|---|---|---|---|---|
| A. Onboarding | 14 | 9 | 3 | 2 |
| B. Settings | 21 | 13 | 6 | 2 |
| C. Voice Manager | 9 | 7 | 1 | 1 |
| D. Reader overlay | 10 | 5 | 2 | 3 |
| E. Tray / hotkeys | 9 | 3 | 3 | 3 |
| F. Command server IPC | 2 | 0 | 1 | 1 |
| **Total** | **65** | **37** | **16** | **12** |

Split by tier (where covered/partial):

- **Tier-1 (`e2e/web/`)** carries the bulk: all 37 "covered" have a
  Tier-1 test; 16 "partial" have a Tier-1 happy-path test missing the
  error/edge variant.
- **Tier-2 (`e2e/journey/`)** independently covers the 5 core journeys
  J1–J5 (UC-A2/A3, UC-A7, UC-B5/B8, UC-B14, UC-C1/C6, UC-D1/D2/D8) on
  the *real launched desktop app*. No "missing" use-case is covered by
  Tier-2.
- **12 "missing"** have zero coverage in either tier.

---

## Prioritized phase plan (Core)

Each phase is a coherent shippable chunk. "Tier" = which lane the new
test belongs in: **Tier-1** = per-control real-effect `e2e/web/` test;
**Tier-2** = full user-journey on the launched desktop app
(`e2e/journey/`).

### Phase 1 — Error/recovery on the destructive & money paths (highest user risk)
*Why first:* these are the failures a real user is most likely to hit
(no Wi-Fi mid-download, registry locked-down, bad hotkey) and where a
silent failure is worst. All are pure logic reachable headless.

- UC-A7 voice download **no-network / interrupted / disk-full** failure
  (Tier-1 — drive `install_default_voice` against an unreachable/short
  origin, assert the JS `fail()` toast + status).
- UC-C6 per-row install **failure** UI (`app.js:539`) (Tier-1).
- UC-B7 **invalid combo** + **duplicate combo** hotkey failure surfacing
  (`hotkey.py:126,148`, `bridge.py:152`) (Tier-1).
- UC-B11 Windows-integration **registry-write-failure** path (Tier-1,
  hermetic — simulate a failing `reg add`).
- UC-D8 core **"Synthesis failed"** overlay message (Tier-1 — backend
  with a synth that fails, assert the message at the `show_message`
  sink, mirroring the pro pattern).

*Est. size:* ~5 focused Tier-1 tests. Medium (needs fault injection
fixtures: short-read HTTP origin, failing `reg`, failing synth backend).

### Phase 2 — Untested core interaction journeys (functional gaps in the merge gate)
*Why second:* these are everyday actions with **zero** coverage today;
they belong in the per-PR gate.

- UC-E8 queue/pause/stop **hotkey dispatch** + queue-while-speaking vs
  queue-while-idle branch (`engine.py:481-509`) (Tier-1, mirror the
  existing `test_global_hotkey_speak_dispatch_drives_real_engine`).
- UC-D9 one-shot overlay message ("No text selected" / "Queued — N
  pending") + `OVERLAY_MESSAGE_MS` self-dismiss (Tier-1).
- UC-D10 pause→silence→resume-from-start + seek-while-paused behaviour
  (Tier-1, drive a real reading session).
- UC-F1/UC-F2 IPC reject branches (413/415/404, `/read` route) (Tier-1
  — POST directly to the per-test command server; **assert only**, no
  `command_server.py` change).

*Est. size:* ~4–5 Tier-1 tests. Medium.

### Phase 3 — Onboarding completeness & startup decision
*Why third:* lower frequency but real first-run UX; mostly logic.

- UC-A14 selected-text activation completion + capture-failure recovery
  message (`engine.py:390`, `onboarding.py:218`) (Tier-1 — seed pending
  activation, drive a real selected-text read).
- UC-A6 already-complete onboarding re-entry copy branch
  (`app.js:399-422`) (Tier-1).
- UC-A13 startup auto-open decision (`app_web.py:38-40,261`) — assert
  `_selected_piper_missing`/`should_show_activation_panel` gate (Tier-1
  unit-style assertion against the real composition helper).
- UC-C9 first-run→VM install-completion parity gap — **decision item**:
  either implement the web equivalent or formally accept the parity gap
  in the checklist (doc/triage, not a test).

*Est. size:* ~3 Tier-1 tests + 1 triage decision. Small–medium.

### Phase 4 — Resilience & single-instance (defensive paths)
*Why fourth:* important robustness but rarely hit; some are
unit-covered, lacking only a journey-level assertion.

- UC-B21 corrupt-`config.json` `.bak`-rename recovery as a journey
  (Tier-2 — launch the real app with a corrupt config, assert it starts
  on defaults and the `.bak` exists).
- UC-E9 single-instance gate (Tier-1 — bind the port first, assert the
  second `start_command_server` returns None and the documented exit
  path; the MessageBox itself is an OS boundary).
- UC-B14 notices-file-missing fallback (`bridge.py:352`) (Tier-1).
- UC-E6 live tray idle↔speaking swap during a real read (Tier-1 — poll
  `make_tray_icon` selection through `tray_poll`'s logic).
- UC-D6 cancel-pending-auto-hide-on-new-read generation guard
  (`overlay_state.py:151,176`) (Tier-1).

*Est. size:* ~4 Tier-1 + 1 Tier-2. Medium.

### Phase 5 — Tier-2 journey breadth (release-lane depth)
*Why last:* Tier-2 is the release lane, not the merge gate; these add
end-to-end confidence on the *real launched app* for flows currently
only Tier-1-tested.

- New Tier-2 journey: **J6 — user rebinds a hotkey and it takes effect**
  (covers UC-B7 happy path on the real window + real `HotkeyManager`).
- New Tier-2 journey: **J7 — user installs the Windows right-click
  entry, reads a file through it, removes it** (UC-B11/B13 end-to-end on
  the launched app, hermetic).
- New Tier-2 journey: **J8 — pause / replay / skip during a real read**
  (UC-D3/D5/D10 on the real overlay window).

*Est. size:* 3 new Tier-2 journeys. Large (each is a full launched-app
journey with real effects), but additive and not a CI gate.

---

## Honest gaps & overclaims found

1. **No `pronunciation` feature exists.** The brief asked for
   pronunciation-rule use-cases (add/edit/delete/import/export + bad
   input). There is **no `pronunciation.py`, no pronunciation UI, no
   bridge method** anywhere at `feat/web-ui-migration`. It is not a
   current use-case — recorded here so the absence is explicit.
2. **`UI_TEST_CHECKLIST.md` claims "72/72, 0 uncovered" — true for
   *controls*, but it does NOT enumerate error/edge/recovery
   use-cases.** That is honest within its own stated scope ("one test
   per *control*"), but a reader could over-read it as full behavioural
   coverage. The 16 partial + 12 missing rows above are the
   use-case-level gaps the per-control tally structurally cannot show
   (e.g. row 1.11 "install default voice" is `[x]` for the happy click
   but the **no-network/interrupted/disk-full** variant is untested).
3. **Core has no "Synthesis failed" / one-shot-message coverage** even
   though the Pro checklist makes a point of asserting the analogous
   `"Synthesis failed"` overlay message (`pro` `test_ollama_read_path_*`).
   Core `playback.py:166` and `engine.py:472,498` emit the same class of
   user-visible message with zero core test — an asymmetry worth closing
   (Phase 1/2).
4. **Tier-2 (journey) breadth is narrow (J1–J5).** The PR/checklist
   presents Tier-2 as the journey lane; it currently covers only 5
   journeys and **does not** touch hotkey rebinding, Windows-integration
   round-trip, pause/seek, or any error path on the real launched app.
   Not overclaimed in the checklist text, but worth stating plainly.
5. **Activation/onboarding bookkeeping around real selections
   (`engine.py:381-403`) is entirely untested in E2E/journey.** The
   selection-capture *seam* is an OS boundary on a headless runner
   (legitimately), but the pure activation-state logic that runs around
   it (`record_activation_failure`, `_mark_activation_selected_text_complete`)
   is not exercised by any Tier-1/Tier-2 test.

No coverage claim in `UI_TEST_CHECKLIST.md` was found to be *false* for
the control it names; the gaps are use-case/behavioural variants the
control-level checklist does not (and does not claim to) cover.
