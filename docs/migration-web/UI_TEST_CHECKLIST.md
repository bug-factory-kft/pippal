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

## 6. Error / recovery on the destructive & money paths (`e2e/web/test_error_recovery.py`)

> **Scope.** Sections 1–5 enumerate one test **per control** (the happy
> click). They deliberately do **not** enumerate the *error / edge /
> recovery variant* of each control — that is the job of
> `docs/USE_CASE_BACKLOG.md` (the use-case backlog). This section tracks
> the **Phase-1** error/recovery use-cases now covered by
> `e2e/web/test_error_recovery.py`, so the new tests are visible here
> too. Every failure is induced at a **true seam** (a real closed /
> RST-mid-stream socket, a real read-only on-disk target, a
> syntactically invalid registry root hive `reg.exe` rejects for *any*
> caller incl. the CI runner's LocalSystem, a real registered failing
> synth backend) — never by mocking the unit under test, and never in a
> privilege- or host-state-dependent way — and every assertion is a real
> observable effect (real error toast / row state in the served DOM,
> real on-disk absence, the real `HotkeyManager` map, the real
> `show_message` sink invocation).

| # | Error/recovery use-case | Playwright test | Status |
|---|---|---|---|
| 6.1 | Default-voice download **no-network** (real connection-refused, WinError 10061) → real `fail()` toast, status stuck "Installing…", clean disk, config unchanged | `test_onboarding_install_default_voice_failure_recovers[no_network]` | [x] |
| 6.2 | Default-voice download **interrupted** (real RST mid-stream, WinError 10054) → same real recovery surface | `test_onboarding_install_default_voice_failure_recovers[interrupted]` | [x] |
| 6.3 | Default-voice download **un-writable target / disk-full class** (real read-only on-disk `.part`, Errno 13) → same real recovery surface | `test_onboarding_install_default_voice_failure_recovers[unwritable_target]` | [x] |
| 6.4 | Voice Manager **per-row Install failure** (`app.js:539`) — no-network → row "failed" (`vstatus err`), button re-enabled, error toast, catalogue still NOT installed | `test_voice_manager_row_install_failure_ui[no_network]` | [x] |
| 6.5 | Voice Manager **per-row Install failure** — interrupted mid-stream → same | `test_voice_manager_row_install_failure_ui[interrupted]` | [x] |
| 6.6 | **Invalid hotkey combo** (`"ctrl+shift"`, real `parse_combo`→None) → real "Saved, but some hotkeys could not be bound." toast; real `bind_hotkeys` failure entry; real `HotkeyManager` has no handler for it | `test_settings_invalid_hotkey_combo_surfaces_failure` | [x] |
| 6.7 | **Duplicate hotkey combo** (real `duplicate_combo_failures`) → real error toast; exactly ONE handler for the duplicated identity in the real `HotkeyManager`; real duplicate-reason failure | `test_settings_duplicate_hotkey_combo_surfaces_failure` | [x] |
| 6.8 | Windows-integration **registry-write failure** (`context_menu.py:75-77`) — real `reg.exe` against a **syntactically invalid root hive** `HKXX\…` that `reg.exe` itself rejects (`ERROR: Invalid key name.`, exit 1) for *every* caller — non-admin, admin, and the CI runner's LocalSystem alike, no ACL, no real hive written → real `RuntimeError`, real `fail()` toast, status does NOT flip to "✓ installed", invalid root never readable/written. Privilege- and host-state-independent by construction. | `test_settings_ctx_install_registry_write_failure` | [x] |
| 6.9 | Core **"Synthesis failed"** (`playback.py:167`) — real registered failing synth backend → unmodified `pippal.playback` → asserted at the **real `show_message` sink** + real recovery (engine not speaking, overlay self-recovers to idle). **Honest caveat:** core overwrites `overlay.message` within µs via a trailing `set_state("done")`, so the served-DOM string is transient and is asserted at the sink, not via a flaky DOM poll (documented at UC-D8 in the backlog). | `test_read_aloud_synthesis_failed_overlay_message` | [x] (at sink, with caveat) |

---

## 7. Untested core interaction journeys (`e2e/web/test_core_interactions.py`)

> **Scope.** Like §6, this section tracks **use-case / behavioural**
> rows (the **Phase-2** rows of `docs/USE_CASE_BACKLOG.md`: UC-E8, UC-D9,
> UC-D10, UC-F1, UC-F2), not new *controls* — so the §1–§5 per-control
> 72/72 tally is unchanged. These are everyday actions that had **zero**
> automated coverage. Every condition is induced at a **true seam**
> (the real `HotkeyManager`'s own stored handler == `_safe_call`'s call;
> a real `plugins.register_engine` WAV backend driving the *unmodified*
> `pippal.playback` loop; genuinely non-conforming real HTTP at the real
> *unchanged* command-server `CmdHandler`) — never by mocking the unit
> under test, and never in a privilege- or host-state-dependent way. The
> only seam (UC-E8/UC-D9) is the OS-boundary *selection input*
> (`clipboard_capture.capture_for_action` — the established
> `tests/test_engine.py:170` unit pattern lifted to E2E; it replaces
> only the OS clipboard read so the result is byte-for-byte identical on
> the LocalSystem CI runner). `command_server.py` / `open_file.py` are
> protected and **unchanged** (assert-only).

