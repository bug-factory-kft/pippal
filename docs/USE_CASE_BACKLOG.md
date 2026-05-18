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
| UC-A7 | MISSING_VOICE → Install default voice | First user has no voice; wants the one-click path to a working read | `onboarding-install-voice` → `bridge.install_default_voice` downloads default ~120 MB voice, sets `config["voice"]` (`bridge.py:237`) | **No network / interrupted / disk full** during the ~120 MB download → `install_piper_voice` raises, JS `fail()` toasts, status stuck on "Installing…" | **covered** — happy path Tier-1 `test_onboarding_install_default_voice_real_effect` + Tier-2 J1 (real ~60 MB download). Failure/recovery variant **now Tier-1** `test_error_recovery.py::test_onboarding_install_default_voice_failure_recovers[no_network|interrupted|unwritable_target]`: the real installer/`_streaming_download`/`urllib` runs unchanged, only the *origin* (the pure `voices.voice_url_base` helper) points at a real **closed** socket (genuine `URLError` WinError 10061 = no network), a real server that **RST-closes mid-stream** (genuine `ConnectionResetError` WinError 10054 = interrupted), or a real read-only file pre-occupying the on-disk `.part` target (genuine `PermissionError` Errno 13 = unwritable/disk-full class). Asserts the real `fail()` error toast, status honestly stuck on "Installing…", **no** voice/partial on the real disk, live `config["voice"]` unchanged. Code: `bridge.py:237` |
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
| UC-B7 | Hotkeys — rebind each of 4 fields | User's default combo clashes with another app | `settings-hotkey_speak/queue/pause/stop` → rebind + persist + `bind_hotkeys()` re-registers (`bridge.py:149`) | **Invalid combo** (`parse_combo` → None, `hotkey.py:126`) → `hotkey_failures` returned, toast "some hotkeys could not be bound" (`app.js:263`). **Duplicate combo** (`duplicate_combo_failures`, `hotkey.py:148`) → that action skipped | **covered** — happy rebind Tier-1 `test_settings_hotkey_edit_rebinds_and_persists`, `test_settings_hotkey_each_field_rebinds_and_persists[*]`. Invalid-combo and duplicate-combo failure paths **now Tier-1** `test_error_recovery.py::test_settings_invalid_hotkey_combo_surfaces_failure` and `…::test_settings_duplicate_hotkey_combo_surfaces_failure`: a fresh real bridge/server wired to a **real `HotkeyManager`** + the **verbatim `app_web.bind_hotkeys`** is driven through the real served Settings UI; an unparseable `"ctrl+shift"` hits the real `parse_combo`→None reject (`hotkey.py:126`) and a real duplicate hits the real `duplicate_combo_failures` (`hotkey.py:148`); asserts the real "Saved, but some hotkeys could not be bound." error toast, the real persisted literal, the real `bind_hotkeys` failure entry (reason text) and the real `HotkeyManager._handlers` map (no handler for the invalid combo; exactly one for the duplicated identity). `bridge.py:152` |
| UC-B8 | Reader panel — Show panel / Show text checkboxes | User wants a quieter screen / no karaoke text | `settings-show_overlay`, `settings-show_text_in_overlay` persist; `show_overlay=False` actually suppresses the panel on a real read (`overlay_state.py:69`) | n/a | **covered** Tier-1 `test_settings_checkbox_persists[*]`; Tier-2 `test_j3_settings_persist_and_behave` proves the behavioural effect (overlay stays idle) |
| UC-B9 | Reader panel — Auto-hide / Distance / Karaoke offset spinboxes | User tunes how long the panel lingers / where it sits / lip-sync | `settings-auto_hide_ms`, `settings-overlay_y_offset`, `settings-karaoke_offset_ms` persist | n/a | **covered** Tier-1 `test_settings_edit_persists_to_backend`, `test_settings_spinbox_persists[*]` |
| UC-B10 | Windows integration — status reflects reality | User wants to know if the right-click entry is installed | `settings-ctx-status` reflects `context_menu_status()` all/partial/none (`context_menu.py:33`) | **partial** install state shows "⚠ Partial — re-run Install" | **covered** Tier-1 `test_settings_ctx_status_reflects_backend` (the partial-state copy branch in `app.js:235` is rendered from real status) |
| UC-B11 | Windows integration — Install | User wants "Read with PipPal" on .txt/.md | `settings-ctx-install` → real HKCU keys created (`context_menu.py:59`) | **Registry write fails** → `RuntimeError`, JS `fail()` toast (`context_menu.py:76`) | **covered** — install Tier-1 `test_settings_ctx_install_real_effect`. Registry-write-failure path **now Tier-1** `test_error_recovery.py::test_settings_ctx_install_registry_write_failure`: the real `install_context_menu` runs the real `reg.exe` `subprocess.run` unchanged; only the *target hive* (the pure `context_menu._reg_base_path` helper) is pointed at a **syntactically invalid root hive** `HKXX\…` that `reg.exe` itself rejects with `ERROR: Invalid key name.` (exit 1) for *every* caller — non-admin, admin, and the CI runner's LocalSystem alike — with no ACL involved and no real hive ever written (real non-zero rc → the real `RuntimeError` at `context_menu.py:75-77`, verified at the bridge with `pytest.raises`). Asserts the real `fail()` error toast, the status label does NOT flip to "✓ installed", and the invalid registry root was never readable/written. Privilege- and host-state-independent by construction. `context_menu.py:75-77` |
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
| UC-C6 | Per-row Install | User installs a chosen voice | `vm-action-<id>` → `bridge.install_voice` writes `.onnx`+`.onnx.json`, resets backend (`bridge.py:209`) | **Network/disk failure** → `install_voice` raises, row shows "failed", button re-enabled (`app.js:539`) | **covered** — install success Tier-1 `test_voice_manager_row_install_real_effect` + Tier-2 J1. Per-row install-failure UI path **now Tier-1** `test_error_recovery.py::test_voice_manager_row_install_failure_ui[no_network|interrupted]`: the real `bridge.install_voice`→`install_piper_voice` runs unchanged, only the origin is a real closed / RST-mid-stream socket (genuine `URLError`/`ConnectionResetError`); asserts the real row status flips to "failed" (`vstatus err`), the button is re-enabled, the `fail()` error toast shows, and the real catalogue/disk still report the voice NOT installed (`app.js:539-544`) |
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
| UC-D8 | Full real read-aloud path (synth → WAV → karaoke → history) | The core product: select text, hear it, see karaoke, find it in Recent | Real synth backend → RIFF/WAVE PCM per chunk + `is_speaking` + overlay + Recent records text (`playback.py:59`) | **Synthesis failure** → `ov.show_message("Synthesis failed")` (`playback.py:166`) | **covered (at the real sink — see honest caveat)** — full real path Tier-1 `test_read_aloud_full_real_path_wav_karaoke_history` + Tier-2 J2. The "Synthesis failed" failure branch is **now Tier-1** `test_error_recovery.py::test_read_aloud_synthesis_failed_overlay_message`: a real `TTSBackend` registered via the **real `plugins.register_engine`** API (its `synthesize` genuinely returns False) drives the **unmodified `pippal.playback`** loop to the **real `WebOverlay.show_message("Synthesis failed")` sink** (`playback.py:167`); asserted at the real sink (the real method still executes — only the call is recorded, the unit-suite pattern at `tests/test_engine.py:179` lifted to E2E) + real recovery (engine no longer `is_speaking`, overlay self-recovers to idle in the served DOM, the failure string never enters Recent). **Honest caveat:** in *core* `playback.synthesize_and_play` runs an unconditional trailing `ov.set_state("done")` *immediately after* `_prepare_first_chunk`'s `show_message` (no I/O between them), clearing `overlay.message` within microseconds — so the 120 ms-polled served DOM/`snapshot()` cannot reliably observe the literal string (asserting it there would be a flake/tautology). The message is genuinely emitted at the real sink; its transient overwrite is a real core behaviour (the core/pro asymmetry the gaps section names), not a test weakness. `playback.py:166-168` |
| UC-D9 | One-shot overlay message ("No text selected" / "Queued — N pending") | User gets feedback when a hotkey action has nothing/queued | `show_message` sets `done` + arms `OVERLAY_MESSAGE_MS` self-dismiss (`overlay_state.py:105`); engine emits these (`engine.py:472,498`) | **Message auto-dismiss timing** | **covered (Phase-2)** Tier-1 `test_core_interactions.py::test_overlay_no_text_selected_message_and_self_dismiss` + `…::test_overlay_queued_message_and_self_dismiss`. A real `_RealWavBackend` registered via the real `plugins.register_engine` makes the engine `is_ready()` so the real `_queue_selection_impl` does NOT short-circuit into the no-voice onboarding clip (`engine.py:482`) and genuinely reaches the empty-selection branch (`engine.py:486-489`) and the queue-while-speaking branch (`engine.py:498`). **No-text case (no concurrent read):** asserts the real `WebOverlay.show_message("No text selected")` sink (observe-don't-replace, the `tests/test_engine.py:179` pattern lifted to E2E), the **served-DOM** banner (`body[data-overlay-state=done]` + the `overlay-text` element shows the string — genuinely stable for the full `OVERLAY_MESSAGE_MS`), and the **real `OVERLAY_MESSAGE_MS` self-dismiss** (the real `WebOverlay` timer returns the served DOM to idle on its own, no test action). **Queued case:** asserts the real `engine._queue` append, the real `show_message("Queued — 1 pending")` sink, and that the real `show_message` armed the real `_arm_hide_locked(OVERLAY_MESSAGE_MS)` self-dismiss (observed at the real `_arm_hide_locked` sink) + that the one-shot does not persist. **Honest core caveat (same UC-D8 core/pro asymmetry):** in the queued case the *first* read is still genuinely running, so its own real overlay transition (`start_chunk` → "reading") overwrites the queued banner within microseconds — the served-DOM/snapshot string is genuinely transient there, so it is asserted at the real sinks, not via a flaky DOM poll against the concurrent read; the dedicated served-DOM banner+self-dismiss visibility is proven by the no-text test. `engine.py:472,498`; `overlay_state.py:105` |
| UC-D10 | Pause/resume mid-chunk audio behaviour | User pauses, audio silences, resumes from chunk start | `pause_toggle` purges audio + freezes overlay; resume replays chunk from start (`playback.py:282`) | **Seek while paused** hands the seek back without restarting (`playback.py:316`) | **covered (Phase-2)** Tier-1 `test_core_interactions.py::test_pause_silences_and_resume_replays_then_seek_while_paused`. A real `_RealWavBackend` registered via the real `plugins.register_engine` produces real RIFF/WAVE PCM so the **unmodified `pippal.playback`** loop genuinely runs its real `_wait_for_chunk_end` pause/resume/seek code (the no-piper checkout's onboarding clip bypasses that loop). Drives a real 2-chunk read through the real served UI, then the **real `engine.pause_toggle`**: asserts the real pause-hold is entered (`engine.is_paused` True, overlay `is_paused` True, the karaoke clock genuinely frozen — `elapsed` unchanged across a real interval), resume genuinely continues and the real read completes (real resume re-bases `_chunk_start`, the loop drains to its trailing `done`), then on a fresh real 2-chunk read a real `engine.seek(+1)` *while paused* is handed back as a real SEEKED by the real loop (`playback.py:316-319`): the real `engine._skip_to` is consumed and the real `engine._chunk_idx` moves forward without a spurious restart. `playback.py:305-333` |

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
| UC-E8 | Global hotkey: Queue / Pause / Stop | User queues another selection / pauses / stops via hotkey | `queue`/`pause`/`stop` handlers → `engine.queue_selection_async`/`pause_toggle`/`stop` (`app_web.py:142-145`) | **Queue while idle** behaves like Read; **queue while speaking** appends + "Queued — N pending" (`engine.py:481`) | **covered (Phase-2)** Tier-1 `test_core_interactions.py::test_queue_pause_stop_hotkey_dispatch_drives_real_engine` (mirrors the existing `test_global_hotkey_speak_dispatch_drives_real_engine`). The `queue`/`pause`/`stop` actions are registered on the **real `HotkeyManager`** exactly as `app_web.bind_hotkeys` does and dispatched via the manager's OWN stored handler (the exact callable `HotkeyManager._safe_call` runs when the physical combo fires — only the OS routing the keystroke into the hook is skipped, "testing Windows not PipPal"). A real `_RealWavBackend` (real `plugins.register_engine`, `is_ready()` True) makes the engine take the real synth path so the queue-while-speaking branch is genuinely reached. Asserts: **queue while idle** behaves like Read (real token bump + `is_speaking`, Recent records the text — `engine.py:500-509`); **queue while speaking** really appends to `engine._queue` and the real `WebOverlay.show_message` sink receives exactly `"Queued — 1 pending"` (`engine.py:493,498`); **pause** flips real `engine.is_paused`/overlay `is_paused` and a second dispatch resumes; **stop** runs the real `engine.stop` (token bump, `is_speaking` cleared, queue emptied). The only seam is the OS-boundary selection input (`clipboard_capture.capture_for_action` — sending a real Ctrl+C / reading the system clipboard cannot be driven on a headless Session-0 runner with no foreground selection; the backlog itself names selection capture an OS boundary). That seam is the lifted-to-E2E form of the established unit pattern (`tests/test_engine.py:170`) and is **privilege/host-independent**: it replaces only the OS clipboard read, so the result depends purely on PipPal's branch logic — byte-for-byte identical on the LocalSystem CI runner. `engine.py:481-509` |
| UC-E9 | Single-instance gate | User accidentally launches PipPal twice | `start_command_server` can't bind → "PipPal is already running" MessageBox, exit (`app_web.py:208`) | This is the gate itself | **missing** — the second-instance MessageBox + `SystemExit` gate (`app_web.py:208-221`, `app.py:382`) has no Tier-1/Tier-2 test |

---

## F. Command server / IPC text-read (`command_server.py`)

| id | Surface / control | Use-case | Happy-path journey | Error / edge / recovery variants | Status + evidence |
|---|---|---|---|---|---|
| UC-F1 | Read a file via IPC | The shell entry / a helper asks the running app to read a file | `POST /read-file` → size/extension/binary guards → `engine.read_text_async` (`command_server.py:222`) | **Too large / wrong extension / binary / missing** → 413/415/404 (`command_server.py:231-251`) | **covered (Phase-2)** Tier-1 `test_core_interactions.py::test_command_server_ipc_reject_branches_and_happy_roundtrips` (and the happy round-trip also by `test_shell_integration_registry_and_command`). Stands up the **same real `start_command_server` `CmdHandler`** the desktop app uses (unchanged — `command_server.py` is protected) on this test's hermetic ephemeral-port + token (`cmd_server_identity`), then POSTs genuinely non-conforming real HTTP requests: a missing file → real **404**, a disallowed `.exe` extension → real **415**, a real on-disk file over the real 200 KB cap → real **413**, real NUL-byte content → real **415**; asserts the real HTTP status AND that **none of the four rejects drove the real engine** (real `engine.token` unchanged — the true behavioural contract). The happy `.txt` → real **200** + the real engine genuinely starts reading it. Assert-only, privilege/host-independent (depends only on the real handler's own validation). `command_server.py:222-254` |
| UC-F2 | Read arbitrary text via IPC | A helper hands text directly | `POST /read` → `engine.read_text_async` (`command_server.py:256`) | **Empty / too large** → 400/413 | **covered (Phase-2)** Tier-1 `test_core_interactions.py::test_command_server_ipc_reject_branches_and_happy_roundtrips` (same real `CmdHandler`, unchanged): `/read` empty/whitespace text → real **400**, an over-the-200 KB-cap body (kept under the cheap 2× pre-json guard so the real `len(text.encode()) > MAX_READ_TEXT_BYTES` branch is the one that rejects) → real **413**, neither reject drives the real engine (token unchanged), and the happy text → real **200** + the real engine genuinely starts reading it. Assert-only; `command_server.py` / `open_file.py` unchanged. `command_server.py:256-265` |

> `command_server.py` and `open_file.py` are protected — they are
> **not modified** by this backlog; the gaps above are recorded for the
> test-writing phases only.

---

## Totals tally (Core)

Use-cases enumerated from the real code, excluding the non-existent
pronunciation surface (recorded separately as a not-a-feature note).

| Area | Use-cases | covered | partial | missing |
|---|---|---|---|---|
| A. Onboarding | 14 | 10 | 2 | 2 |
| B. Settings | 21 | 15 | 4 | 2 |
| C. Voice Manager | 9 | 8 | 0 | 1 |
| D. Reader overlay | 10 | 8 | 1 | 1 |
| E. Tray / hotkeys | 9 | 4 | 3 | 2 |
| F. Command server IPC | 2 | 2 | 0 | 0 |
| **Total** | **65** | **47** | **10** | **8** |

> **Phase-1 delta:** the 5 Phase-1 error/recovery rows — UC-A7, UC-C6,
> UC-B7, UC-B11, UC-D8 — flipped **partial → covered** by
> `e2e/web/test_error_recovery.py` (9 Tier-1 test instances). Each
> induces the *real* failure at a true seam (closed / RST-mid-stream
> socket, read-only on-disk target, a syntactically invalid registry
> root hive `reg.exe` rejects for *any* caller incl. the CI runner's
> LocalSystem, real registered failing synth backend) and asserts the
> *real* surfacing + recovery. Covered 37 → 42, partial 16 → 11;
> missing unchanged at 12. UC-D8 is "covered at the real sink" with the
> honest transient-overwrite caveat recorded inline.

> **Phase-2 delta (this PR update):** the 5 Phase-2 untested-core-
> interaction rows — **UC-E8** (missing→covered), **UC-D9**
> (missing→covered), **UC-D10** (missing→covered), **UC-F1**
> (partial→covered), **UC-F2** (missing→covered) — are now Tier-1 in
> `e2e/web/test_core_interactions.py` (5 Tier-1 tests). Each drives the
> real served UI / real engine + overlay / real `HotkeyManager` / real
> `command_server` and asserts a real backend/overlay/engine/IPC state.
> The real condition is induced at a true seam, never by mocking the
> unit under test, and never in a privilege- or host-state-dependent
> way: UC-E8/UC-D9's only seam is the OS-boundary *selection input*
> (`clipboard_capture.capture_for_action` — the established
> `tests/test_engine.py:170` unit pattern lifted to E2E, replacing only
> the OS clipboard read so the result is identical on the LocalSystem
> runner); UC-D10 uses a real `plugins.register_engine` WAV backend so
> the *unmodified* `pippal.playback` loop genuinely runs its real
> pause/resume/seek code; UC-F1/F2 POST genuinely non-conforming real
> HTTP at the real unchanged `CmdHandler` (assert-only). Covered 42 →
> 47, partial 11 → 10 (UC-F1), missing 12 → 8 (UC-E8/D9/D10/F2). UC-D9's
> queued-while-speaking sub-case carries the same honest UC-D8
> transient-overwrite caveat (asserted at the real `show_message` /
> `_arm_hide_locked` sinks, not via a flaky DOM poll against the
> concurrent real read); UC-D9's no-text sub-case proves the served-DOM
> banner + `OVERLAY_MESSAGE_MS` self-dismiss directly (no concurrent
> read).

Split by tier (where covered/partial):

- **Tier-1 (`e2e/web/`)** carries the bulk: all 47 "covered" have a
  Tier-1 test; the 10 remaining "partial" have a Tier-1 happy-path test
  missing the error/edge variant (Phases 3–4).
- **Tier-2 (`e2e/journey/`)** independently covers the 5 core journeys
  J1–J5 (UC-A2/A3, UC-A7, UC-B5/B8, UC-B14, UC-C1/C6, UC-D1/D2/D8) on
  the *real launched desktop app*. No "missing" use-case is covered by
  Tier-2.
- **8 "missing"** have zero coverage in either tier.

---

## Prioritized phase plan (Core)

Each phase is a coherent shippable chunk. "Tier" = which lane the new
test belongs in: **Tier-1** = per-control real-effect `e2e/web/` test;
**Tier-2** = full user-journey on the launched desktop app
(`e2e/journey/`).

### Phase 1 — Error/recovery on the destructive & money paths (highest user risk) — ✅ DONE
*Why first:* these are the failures a real user is most likely to hit
(no Wi-Fi mid-download, registry write refused, bad hotkey) and where a
silent failure is worst. All are pure logic reachable headless.

**Status: implemented and verified green on the merge-required CI
runner** in `e2e/web/test_error_recovery.py` (9 Tier-1 test instances;
full `e2e/web` 68 passed locally — 3 runs, 2 orders — and **68 passed on
the self-hosted LocalSystem runner** via the `Web UI E2E (served,
headless Chromium)` required check on commit `4d0b3b7`
(`actions/runs/26040463378`, SUCCESS), with
`test_settings_ctx_install_registry_write_failure` (UC-B11) PASSED in
that real CI run; `Lint` + `Unit tests` also green; 266 unit + ruff
unaffected). The real failure is induced at a true seam in every case —
never by mocking the unit under test, and never in a way that depends on
caller privilege or host state (UC-B11's registry seam is a
syntactically invalid root hive that `reg.exe` rejects identically for
non-admin / admin / LocalSystem).

- UC-A7 voice download **no-network / interrupted / disk-full** failure
  → `test_onboarding_install_default_voice_failure_recovers[no_network|
  interrupted|unwritable_target]`. Real `urllib`/installer unchanged;
  origin = real closed socket (WinError 10061), real RST-mid-stream
  server (WinError 10054), or a real read-only on-disk `.part` target
  (Errno 13). Asserts the real `fail()` toast + stuck status + clean
  disk + unchanged config. ✅
- UC-C6 per-row install **failure** UI (`app.js:539`) →
  `test_voice_manager_row_install_failure_ui[no_network|interrupted]`. ✅
- UC-B7 **invalid combo** + **duplicate combo** hotkey failure surfacing
  (`hotkey.py:126,148`, `bridge.py:152`) →
  `test_settings_invalid_hotkey_combo_surfaces_failure` +
  `test_settings_duplicate_hotkey_combo_surfaces_failure` (real
  `HotkeyManager` + verbatim `app_web.bind_hotkeys`). ✅
- UC-B11 Windows-integration **registry-write-failure** path →
  `test_settings_ctx_install_registry_write_failure` (real `reg.exe`
  against a **syntactically invalid root hive** `HKXX\…` that `reg.exe`
  itself rejects with `ERROR: Invalid key name.` (exit 1) for *every*
  caller — non-admin, admin, and the CI runner's LocalSystem alike, with
  no ACL involved and no real hive ever written → the real
  `RuntimeError` at `context_menu.py:75-77`). Privilege- and
  host-state-independent by construction. ✅
- UC-D8 core **"Synthesis failed"** overlay message →
  `test_read_aloud_synthesis_failed_overlay_message` (real registered
  failing synth backend → unmodified `pippal.playback` → asserted at
  the real `show_message` sink, with the honest transient-overwrite
  caveat documented at UC-D8 and in the gaps section). ✅

*Actual size:* 7 test functions / 9 parametrized instances. The fault
injection is real seams (closed/short HTTP origin sockets, read-only
disk target, locked `reg` hive, real registered failing synth backend),
not mocks.

### Phase 2 — Untested core interaction journeys (functional gaps in the merge gate) — ✅ DONE
*Why second:* these are everyday actions with **zero** coverage today;
they belong in the per-PR gate.

**Status: implemented and verified green on the merge-required CI
runner** in `e2e/web/test_core_interactions.py` (5 Tier-1 tests; full
`e2e/web` 73 passed locally — 3 runs, 2 orders incl. the new file
collected first — and **73 passed on the self-hosted LocalSystem
runner** via the `Web UI E2E (served, headless Chromium)` required check;
`Lint` + `Unit tests` also green; 266 unit + ruff unaffected). The real
condition is induced at a true seam in every case — never by mocking the
unit under test, and never in a way that depends on caller privilege or
host state.

- UC-E8 queue/pause/stop **hotkey dispatch** + queue-while-speaking vs
  queue-while-idle branch (`engine.py:481-509`) →
  `test_queue_pause_stop_hotkey_dispatch_drives_real_engine` (mirrors
  `test_global_hotkey_speak_dispatch_drives_real_engine`: real
  `HotkeyManager` own stored handler == `_safe_call`'s call; real
  `_RealWavBackend` so the speaking branch is genuinely reached; only
  the OS-boundary selection input is seamed, privilege/host-independent).
  ✅
- UC-D9 one-shot overlay message ("No text selected" / "Queued — N
  pending") + `OVERLAY_MESSAGE_MS` self-dismiss →
  `test_overlay_no_text_selected_message_and_self_dismiss` (served-DOM
  banner + real self-dismiss, no concurrent read) +
  `test_overlay_queued_message_and_self_dismiss` (real `engine._queue`
  append + real `show_message`/`_arm_hide_locked` sinks; honest UC-D8
  transient-overwrite caveat for the concurrent-read sub-case). ✅
- UC-D10 pause→silence→resume-from-start + seek-while-paused behaviour →
  `test_pause_silences_and_resume_replays_then_seek_while_paused` (real
  `plugins.register_engine` WAV backend → the *unmodified*
  `pippal.playback` `_wait_for_chunk_end` pause/resume/seek code; real
  `engine.pause_toggle` / `engine.seek`). ✅
- UC-F1/UC-F2 IPC reject branches (404/415/413, `/read` 400/413, `/read`
  route) → `test_command_server_ipc_reject_branches_and_happy_roundtrips`
  (the same real unchanged `CmdHandler` on the hermetic ephemeral-port +
  token; genuinely non-conforming real HTTP; asserts the real status AND
  that no reject drove the real engine; happy round-trips too;
  assert-only — no `command_server.py` change). ✅

*Actual size:* 5 Tier-1 test functions. The conditions are real seams
(real `HotkeyManager` dispatch, real WAV synth via the plugin API, real
non-conforming HTTP at the unchanged command server), not mocks.

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
   coverage. The remaining 11 partial + 12 missing rows above are the
   use-case-level gaps the per-control tally structurally cannot show.
   (Phase 1 closed the 5 highest-risk ones — e.g. row 1.11 "install
   default voice" now has the real **no-network/interrupted/disk-full**
   variant in `e2e/web/test_error_recovery.py`.)
3. **Core "Synthesis failed" is now covered at the real sink, with a
   real-behaviour caveat (Phase 1).**
   `test_read_aloud_synthesis_failed_overlay_message` drives a real
   registered failing synth backend through the unmodified
   `pippal.playback` loop and asserts the real
   `WebOverlay.show_message("Synthesis failed")` invocation
   (`playback.py:167`). The honest caveat (also recorded inline at
   UC-D8): core's `synthesize_and_play` runs an unconditional trailing
   `set_state("done")` *immediately after* the `show_message`, clearing
   `overlay.message` within microseconds — so the served-DOM/`snapshot()`
   string is genuinely transient and is asserted at the sink (the
   unit-suite pattern lifted to E2E), not via a flaky DOM poll. The
   sibling one-shot messages `engine.py:472,498` ("No text selected" /
   "Queued — N pending") are now **covered in Phase-2** (UC-D9,
   `e2e/web/test_core_interactions.py`): the *no-text* case has **no
   concurrent read** so its served-DOM banner + `OVERLAY_MESSAGE_MS`
   self-dismiss are asserted directly and stably; the *queued-while-
   speaking* case carries the **same transient-overwrite caveat** as
   UC-D8 (the first read's concurrent `start_chunk`→"reading" overwrites
   the banner within microseconds) and is therefore asserted at the real
   `show_message` / `_arm_hide_locked` sinks plus the real `engine._queue`
   append, not via a flaky DOM poll against the concurrent real read.
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
