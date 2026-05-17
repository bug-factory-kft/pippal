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

Test files: `e2e/web/test_web_ui.py` (the original 17, kept) and
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

## 5. Tray + global hotkeys (native — `app_web.py` / `tray.py`)

The tray (pystray) and global hotkeys (keyboard) are deliberately kept
**native and unchanged** by this migration — the web frontend only
replaces the *windows*. They are out of scope of a served-headless
Playwright suite (no DOM, no served surface), so they are marked
not-E2E-testable here with the reason, and their *web-reachable effects*
(the window each tray item opens) ARE covered through the bridge.

| # | Control / function | Test / coverage | Status |
|---|---|---|---|
| 5.1 | Tray "Recent" submenu + Clear history | `test_history_clear_real_effect` (bridge get_history/clear_history — the same engine API the tray submenu calls) | [x] |
| 5.2 | Tray "Settings…" item | `test_settings_renders_seven_cards` covers the surface it opens; native pystray click not E2E-testable | [~] |
| 5.3 | Tray "First-run check" item | `test_onboarding_renders_and_closes` covers the surface it opens; native pystray click not E2E-testable | [~] |
| 5.4 | Tray "Quit" item | not E2E-testable: native pystray menu callback (`quit_action`) stops the icon/hotkeys/windows process — no DOM, would tear down the test host | [~] |
| 5.5 | Tray icon idle↔speaking swap (`make_tray_icon`) | not E2E-testable: a Pillow image painted into the OS tray, no served surface. Covered by the existing unit suite (`tests/`) | [~] |
| 5.6 | Global hotkeys (keyboard lib) | not E2E-testable: OS-level key hooks, native and unchanged. The bridge hotkey-rebind path IS covered (`test_settings_hotkey_*`) | [~] |

---

## Tally

| Section | Rows | `[x]` covered | `[~]` not-E2E (reason) | `[ ]` uncovered |
|---|---|---|---|---|
| §1 Onboarding | 14 | 14 | 0 | 0 |
| §2 Settings | 30 | 30 | 0 | 0 |
| §3 Voice Manager | 10 | 10 | 0 | 0 |
| §4 Reader overlay | 10 | 10 | 0 | 0 |
| §5 Tray / hotkeys | 6 | 1 | 5 | 0 |
| **Total** | **70** | **65** | **5** | **0** |

- **Total enumerated interactive rows:** 70
- **Covered by a genuine real-effect Playwright test (`[x]`):** 65
- **Not E2E-testable, marked with reason (`[~]`):** 5 — rows 5.2–5.6
  (native pystray menu callbacks, the OS tray icon image, OS-level
  keyboard hooks). None has a served DOM surface; the migration keeps
  them native and *unchanged*.
- **Uncovered (`[ ]`):** 0

> The §5 "not-E2E" rows are an honest limitation of a served-headless
> Playwright suite, not a skipped requirement: pystray menu callbacks,
> the OS tray icon image and OS-level keyboard hooks have no served DOM.
> The migration keeps them native and *unchanged*, and every effect of
> them that the web frontend can reach is exercised through the real
> bridge.

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
   and returns before `_remember`. Row 5.1 therefore exercises the
   genuine tray contract directly (real `pippal.history` round-trip →
   `engine.get_history()` via the bridge → `engine.clear_history()`
   empties memory *and* `history.json` on disk) instead of asserting a
   history entry that would never appear here (which would be a false
   positive).
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

- Files: `e2e/web/test_web_ui.py` (17 original, kept) +
  `e2e/web/test_web_ui_controls.py` (35 new, incl. parametrized).
- **Local headless run: 52 passed** (Chromium, served + headless,
  ~81 s), **stable across 3 full runs** + the order-independence runs.
- `py -3.11 -m pytest -q` → **262 passed** (unit suite unaffected;
  additive only). `ruff check src/pippal tests e2e/web` → clean.
- `e2e/web` stays excluded from the default `pytest` (`testpaths =
  tests`): `pytest --collect-only` collects exactly 262, zero from
  `e2e/web`.