| # | Use-case | Playwright test | Status |
|---|---|---|---|
| 7.1 | **UC-E8** queue/pause/stop **global-hotkey dispatch** + queue-while-idle (behaves like Read) vs queue-while-speaking (appends to real `engine._queue` + real `show_message("Queued — 1 pending")`) — real `HotkeyManager` own stored handler; real WAV backend so the speaking branch is genuinely reached; pause flips real `is_paused`, stop runs the real `engine.stop` | `test_queue_pause_stop_hotkey_dispatch_drives_real_engine` | [x] |
| 7.2 | **UC-D9** one-shot **"No text selected"** message — real empty-selection queue branch → real `show_message` sink + the **served-DOM** banner (`body[data-overlay-state=done]` + `overlay-text`) + the real `OVERLAY_MESSAGE_MS` self-dismiss (no concurrent read → stable) | `test_overlay_no_text_selected_message_and_self_dismiss` | [x] |
| 7.3 | **UC-D9** one-shot **"Queued — N pending"** message — real queue-while-speaking → real `engine._queue` append + real `show_message` sink + real `_arm_hide_locked(OVERLAY_MESSAGE_MS)` self-dismiss arming. **Honest caveat (same UC-D8 asymmetry):** the concurrent real read's `start_chunk`→"reading" overwrites the banner within µs, so it is asserted at the real sinks, not via a flaky DOM poll | `test_overlay_queued_message_and_self_dismiss` | [x] (at sink, with caveat) |
| 7.4 | **UC-D10** pause→silence→resume-replays-from-start + seek-while-paused — real `plugins.register_engine` WAV backend → the *unmodified* `pippal.playback` `_wait_for_chunk_end` pause/resume/seek code; real `engine.pause_toggle` (overlay clock genuinely frozen), real `engine.seek(+1)` while paused handed back as SEEKED (`_skip_to` consumed, chunk idx moves, no spurious restart) | `test_pause_silences_and_resume_replays_then_seek_while_paused` | [x] |
| 7.5 | **UC-F1 / UC-F2** command-server IPC reject branches — the real *unchanged* `CmdHandler` on the hermetic ephemeral-port + token: `/read-file` missing→**404**, disallowed ext→**415**, over-cap→**413**, binary→**415**; `/read` empty→**400**, over-cap→**413**; each reject asserted to **not** drive the real engine; both happy round-trips → **200** + the real engine genuinely reads. Assert-only, no `command_server.py` change | `test_command_server_ipc_reject_branches_and_happy_roundtrips` | [x] |

---

## 8. Onboarding completeness & startup decision (`e2e/web/test_core_phase3.py`)

> **Scope.** Like §6/§7, this section tracks **use-case / behavioural**
> rows (the **Phase-3** rows of `docs/USE_CASE_BACKLOG.md`: UC-A14,
> UC-A6, UC-A13), not new *controls* — so the §1–§5 per-control 72/72
> tally is **unchanged**. These are real first-run-UX behaviours that
> were untested in either tier. Every condition is induced at a **true
> seam** (a real `plugins.register_engine` WAV backend so the *unmodified*
> `_speak_selection_impl` genuinely reaches the real activation
> bookkeeping; the conftest's pre-seeded *complete* activation so the
> real `renderOnboarding` genuinely takes its `st.is_complete` branch;
> the **real** `app_web._selected_piper_missing` + real
> `should_show_activation_panel` against real on-disk state — the exact
> `app_web.py:261` gate) — never by mocking the unit under test, and
> never in a privilege- or host-state-dependent way. The only seam
> (UC-A14) is the OS-boundary *selection input*
> (`clipboard_capture.capture_for_action` — the established
> `tests/test_engine.py:170` unit pattern lifted to E2E; it replaces
> only the OS clipboard read so the result is byte-for-byte identical on
> the LocalSystem CI runner). No production code is modified
> (strictly additive — new test file + docs only).

| # | Use-case | Playwright test | Status |
|---|---|---|---|
| 8.1 | **UC-A14** selected-text activation **completion** — real selected-text read → real `_mark_activation_selected_text_complete` → real `mark_activation_complete("selected_text")`; asserts the real on-disk `first_run_activation.json` has `completed_with="selected_text"` + `is_complete` flips (engine took the REAL synth path via a real registered WAV backend, NOT the no-voice clip) | `test_selected_text_activation_completes_on_real_selection_read` | [x] |
| 8.2 | **UC-A14** selected-text **capture-failure recovery** — empty selection → real no-text branch → real `_record_activation_capture_failure`; asserts the real persisted `last_failure == SELECTED_TEXT_CAPTURE_FAILURE` (activation still NOT complete) **and** the real `activation_failure_recovery_message` builds the genuine recovery copy from that real persisted failure + real hotkey label (`onboarding.py:218`) | `test_selected_text_capture_failure_records_recovery_message` | [x] |
| 8.3 | **UC-A6** already-complete onboarding re-entry copy branch (`app.js:399-422`) — real served DOM: Finish=`"Close"` (primary, ungated), Play=`"Play sample again"` (not primary), already-set-up status; "Play sample again" drives a real engine read; "Close" reaches the real `on_close_window` callback and does **NOT** re-write the real `first_run_activation.json` (the `is_complete` branch returns before `mark_activation_complete`). No seam | `test_onboarding_already_complete_reentry_close_and_play_again` | [x] |
| 8.4 | **UC-A13** startup auto-open **decision** (`app_web.py:38-40,261`) — the exact real gate `_selected_piper_missing(config) or should_show_activation_panel()` across all 4 real branches with real on-disk state (real stub `piper.exe` toggled by real file create/delete; real activation file written by the real `mark_activation_complete`); privilege/host-independent | `test_startup_auto_open_decision_real_composition_gate` | [x] |
| 8.5 | **UC-C9** first-run→Voice-Manager install-completion parity gap | — | **[ ] open — Phase-3 triaged & formally accepted** (see Honest parity note 4 below; the web path has no install-completion callback, so a test would be a fake-green or need an out-of-scope feature change) |

---

## 9. Resilience & single-instance (`e2e/web/test_core_phase4.py` + `e2e/journey/test_journey_phase4.py`)

> **Scope.** Like §6–§8, this section tracks **use-case / behavioural**
> rows (the **Phase-4** rows of `docs/USE_CASE_BACKLOG.md`: UC-B14,
> UC-E6, UC-D6 Tier-1; UC-B21 Tier-2 J6; UC-E9 honestly triaged), not
> new *controls* — the §1–§5 per-control 72/72 tally is **unchanged**.
> Every condition is induced at a **true seam** (the pure
> `notices_card._candidate_notice_roots` helper at real empty temp
> dirs; a real `plugins.register_engine` WAV backend so the *unmodified*
> `pippal.playback`/engine genuinely flips real overlay/`is_speaking`
> state; a real corrupt `config.json`'s bytes under a fresh launched-app
> profile; a real OS `SO_EXCLUSIVEADDRUSE` port holder) — never by
> mocking the unit under test, never privilege/host-dependent. No
> production code is modified (strictly additive — new test files +
> docs only).

| # | Use-case | Test | Status |
|---|---|---|---|
| 9.1 | **UC-B14** notices-file-missing fallback (`bridge.py:352-357`) — the real `bridge.get_notices` calls the real `_resolve_notices_path` unchanged; seam ONLY `_candidate_notice_roots` → real empty temp dirs so the real resolver genuinely returns `None` and the real fallback branch returns the genuine "reinstall" copy; asserted in the **real served Notices DOM** (no-tautology precondition first asserts the default resolver finds a REAL file) | `test_core_phase4.py::test_notices_file_missing_fallback_copy_in_served_dom` | [x] (Tier-1) |
| 9.2 | **UC-E6** live tray idle↔speaking swap (`app_web.py:226-244`) — the **verbatim** `app_web.update_tray_icon` body run on a fake icon exactly as the real `tray_poll` loop calls it, driven by a **real** engine read (real WAV backend → real `engine.is_speaking`); asserts the real `tray.make_tray_icon` factory's genuinely pixel-distinct idle vs speaking images swap at rest→reading→stop and the real tooltip | `test_core_phase4.py::test_tray_icon_live_swaps_idle_to_speaking_on_real_read` | [x] (Tier-1) |
| 9.3 | **UC-D6** cancel-pending-auto-hide-on-new-read generation guard (`overlay_state.py:139,151,176`) — real WAV backend → *unmodified* `pippal.playback`; a real long-pending auto-hide timer (60 s `auto_hide_ms`) armed by the real `set_state("done")`, then a real second read's real `_cancel_hide_locked` bumps `_hide_generation` (asserted advanced); the fresh reading is genuinely PRESERVED (real served DOM stays `reading`, panel visible — NOT clobbered to idle by the stale timer) | `test_core_phase4.py::test_new_read_cancels_pending_autohide_generation_guard` | [x] (Tier-1) |
| 9.4 | **UC-B21** corrupt-`config.json` `.bak`-rename recovery — **Tier-2 J6** on the **REAL launched** `app_web.main()` WebView2 desktop app (CDP `Edg/…`, not headless); corrupt `config.json` pre-written into the fresh profile so the real `pippal.config.load_config` recovery (`config.py:84-96`) genuinely runs at launch; asserts on the real running process: no crash + real `config.json.bak` is a byte-for-byte copy of the user's file + the real `POST /bridge get_config` equals layered defaults + no corrupt config remains; real recording artifact (ffmpeg `.mp4` + trace.zip) attached like J1–J5 | `test_journey_phase4.py::test_j6_corrupt_config_recovers_to_defaults_and_bak` | [x] (Tier-2) |
| 9.5 | **UC-E9** single-instance gate (`app_web.py:207-221`) — **honestly triaged with a VERIFIED real product finding, NOT forced green.** The documented bind-conflict gate does **not** trigger for two real instances on Windows (`http.server.HTTPServer.allow_reuse_address=True` + `SO_REUSEADDR`, empirically verified incl. the exact prod fixed-port-51677 path; `command_server.py` protected). The Tier-1 test asserts the real verified product behaviour (two binds BOTH succeed — the honest fact, not "refused") AND the gate's real EXIT logic when the bind genuinely fails (real `SO_EXCLUSIVEADDRUSE` holder → real `start_command_server` `None` → the verbatim guard's real `SystemExit(0)`; only the native `MessageBoxW` OS call skipped) | `test_core_phase4.py::test_single_instance_gate_bind_failure_exits_but_dup_bind_caveat` | **[ ] open — Phase-4 triaged with a verified product finding** (gate exit-logic proven Tier-1; the Windows trigger-condition is a documented latent product gap, see Honest parity note 5 below — not forced green) |

---

## 10. Final-phase partial-row closure & Tier-2 breadth (`e2e/web/test_core_phase5.py` + `e2e/journey/test_journey_phase5.py`)

> **Scope.** Like §6–§9, this section tracks **use-case / behavioural**
> rows (the **Phase-5** rows of `docs/USE_CASE_BACKLOG.md`: UC-B2,
> UC-E1, UC-E7 Tier-1 partial→covered; UC-B11/B13/B12 Tier-2 **J7** and
> UC-D3 Tier-2 **J8** as additive release-lane breadth for
> already-covered rows), not new *controls* — the §1–§5 per-control
> 72/72 tally is **unchanged**. Phase-5 is the **final core phase**:
> after it **0 use-case rows are partial**; the only 2 open rows are
> the honestly-documented product-gap exceptions UC-C9 (§8.5) and
> UC-E9 (§9.5). Every Tier-1 condition is induced at a **true seam**
> (the real served Settings UI + the real `build_activation_readiness`;
> the verbatim `app_web.build_tray_menu` + a real
> `plugins.register_engine` WAV backend so the *unmodified*
> `pippal.playback` runs; the real `HotkeyManager._on_event` fed the
> exact `keyboard`-hook event objects with a modifier-free combo) —
> never by mocking the unit under test, never privilege/host-dependent,
> no fixed-sleep sync, no skip/xfail. Both J7/J8 run on the **real
> launched WebView2 app** (CDP `Edg/…`, not headless) with the real
> per-journey recording artifact, exactly like J1–J6. No production
> code is modified (strictly additive — 2 new test files + docs only).

| # | Use-case | Test | Status |
|---|---|---|---|
| 10.1 | **UC-B2** engine-switch-with-missing-piper **consequence** (`bridge.py:120-136`; `onboarding.py:249-309`) — drives the **real served Settings UI** `settings-engine` select → real `bridge.save_config`; asserts the real persisted `engine` AND that the real `build_activation_readiness` / served `bridge.get_readiness()` consequence genuinely becomes `missing_piper` (`can_play_sample` False — reading paused / engine falls back) with no real `piper.exe`, then flips to `ready` via the genuine non-piper branch when a real `plugins.register_engine` non-piper engine is selected (no-tautology precondition asserts no real `piper.exe` first). No seam; privilege/host-independent | `test_core_phase5.py::test_engine_switch_missing_piper_changes_real_readiness_consequence` | [x] (Tier-1) **partial → covered** |
| 10.2 | **UC-E1** replay a **specific** Recent item + the **empty-state** item (`app_web.py:76-93`; `engine.py:532-550`) — the **verbatim** `app_web.build_tray_menu` pystray menu + a real `plugins.register_engine` WAV backend so the engine `is_ready()` and the real `_replay_text_impl` does NOT short-circuit; invoking the real `replay_handler` closure for a *specific* entry drives the *unmodified* `pippal.playback` and the **exact replayed text** lands in the real `WebOverlay` (asserted via the real served `bridge.engine_state()` `chunk_text` — "BRAVO" not "ALPHA", text-specific not a token bump); the disabled `(empty)` item's real `enabled is False` + genuine no-op asserted on a fresh profile; replay does not re-record history (the genuine `replay_text`≠`read_text` contract) | `test_core_phase5.py::test_tray_recent_replay_specific_item_and_empty_state_real_effect` | [x] (Tier-1) **partial → covered** |
| 10.3 | **UC-E7** global-hotkey **repeat-dedup / physical-modifier exact-match** edge logic (`hotkey.py:293-358`) — feeds the **real** `HotkeyManager._on_event` the *exact* synthetic event objects the `keyboard` hook passes, for a **modifier-free** combo so the real `_physical_modifiers()` `GetAsyncKeyState` read is deterministically empty in an automated context (no-tautology precondition asserts it); asserts the real effects: first `down` → handler fires exactly once + returns `False` (suppress); held-key repeat `down`s do NOT re-fire + stay suppressed; `up` → `True` + clears the real `_held_non_mod`/`_suppressed_non_mod`; an unregistered key passes through + never fires; a fresh press after `up` fires again exactly once (per-press, not a latch). Only the OS delivering the keystroke is skipped; the secure-desktop ghost-modifier *transition* stays an OS boundary (unit-noted, recorded honestly) | `test_core_phase5.py::test_hotkey_repeat_dedup_and_exact_match_real_effect` | [x] (Tier-1) **partial → covered** |
| 10.4 | **UC-B11/B13/B12** — install the Windows right-click entry, read a file **through it**, remove it — **Tier-2 J7** on the **REAL launched** WebView2 desktop app. The launched app's OWN real `bridge.install_context_menu` does the genuine per-user HKCU `reg add`; real registry keys asserted present with the real `%1` command; the **exact registered command** (`python -m pippal.open_file <file>`, what Explorer spawns) is run with THIS launched app's hermetic IPC identity so the **real running desktop process's real engine** reads the file (live `POST /bridge` engine_state + Recent history); real `bridge.remove_context_menu` deletes the keys, registry asserted clean. Hermetic: machine-wide registry lock (same as the Tier-1 shell test) + ALWAYS-remove teardown; privilege-independent. Real recording artifact attached like J1–J6 | `test_journey_phase5.py::test_j7_context_menu_install_read_through_it_remove` | [x] (Tier-2 — **additive breadth for already-covered UC-B11/B13/B12**, no row flip) |
| 10.5 | **UC-D3** replay/prev/next reader transport during a real read — **Tier-2 J8** on the **REAL launched** app's overlay. A real multi-chunk read (`chunk_total=4` verified); `next`/`prev` genuinely move the real `chunk_idx` (0→1→0 verified), `replay` accepted + process alive — driven through the launched app's OWN real `POST /bridge` `overlay_action` (the **exact transport the real desktop overlay window's prev/replay/next buttons use**, `webui/js/app.js:606-619`). **HONEST FINDING (NOT fake-green):** UC-D5/UC-D10 pause/resume is NOT a journey leg — no real desktop web overlay pause control + the IPC `/pause` route 404s by default (`control_routes_enabled=False`, `command_server.py` protected); UC-D5/UC-D10 stay covered by their existing Tier-1 test (§7's `test_pause_silences_and_resume_replays_then_seek_while_paused`). Real recording artifact attached like J1–J6 | `test_journey_phase5.py::test_j8_replay_skip_transport_during_real_read` | [x] (Tier-2 — **additive breadth for already-covered UC-D3**, no row flip) |

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

> **The 72/72 tally is per-*control* (the §1–§5 happy click) and is
> deliberately unchanged by Phases 1–5.** §6 (Phase-1 error/recovery),
> §7 (Phase-2 untested core interactions), §8 (Phase-3 onboarding
> completeness & startup decision), §9 (Phase-4 resilience &
> single-instance) and §10 (Phase-5 final partial-row closure + Tier-2
> breadth) track **use-case / behavioural** rows from
> `docs/USE_CASE_BACKLOG.md`, *not* new controls — they are listed here
> so the new real-effect tests are visible, but they do not change the
> per-control count. §8 adds 4 genuine `[x]` Phase-3 tests; **§8.5
> (UC-C9) is an honest open `[ ]`** — the first-run→Voice-Manager
> install-completion parity gap, **Phase-3 triaged & formally accepted**
> (Honest parity note 4 below), not forced green. §9 adds 4 genuine
> `[x]` Phase-4 tests (UC-B14/E6/D6 Tier-1 + UC-B21 Tier-2 J6); **§9.5
> (UC-E9) is an honest open `[ ]`** — the single-instance gate, **Phase-4
> triaged with a VERIFIED real product finding** (the documented
> bind-conflict gate does not trigger for two real instances on Windows
> due to stdlib `HTTPServer.allow_reuse_address` + `SO_REUSEADDR`;
> Honest parity note 5 below), not forced green. **§10 (Phase-5, the
> final core phase) closes the LAST 3 partial use-case rows**: UC-B2,
> UC-E1, UC-E7 are now genuine `[x]` Tier-1 in
> `e2e/web/test_core_phase5.py` (**partial → covered**), and 2 additive
> Tier-2 journeys (**J7** UC-B11/B13/B12 right-click round-trip; **J8**
> UC-D3 reader transport) prove already-covered rows end-to-end on the
> real launched WebView2 app (no row flip from the journeys). After
> Phase-5 there are **0 partial use-case rows**; the only 2 open rows
> are the honestly-documented product-gap exceptions §8.5 (UC-C9) and
> §9.5 (UC-E9). The authoritative use-case-level covered/partial/missing
> tally lives in `docs/USE_CASE_BACKLOG.md` (**63 covered / 0 partial /
> 2 missing of 65 after Phase-5** — full phased core coverage achieved
> except the 2 honestly-documented product-gap exceptions).

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
4. **First-run → Voice-Manager install-completion callback is not
   ported (UC-C9 — Phase-3 triaged & formally accepted).** Tk's
   `_open_voice_manager_from_first_run` wires
   `on_installed=panel.apply_installed_voice` (`app.py:574-583`) so a
   voice installed *from the first-run-launched VM* refreshes the
   onboarding panel. The web onboarding "Open Voice Manager" button
   (`app.js:385-386` → the real `open_voice_manager_window` host
   callback) opens the VM as an **independent window with no
   install-completion callback** back into the onboarding surface —
   there is no `apply_installed_voice` analogue in the web
   bridge/`app_web` path. This is a **genuine migration parity gap, not
   a test weakness.** Phase-3 **formally accepts** it rather than
   forcing a green: a test here would either assert behaviour that does
   not exist (a tautology / fake-green) or require *implementing* the
   missing web wiring (a feature change, out of strictly-additive
   Phase-3 scope). Recorded as the open `[ ]` row §8.5 and as UC-C9 in
   `docs/USE_CASE_BACKLOG.md`. Recommended future work: add an
   `on_installed` callback to the web VM open path (a real feature
   change for a later phase), then add the Tier-1 test.
5. **The single-instance gate does not actually trigger for two real
   instances on Windows (UC-E9 — Phase-4 triaged with a VERIFIED real
   product finding).** Both `app_web.main` (`app_web.py:207-221`) and
   `pippal.app` (`app.py:422-431`) treat `start_command_server`
   returning `None` (port could not be bound) as "another instance is
   running" → show the "PipPal is already running" `MessageBoxW` and
   `raise SystemExit(0)`. But `http.server.HTTPServer` sets
   `allow_reuse_address = True`, and on Windows `SO_REUSEADDR` lets two
   sockets bind the **same** `127.0.0.1:port` concurrently —
   empirically verified on this runner on **both** the hermetic
   ephemeral path **and** the exact production fixed-port-51677 path: a
   real second `start_command_server` while the first is serving *also
   binds and returns a live server*, so the `cmd_server is None` guard
   never fires for two genuine instances. This is a **real latent
   product weakness in the gate's trigger condition, not a test
   weakness**, and `command_server.py` is protected (not changed here).
   Phase-4 **does not fake-green it**: §9.5's Tier-1 test asserts the
   real verified product behaviour (two binds both succeed — the honest
   fact, asserted, not "refused") **and** the gate's real *exit* logic
   when the bind genuinely fails (a real OS `SO_EXCLUSIVEADDRUSE` port
   holder → real `start_command_server` `None` → the verbatim
   `app_web.main` guard's real `SystemExit(0)`; only the native
   `MessageBoxW` OS call is skipped). Recorded as the open `[ ]` row
   §9.5 and as UC-E9 in `docs/USE_CASE_BACKLOG.md` (Honest gaps note 6).
   Recommended future work (a real product fix, out of this
   strictly-additive scope): bind the IPC listener with
   `SO_EXCLUSIVEADDRUSE` (or probe an existing instance's `/ping`
   before binding) so the gate is genuine on Windows, then flip UC-E9
   to covered with a real two-instance test.

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
  function exemptions) + `e2e/web/test_error_recovery.py` (9 — the §6
  Phase-1 error/recovery use-cases: 7 test functions, 9 parametrized
  instances; real failures at true seams) + `e2e/web/test_core_
  interactions.py` (5 — the §7 Phase-2 untested-core-interaction
  use-cases UC-E8/D9/D10/F1/F2; real conditions at true seams) +
  `e2e/web/test_core_phase3.py` (4 — the §8 Phase-3 onboarding-
  completeness / startup-decision use-cases UC-A14/A6/A13; real
  conditions at true seams; UC-C9 honestly triaged in docs, no test) +
  `e2e/web/test_core_phase4.py` (4 — the §9 Phase-4 resilience
  use-cases: UC-B14 notices-missing fallback, UC-E6 live tray swap,
  UC-D6 auto-hide generation guard, + the UC-E9 finding/exit-logic
  test; real conditions at true seams; UC-E9's Windows
  trigger-condition honestly triaged in docs as a verified product
  finding) + `e2e/web/test_core_phase5.py` (3 — the §10 Phase-5 final
  partial-row closures UC-B2/UC-E1/UC-E7, **partial → covered**; real
  conditions at true seams: the real served Settings UI + real
  `build_activation_readiness`; the verbatim `app_web.build_tray_menu`
  + a real `plugins.register_engine` WAV backend; the real
  `HotkeyManager._on_event` fed the exact hook event objects). The
  Phase-4 Tier-2 journey **J6** (UC-B21, corrupt-config recovery) is in
  `e2e/journey/test_journey_phase4.py`; the Phase-5 Tier-2 journeys
  **J7** (UC-B11/B13/B12 right-click round-trip) + **J8** (UC-D3 reader
  transport) are in `e2e/journey/test_journey_phase5.py` (the Tier-2
  lane, not part of the `e2e/web` count). **Full `e2e/web`: 84 tests**
  (81 + 3 Phase-5). **Local run record (this machine):** full `e2e/web`
  **84 passed** twice — definition order and the Phase-5 file collected
  first (isolation/order-independence) — both green & stable;
  `e2e/journey/test_journey_phase5.py` **J7+J8 passed twice**
  (`run-journey.ps1 -Runs 2`, gate status=pass, exit 0) on the **real
  launched WebView2 app** (CDP build `Edg/148.0.3967.70` — a real
  desktop window, not headless `HeadlessChrome`), with a real
  per-journey `.mp4` (ffmpeg gdigrab) + `trace.zip` + window screenshot
  recording attached each run; full unit suite **266/266** (one
  pre-existing transient `tests/test_command_server.py` socket-abort
  flake — passes 42/42 in isolation, unrelated to the additive Phase-5
  files); `ruff check src/pippal tests e2e/web e2e/journey` clean;
  `pytest --collect-only` exactly 266 (zero from `e2e/web` /
  `e2e/journey` — fully additive; `git status` shows only the 2 new
  test files).
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
- **Phase-1 update (this PR update) — local headless run: 68 passed**
  (Chromium, served + headless): the 59 prior + the 9 new
  `test_error_recovery.py` instances. The full `e2e/web` suite was run
  **3 consecutive times — twice in definition order and once with the
  new error/recovery file collected first (isolation check) — all 3
  green (68/68 each, 0 failures, ~106 s each)**, confirming the new
  error/recovery tests are order-independent (each gets its own fresh
  per-test profile; the hotkey tests build their own real bridge/server
  and tear it down). The merge-required **`Web UI E2E (served, headless
  Chromium)`** check then ran the same suite on the self-hosted
  **LocalSystem** runner on commit `4d0b3b7` and concluded **SUCCESS —
  68 passed in 121.46 s** (run
  `https://github.com/bug-factory-kft/pippal/actions/runs/26040463378`),
  with `test_error_recovery.py::test_settings_ctx_install_registry_write_failure[chromium]`
  (UC-B11) **PASSED** in that real CI run — the CI log shows the invalid
  `HKXX` root raising the real `RuntimeError: ERROR: Invalid key name.`
  for the LocalSystem caller, so the result does not depend on caller
  privilege. The required `Lint` and `Unit tests` checks stayed green on
  the same commit. `py -3.11 -m pytest -q` → **266 passed** (unchanged; fully
  additive), `ruff check src/pippal tests e2e/web e2e/journey` → clean,
  `pytest --collect-only` → exactly 266, zero from `e2e/web`. Honest
  caveat: the synth-failed test (6.9) carries a documented
  real-behaviour caveat (core's transient `show_message` overwrite
  asserted at the sink) — see §6 and the backlog UC-D8 row. UC-B11's
  earlier `HKLM\SYSTEM` "locked-hive" seam was **incorrect** (LocalSystem
  has FullControl on `HKLM\SYSTEM`, so the write *succeeded* on the CI
  runner and the test wrongly failed + polluted the host); it was
  re-seamed to the privilege-independent invalid-root form above.
- **Phase-2 update (this PR update) — local headless run: 73 passed**
  (Chromium, served + headless): the 68 prior + the 5 new
  `test_core_interactions.py` Tier-1 tests (§7 / backlog UC-E8, UC-D9,
  UC-D10, UC-F1, UC-F2). The full `e2e/web` suite was run **3
  consecutive times — twice in definition order and once with the new
  Phase-2 file collected first (isolation check) — all 3 green (73/73
  each, 0 failures, ~130 s each)**, confirming the new tests are
  order-independent (each gets its own fresh per-test profile; the
  hotkey test builds its own real `HotkeyManager` and tears it down; the
  IPC test uses the hermetic ephemeral-port + token). The
  merge-required **`Web UI E2E (served, headless Chromium)`** check then
  ran the same suite on the self-hosted **LocalSystem** runner
  (`runs-on: [self-hosted, windows, pippal-windows]`, runner
  `pippal-ci-ACER-LAPTOP`) on commit `c3a1f44` and concluded **SUCCESS —
  73 passed in 143.43 s** (run
  `https://github.com/bug-factory-kft/pippal/actions/runs/26056179324`,
  job `…/job/76604725633`), with all 5 `test_core_interactions.py` tests
  **PASSED** in that real CI run — the CI log shows
  `PASSED e2e/web/test_core_interactions.py::test_queue_pause_stop_hotkey_dispatch_drives_real_engine[chromium]`,
  `…::test_overlay_no_text_selected_message_and_self_dismiss[chromium]`,
  `…::test_overlay_queued_message_and_self_dismiss[chromium]`,
  `…::test_pause_silences_and_resume_replays_then_seek_while_paused[chromium]`,
  `…::test_command_server_ipc_reject_branches_and_happy_roundtrips[chromium]`.
  The required `Lint` (pass, run 26056179322 job 76604725577) and
  `Unit tests` (pass, run 26056179322 job 76604725563) checks stayed
  green on the same commit. `py -3.11 -m pytest -q` →
  **266 passed** (unchanged; fully additive),
  `ruff check src/pippal tests e2e/web e2e/journey` → clean,
  `pytest --collect-only` → exactly 266, zero from `e2e/web`. Honest
  caveat: UC-D9's queued-while-speaking sub-case (7.3) carries the same
  documented UC-D8 transient-overwrite caveat (the concurrent real read
  overwrites the banner within µs; asserted at the real `show_message` /
  `_arm_hide_locked` sinks + the real `engine._queue` append, not via a
  flaky DOM poll) — see §7 and the backlog UC-D9/UC-D8 rows; the no-text
  sub-case (7.2) has no concurrent read and proves the served-DOM banner
  + self-dismiss directly.
- **Phase-3 update (this PR update) — local headless run: 77 passed**
  (Chromium, served + headless): the 73 prior + the 4 new
  `test_core_phase3.py` Tier-1 tests (§8 / backlog UC-A14, UC-A6,
  UC-A13). The full `e2e/web` suite was run **3 consecutive times —
  twice in definition order and once with the new Phase-3 file collected
  first (isolation check) — all 3 green (77/77 each, 0 failures, ~133 s
  each)**, confirming the new tests are order-independent (each gets its
  own fresh per-test profile; the activation-state files / `config`
  mutations the Phase-3 tests make are all restored in `finally` so the
  autouse `assert_fresh_baseline` guard still holds for the next test).
  The merge-required **`Web UI E2E (served, headless Chromium)`** check
  then ran the same suite on the self-hosted **LocalSystem** runner
  (`runs-on: [self-hosted, windows, pippal-windows]`, runner
  `pippal-ci-ACER-LAPTOP`) on the PR-#90 head commit
  `d5274b8cd30528e0ebd41752c2e147e9b4e97626` and concluded **SUCCESS —
  77 passed in 147.37 s** (run `26059080180` attempt 2, job
  `76615308301`), with all 4 `test_core_phase3.py` tests **PASSED** in
  that real CI run (`test_selected_text_activation_completes_on_real_selection_read[chromium]`,
  `test_selected_text_capture_failure_records_recovery_message[chromium]`,
  `test_onboarding_already_complete_reentry_close_and_play_again[chromium]`,
  `test_startup_auto_open_decision_real_composition_gate`). Attempt 1
  (job `76614399543`) had all 4 Phase-3 tests PASS but the run was red
  on a single **pre-existing, unrelated** flake —
  `test_web_ui.py::test_read_aloud_full_real_path_wav_karaoke_history[chromium]`
  (a Phase-0 real-Piper-synth karaoke-cursor timing test, row 4.11, in
  an **untouched** file; it was green on the immediately-prior PR head
  `6378295` and flakes independently of content); the `--failed` rerun
  (attempt 2) passed it and the whole suite cleanly, confirming it was
  not a regression and not introduced by this strictly-additive change.
  The required `Lint` (CI run `26059080040`, job `76614399544`) and
  `Unit tests` (job `76614399550`) checks were **SUCCESS** on the same
  head commit. `py -3.11 -m pytest -q` → **266 passed**
  (unchanged; fully additive — `test_core_phase3.py` is a new file, no
  production code touched), `ruff check src/pippal tests e2e/web
  e2e/journey` → clean, `pytest --collect-only` → exactly 266, zero from
  `e2e/web`. **UC-C9 is honestly NOT tested** — it is the Phase-3
  triaged & formally accepted parity gap (§8.5 / Honest parity note 4 /
  backlog UC-C9), recorded open rather than forced green.
- **Phase-4 update (this PR update) — local headless run: 81 passed**
  (Chromium, served + headless): the 77 prior + the 4 new
  `test_core_phase4.py` Tier-1 tests (§9 / backlog UC-B14, UC-E6,
  UC-D6, + the UC-E9 finding/exit-logic test). The full `e2e/web` suite
  was run **twice — once in definition order and once with the new
  Phase-4 file collected first (isolation check) — both green (81/81
  each, 0 failures, ~137 s each)**, confirming the new tests are
  order-independent (each gets its own fresh per-test profile; the
  `auto_hide_ms`/`config`/engine mutations are restored in `finally`,
  the IPC test uses the hermetic ephemeral port + a real
  `SO_EXCLUSIVEADDRUSE` holder it closes, and the registered WAV
  backend is unregistered on teardown so the autouse
  `assert_fresh_baseline` guard still holds for the next test). The
  Phase-4 Tier-2 journey **J6** (UC-B21) **passed twice** on the
  **REAL launched** WebView2 desktop app via
  `e2e/journey/run-journey.ps1`'s harness (CDP build
  `Edg/148.0.3967.70`, not headless; the launched app's own stderr log
  shows the genuine `[config] … unreadable …; moved to
  …config.json.bak` recovery message), with a **real per-journey
  recording artifact** captured each run exactly like J1–J5 (ffmpeg
  gdigrab `.mp4` ≈ 280–295 KB + Playwright `trace.zip` + window
  screenshot + app log + CDP version proof). `py -3.11 -m pytest -q` →
  **266 passed** (unchanged; fully additive — `test_core_phase4.py` /
  `test_journey_phase4.py` are new files, no production code touched),
  `ruff check src/pippal tests e2e/web e2e/journey` → clean,
  `pytest --collect-only` → exactly 266, zero from `e2e/web`. **UC-E9
  is honestly NOT flipped to covered** — Phase-4 triaged with a VERIFIED
  real product finding (the documented bind-conflict gate does not
  trigger for two real instances on Windows; §9.5 / Honest parity note
  5 / backlog UC-E9 + Honest gaps note 6), recorded open rather than
  forced green. The merge-required **`Web UI E2E (served, headless
  Chromium)`** + **`Lint`** + **`Unit tests`** checks were then
  confirmed on the self-hosted **LocalSystem** runner
  `pippal-ci-ACER-LAPTOP` on the pushed PR-#90 head — CI evidence
  (run/job/runner/pass-count/test-names) recorded in the PR; see the
  final report / commit trail.
- **Prior record (pre-Phase-1, still accurate for that state): 59
  passed** (Chromium, served + headless).
  Stability proven on that code: the full `e2e/web` suite was run
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
| J6 | Returning user's `config.json` is corrupt; the app must recover | `test_journey_phase4.py::test_j6_corrupt_config_recovers_to_defaults_and_bak` | corrupt `config.json` pre-written into the fresh profile → real `load_config` recovery runs at launch · real app did NOT crash · real `config.json.bak` is a byte-for-byte copy of the user's file · live `POST /bridge get_config` == layered defaults · no corrupt config remains (UC-B21 — first Tier-2 journey covering a previously-missing row) | [x] |
| J7 | User installs the Windows right-click entry, reads a file **through it**, removes it | `test_journey_phase5.py::test_j7_context_menu_install_read_through_it_remove` | the launched app's OWN real `bridge.install_context_menu` does genuine HKCU `reg add` · real registry keys present with the real `%1` command · the **exact registered command** (`python -m pippal.open_file <file>`, what Explorer spawns) run with THIS launched app's hermetic IPC identity → the **real running desktop process's real engine** reads the file (live `engine_state` + Recent history) · real `bridge.remove_context_menu` deletes the keys, registry clean. Hermetic: machine-wide registry lock + always-remove teardown; privilege-independent (UC-B11/B13/B12 — additive breadth) | [x] |
| J8 | User skips/replays a sentence during a real read (reader transport) | `test_journey_phase5.py::test_j8_replay_skip_transport_during_real_read` | a real multi-chunk read (`chunk_total=4`) · `next`/`prev` genuinely move the real `chunk_idx` (0→1→0) · `replay` accepted + process alive — driven through the launched app's OWN real `POST /bridge` `overlay_action`, the **exact transport the real desktop overlay prev/replay/next buttons use**. Honest finding: pause/resume (UC-D5/UC-D10) is NOT a journey leg (no real desktop web overlay pause control + IPC `/pause` 404s by default — they stay covered by their Tier-1 test) (UC-D3 — additive breadth) | [x] |

### Tier-2 non-journey-able controls (honest notes)

- **Native tray (`pystray`) clicks + global hotkeys (`keyboard`)** —
  OS-level, not DOM in the WebView2 window, so CDP cannot drive them.
  Already covered head-less in Tier-1
  (`e2e/web/test_tray_hotkey_integration.py`, §5) against the same
  callables; J1–J5 reach the same surfaces via in-app buttons.
- **`open_url`** (About links, onboarding "setup instructions") —
  shells out to the OS browser; driving it would test the browser, not
  PipPal. Bridge call covered in Tier-1.
- **Windows-integration Install/Remove right-click entry** — **now
  Tier-2-journeyed by J7** (Phase-5): the global per-user HKCU mutation
  is serialised under the SAME machine-wide registry lock the Tier-1
  hermetic shell test uses and ALWAYS removed in teardown (even on
  failure), so the journey leaves no machine state and cannot race
  other checkouts — and J7 adds the genuine value Tier-1 cannot: the
  **real launched desktop process** services the registered command
  end-to-end (Tier-1 only simulates it with a standalone command
  server). Tier-1's hermetic coverage stays as the merge-gate row.
- **Reader-transport PAUSE / RESUME (UC-D5/UC-D10)** — **honestly NOT
  a Tier-2 journey leg** (verified product fact, not fake-green): the
  real desktop web overlay window has **no pause control** (only
  prev/replay/next/close); the web `/bridge` has no `pause` method; the
  only genuine pause paths are the global hotkey (an OS keystroke
  boundary CDP cannot drive) and the IPC `/pause` *control route*,
  which `command_server.start_command_server` gates behind
  `control_routes_enabled` (**default `False`**; `app_web.main` never
  enables it) so `POST /pause` genuinely **404s** on the real launched
  process (empirically verified). J8 covers the genuinely-reachable
  UC-D3 transport; UC-D5/UC-D10 stay covered by their existing Tier-1
  test (`test_core_interactions.py::test_pause_silences_and_resume_replays_then_seek_while_paused`).
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
- `e2e\journey\run-journey.ps1 -Runs 2` → **both runs green, 0
  failures, 0 errors, 0 skipped** (full suite J1–J8: J1–J5 +
  Phase-4 J6 + Phase-5 J7/J8). Evidence bundle (log + JUnit + JSON
  summary + HTML report + per-journey real-window
  screenshot/app-log/CDP-build + per-journey **recordings**) written
  under `.e2e\evidence\journey-<UTC stamp>\`.
- **Phase-5 record (this machine):** `run-journey.ps1 -K
  test_journey_phase5 -Runs 2` → **both runs `test_j7_*` +
  `test_j8_*` PASSED, gate status=pass, exit 0** on the **real
  launched WebView2 app** (CDP `"Browser": "Edg/148.0.3967.70"` — a
  real desktop window, not `HeadlessChrome`), with a real per-journey
  `.mp4` (ffmpeg gdigrab) + `trace.zip` + window-screenshot recording
  attached each run; J7's genuine right-click round-trip
  (install→read-through-the-registered-command→remove) and J8's real
  reader transport (`next` 0→1, `prev` 1→0, `replay` accepted) proven
  on the live launched process; the global HKCU keys serialised under
  the machine-wide lock and removed in teardown (machine state clean).

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
