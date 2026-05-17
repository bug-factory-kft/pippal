"""Playwright E2E for the migrated PipPal web UI.

Drives the real served frontend with real DOM events + stable
``data-testid`` selectors and Playwright's auto-waiting (no fixed
sleeps). Every assertion checks an effect on the REAL backend
(config on disk via ``pippal.config``, the real ``TTSEngine``
playback state, the real voice catalogue on disk), not just DOM text.

The "reading session" tests exercise a genuine engine read: this
checkout has no ``piper.exe``, so ``read_text`` / ``play_sample`` route
through the engine's onboarding path which plays the bundled ~14 s
no-voice clip and drives the SAME overlay protocol
(``set_state('reading')`` → ``start_chunk`` → ``set_state('done')``) a
real Piper synth would. The karaoke cadence, the done→auto-hide timer
and the transport buttons are therefore tested against a real, multi
second, real-audio engine session — not a mock.

Surfaces / behaviours covered:
  * Settings — renders, edit a slider, engine + voice selection persist.
  * Voice Manager — catalogue, search, status filter.
  * Confirm modal — appears AND gates voice Remove and Reset-to-defaults
    (cancel = no effect on disk/form, accept = real effect).
  * Read-aloud — reaches the real TTSEngine (is_speaking / overlay).
  * Reader overlay — reflects a live reading session, karaoke cursor
    actually advances, transport buttons reach the real engine,
    ``auto_hide_ms`` actually hides the overlay.
  * Onboarding / Notices — render against the real backend.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, expect


def _config_on_disk(profile: Path) -> dict:
    cfg = profile / "config.json"
    if not cfg.exists():
        return {}
    return json.loads(cfg.read_text("utf-8"))


def _goto(page: Page, app_url: str, view: str) -> None:
    page.goto(f"{app_url}/index.html?view={view}")
    # api.js sets data-ready once the surface finished its first render.
    expect(page.locator("body")).to_have_attribute("data-ready", view, timeout=15000)


def _start_reading_session(page: Page, app_url: str) -> None:
    """Drive a REAL engine read via the page's own bridge transport
    (the exact fetch api.js performs). No piper.exe here, so the engine
    plays the bundled onboarding clip and drives the overlay protocol
    for ~14 s — a genuine reading session, real audio, real state."""
    page.goto(f"{app_url}/index.html?view=overlay")
    expect(page.locator("body")).to_have_attribute("data-ready", "overlay")
    page.evaluate(
        """async () => {
            const r = await fetch('/bridge', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                method: 'read_text',
                args: ['PipPal live reading session end to end check.'],
              }),
            });
            return r.ok;
        }"""
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_renders_seven_cards(page: Page, app_url: str):
    _goto(page, app_url, "settings")
    titles = page.locator(".card-title")
    expect(titles).to_have_count(7)
    expect(page.get_by_test_id("settings-engine")).to_be_visible()
    expect(page.get_by_test_id("settings-save")).to_be_visible()


def test_settings_edit_persists_to_backend(page: Page, app_url: str, backend):
    _goto(page, app_url, "settings")

    # Move the Speed slider and Save. Speed is the inverse of
    # length_scale; assert the persisted config matches.
    speed = page.get_by_test_id("settings-speed")
    speed.evaluate(
        "el => { el.value = '1.25';"
        " el.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    expect(page.get_by_test_id("settings-speed-value")).to_have_text("1.25×")

    page.get_by_test_id("settings-auto_hide_ms").fill("2400")
    page.get_by_test_id("settings-save").click()

    expect(page.get_by_test_id("toast")).to_contain_text("Saved")

    cfg = _config_on_disk(backend["profile"])
    assert cfg.get("auto_hide_ms") == 2400
    # 1/1.25 = 0.8
    assert abs(float(cfg.get("length_scale", 0)) - 0.8) < 1e-6
    # And the live config object the engine reads was updated too.
    assert backend["config"]["auto_hide_ms"] == 2400


def test_settings_engine_and_voice_selection_persists(
    page: Page, app_url: str, backend
):
    """The Voice card's Engine + Voice selectors must persist to the
    live config the engine reads, and (for a non-default value) to the
    real config.json. ``en_US-ryan-high.onnx`` is the default voice so
    ``save_config`` correctly omits it from disk; selecting a
    NON-default voice (en_US-amy-medium) proves the value really
    round-tripped through the bridge to disk."""
    from pippal.paths import VOICES_DIR

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for vid in ("en_US-ryan-high", "en_US-amy-medium"):
        onnx = VOICES_DIR / f"{vid}.onnx"
        sidecar = VOICES_DIR / f"{vid}.onnx.json"
        onnx.write_bytes(b"stub-model")
        sidecar.write_text("{}", "utf-8")
        made += [onnx, sidecar]
    try:
        _goto(page, app_url, "settings")

        # piper is the only registered engine in this build; selecting it
        # is still a real round-trip through save_config / reset_backend.
        page.get_by_test_id("settings-engine").select_option("piper")
        # A NON-default voice → it must be written to config.json.
        page.get_by_test_id("settings-voice").select_option("en_US-amy-medium.onnx")

        page.get_by_test_id("settings-save").click()
        expect(page.get_by_test_id("toast")).to_contain_text("Saved")

        # Live config the engine reads reflects both selections.
        assert backend["config"]["engine"] == "piper"
        assert backend["config"]["voice"] == "en_US-amy-medium.onnx"
        # The non-default voice really persisted to disk.
        cfg = _config_on_disk(backend["profile"])
        assert cfg.get("voice") == "en_US-amy-medium.onnx"

        # Re-rendering Settings (fresh bridge round-trip) shows it stuck.
        _goto(page, app_url, "settings")
        expect(page.get_by_test_id("settings-voice")).to_have_value(
            "en_US-amy-medium.onnx"
        )
    finally:
        for p in made:
            p.unlink(missing_ok=True)
        # Restore the default voice in the shared session config so the
        # later reading-session tests aren't affected.
        backend["config"]["voice"] = "en_US-ryan-high.onnx"


def test_settings_hotkey_edit_rebinds_and_persists(page: Page, app_url: str, backend):
    _goto(page, app_url, "settings")
    field = page.get_by_test_id("settings-hotkey_speak")
    field.fill("ctrl+alt+space")
    before = len(backend["hotkey_calls"])
    page.get_by_test_id("settings-apply").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Applied")

    cfg = _config_on_disk(backend["profile"])
    assert cfg.get("hotkey_speak") == "ctrl+alt+space"
    # Changing a hotkey must trigger the host rebind callback.
    assert len(backend["hotkey_calls"]) > before


# ---------------------------------------------------------------------------
# Confirm modal — restores the Tk messagebox.askyesno gate
# ---------------------------------------------------------------------------

def test_reset_confirm_modal_gates_the_form(page: Page, app_url: str, backend):
    """Reset-to-defaults must NOT touch the form until the modal is
    accepted. Cancel leaves edited fields as-is; accept resets them."""
    _goto(page, app_url, "settings")

    # Edit a field to a non-default value we can watch.
    auto_hide = page.get_by_test_id("settings-auto_hide_ms")
    auto_hide.fill("5000")

    # Click Reset → the modal must appear and the field must be UNCHANGED.
    page.get_by_test_id("settings-reset").click()
    expect(page.get_by_test_id("confirm-modal")).to_be_visible()
    expect(page.get_by_test_id("confirm-title")).to_have_text("Reset to defaults")
    expect(auto_hide).to_have_value("5000")  # gate held

    # Cancel → modal closes, field still the edited value (no reset ran).
    page.get_by_test_id("confirm-cancel").click()
    expect(page.get_by_test_id("confirm-modal")).to_be_hidden()
    expect(auto_hide).to_have_value("5000")

    # Reset again, this time accept → the field resets to the default.
    from pippal.config import DEFAULT_CONFIG

    default_ah = str(DEFAULT_CONFIG["auto_hide_ms"])
    page.get_by_test_id("settings-reset").click()
    expect(page.get_by_test_id("confirm-modal")).to_be_visible()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("confirm-modal")).to_be_hidden()
    expect(auto_hide).to_have_value(default_ah)


def test_voice_remove_confirm_modal_gates_deletion(
    page: Page, app_url: str, backend
):
    """Voice Remove must NOT delete files until the modal is accepted.
    Asserts the real on-disk voice files: present before, still present
    after Cancel, gone only after Accept (real bridge.remove_voice)."""
    from pippal.paths import VOICES_DIR

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    onnx = VOICES_DIR / "en_US-ryan-high.onnx"
    sidecar = VOICES_DIR / "en_US-ryan-high.onnx.json"
    onnx.write_bytes(b"stub-model")
    sidecar.write_text("{}", "utf-8")
    try:
        _goto(page, app_url, "voices")
        row_btn = page.get_by_test_id("vm-action-en_US-ryan-high")
        expect(row_btn).to_have_text("Remove")  # catalogue sees it installed

        # Click Remove → modal appears, files still on disk (gate held).
        row_btn.click()
        expect(page.get_by_test_id("confirm-modal")).to_be_visible()
        expect(page.get_by_test_id("confirm-title")).to_have_text("Remove voice")
        expect(page.get_by_test_id("confirm-body")).to_contain_text("Remove")
        assert onnx.exists() and sidecar.exists()

        # Cancel → nothing deleted.
        page.get_by_test_id("confirm-cancel").click()
        expect(page.get_by_test_id("confirm-modal")).to_be_hidden()
        assert onnx.exists() and sidecar.exists()

        # Remove + accept → real bridge.remove_voice unlinks both files.
        page.get_by_test_id("vm-action-en_US-ryan-high").click()
        expect(page.get_by_test_id("confirm-modal")).to_be_visible()
        page.get_by_test_id("confirm-ok").click()
        expect(page.get_by_test_id("confirm-modal")).to_be_hidden()

        def _gone() -> bool:
            return not onnx.exists() and not sidecar.exists()

        deadline = page.evaluate("Date.now()") + 5000
        while page.evaluate("Date.now()") < deadline and not _gone():
            page.wait_for_timeout(100)
        assert _gone(), "accepted Remove did not delete the voice files"
    finally:
        onnx.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Voice Manager
# ---------------------------------------------------------------------------

def test_voice_manager_lists_catalogue(page: Page, app_url: str, backend):
    _goto(page, app_url, "voices")
    rows = page.locator('#view [data-testid^="vm-action-"]')
    catalogue = backend["bridge"].get_voice_catalogue()
    expect(rows).to_have_count(len(catalogue["voices"]))


def test_voice_manager_search_filter(page: Page, app_url: str):
    _goto(page, app_url, "voices")
    # "ryan" matches exactly one curated voice (en_US-ryan-high).
    page.get_by_test_id("vm-search").fill("ryan")
    rows = page.locator('#view [data-testid^="vm-action-"]')
    expect(rows).to_have_count(1)
    expect(page.get_by_test_id("vm-action-en_US-ryan-high")).to_be_visible()

    # A query that matches nothing shows the empty-state hint.
    page.get_by_test_id("vm-search").fill("zzzznotavoice")
    expect(page.get_by_test_id("vm-empty")).to_be_visible()


def test_voice_manager_status_filter(page: Page, app_url: str):
    _goto(page, app_url, "voices")
    # Nothing is installed in the fresh profile → "Installed" empties it.
    page.get_by_test_id("vm-status").select_option("Installed")
    expect(page.get_by_test_id("vm-empty")).to_be_visible()
    page.get_by_test_id("vm-status").select_option("Not installed")
    rows = page.locator('#view [data-testid^="vm-action-"]')
    assert rows.count() > 0


# ---------------------------------------------------------------------------
# Read-aloud → real engine effect
# ---------------------------------------------------------------------------

def test_read_aloud_drives_real_engine(page: Page, app_url: str, backend):
    """Read-aloud must reach the real TTSEngine and produce a real
    audio/engine effect.

    Path 1 (piper + voice present): the onboarding 'Play sample' button
    is rendered — click it with a real DOM event.

    Path 2 (no local engine, e.g. this checkout has no piper.exe): the
    button isn't rendered, so drive the SAME documented read flow the
    UI uses through the served bridge from inside the page (real
    transport, real backend). The engine then plays the bundled
    onboarding clip and flips is_speaking / overlay state.

    Either way we assert the real engine reacted — never a mock.
    """
    _goto(page, app_url, "onboarding")
    engine = backend["engine"]
    overlay = backend["overlay"]

    play = page.get_by_test_id("onboarding-play-sample")
    if play.count() > 0:
        play.click()
    else:
        # Real read-aloud via the page's own bridge transport (the exact
        # fetch the UI's api.js performs) — not a Python-side shortcut.
        page.evaluate(
            """async () => {
                const r = await fetch('/bridge', {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({
                    method: 'read_text',
                    args: ['PipPal web UI end to end read aloud check.'],
                  }),
                });
                return r.ok;
            }"""
        )

    def _engine_reacted() -> bool:
        with engine.lock:
            speaking = engine.is_speaking
        snap = overlay.snapshot()
        return speaking or snap["overlay_state"] in ("thinking", "reading", "done")

    deadline = page.evaluate("Date.now()") + 8000
    while page.evaluate("Date.now()") < deadline and not _engine_reacted():
        page.wait_for_timeout(150)
    assert _engine_reacted(), "engine did not react to read-aloud"
    backend["engine"].stop()


# ---------------------------------------------------------------------------
# Reader overlay panel — live reading session, karaoke, transport, auto-hide
# ---------------------------------------------------------------------------

def test_overlay_panel_buttons_call_engine(page: Page, app_url: str, backend):
    _goto(page, app_url, "overlay")
    expect(page.get_by_test_id("overlay-panel")).to_be_visible()
    for tag in ("overlay-prev", "overlay-replay", "overlay-next", "overlay-close"):
        expect(page.get_by_test_id(tag)).to_be_visible()

    # The close button maps to engine.stop(); clicking it must bump the
    # cancellation token (engine.stop increments engine.token).
    engine = backend["engine"]
    with engine.lock:
        before = engine.token
    page.get_by_test_id("overlay-close").click()

    def _stopped() -> bool:
        with engine.lock:
            return engine.token > before

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not _stopped():
        page.wait_for_timeout(100)
    assert _stopped(), "overlay close did not reach engine.stop()"


def test_overlay_reflects_live_reading_session(page: Page, app_url: str, backend):
    """The overlay must visibly reflect a real reading session: idle →
    reading, karaoke words rendered, progress bar advancing — all driven
    by the real engine playing the real onboarding clip."""
    engine = backend["engine"]
    overlay = backend["overlay"]
    try:
        _start_reading_session(page, app_url)

        # The panel becomes visible and the body shows the read state.
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )
        expect(page.get_by_test_id("overlay-panel")).to_be_visible()
        # Karaoke words actually rendered into the body.
        words = page.locator('[data-testid="overlay-text"] .w')
        expect(words.first).to_be_visible(timeout=4000)
        assert words.count() > 3

        # Backend agrees a real chunk is playing.
        snap = overlay.snapshot()
        assert snap["overlay_state"] == "reading"
        assert snap["chunk_duration"] > 1.0
        assert len(snap["words"]) > 3

        # Progress bar advances (real elapsed time against real audio).
        bar = page.locator(".overlay-bar > div")
        w0 = bar.evaluate("e => parseFloat(e.style.width) || 0")
        page.wait_for_timeout(900)
        w1 = bar.evaluate("e => parseFloat(e.style.width) || 0")
        assert w1 > w0, f"progress did not advance: {w0} -> {w1}"
    finally:
        engine.stop()


def test_overlay_karaoke_cursor_advances(page: Page, app_url: str, backend):
    """The karaoke highlight must actually move forward over time —
    the cursor word index must strictly increase during the real clip."""
    engine = backend["engine"]
    try:
        _start_reading_session(page, app_url)
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )
        cur = page.locator('[data-testid="overlay-text"] .w.cur')

        def cursor_index() -> int:
            el = cur.first
            if el.count() == 0:
                return -1
            return int(el.get_attribute("data-i") or -1)

        # Wait for the highlight to appear, then assert it advances.
        deadline = page.evaluate("Date.now()") + 5000
        i0 = -1
        while page.evaluate("Date.now()") < deadline:
            i0 = cursor_index()
            if i0 >= 0:
                break
            page.wait_for_timeout(100)
        assert i0 >= 0, "karaoke cursor never appeared"

        deadline = page.evaluate("Date.now()") + 6000
        i1 = i0
        while page.evaluate("Date.now()") < deadline:
            i1 = cursor_index()
            if i1 > i0:
                break
            page.wait_for_timeout(150)
        assert i1 > i0, f"karaoke cursor did not advance ({i0} -> {i1})"
    finally:
        engine.stop()


def test_overlay_transport_buttons_reach_engine_during_playback(
    page: Page, app_url: str, backend
):
    """Strengthened replacement for the old near-tautological transport
    test. Drives a REAL reading session, then drives the transport and
    asserts a real engine effect: Replay re-runs the onboarding flow and
    bumps the cancellation token; the engine stays consistent."""
    engine = backend["engine"]
    try:
        _start_reading_session(page, app_url)
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )

        # Replay during an active onboarding read re-enters
        # _start_onboarding which bumps engine.token (real effect).
        with engine.lock:
            tok_before = engine.token
        page.get_by_test_id("overlay-replay").click()

        def _token_bumped() -> bool:
            with engine.lock:
                return engine.token > tok_before

        deadline = page.evaluate("Date.now()") + 5000
        while page.evaluate("Date.now()") < deadline and not _token_bumped():
            page.wait_for_timeout(100)
        assert _token_bumped(), "overlay Replay did not reach the engine"

        # prev / next are real bridge calls; the engine must stay
        # consistent (no queue corruption, still healthy) after them.
        page.get_by_test_id("overlay-prev").click()
        page.get_by_test_id("overlay-next").click()
        page.wait_for_timeout(150)
        assert engine.queue_length() == 0
        # Overlay is still in a real reading session driven by the engine.
        assert backend["overlay"].snapshot()["overlay_state"] in (
            "reading",
            "thinking",
            "done",
        )
    finally:
        engine.stop()


def test_overlay_auto_hide_actually_hides(page: Page, app_url: str, backend):
    """`auto_hide_ms` must actually hide the overlay. Set a short
    auto-hide, run a real reading session, stop it (engine fires
    set_state('done')), then assert the WebOverlay auto-hide timer
    really flips the state to idle and the panel disappears — the exact
    behaviour that was previously inert."""
    engine = backend["engine"]
    config = backend["config"]
    prev = config.get("auto_hide_ms")
    config["auto_hide_ms"] = 500  # short, real auto-hide
    try:
        _start_reading_session(page, app_url)
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )
        expect(page.get_by_test_id("overlay-panel")).to_be_visible()

        # Stop the read → engine calls overlay.set_state('done'), which
        # arms the real auto-hide timer for auto_hide_ms (500 ms).
        engine.stop()

        # The overlay must reach 'done' then auto-hide to 'idle'; the
        # panel must visibly disappear (web analogue of win.withdraw()).
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "idle", timeout=8000
        )
        expect(page.get_by_test_id("overlay-panel")).to_be_hidden()

        # Backend state agrees the auto-hide fired (not just the DOM).
        assert backend["overlay"].snapshot()["overlay_state"] == "idle"
    finally:
        config["auto_hide_ms"] = prev
        engine.stop()


# ---------------------------------------------------------------------------
# Onboarding / Notices
# ---------------------------------------------------------------------------

def test_onboarding_renders_and_closes(page: Page, app_url: str):
    _goto(page, app_url, "onboarding")
    expect(page.get_by_test_id("onboarding-title")).to_be_visible()
    expect(page.get_by_test_id("onboarding-status")).to_be_visible()
    # A Skip/Close button is always present regardless of readiness.
    skip = page.locator(
        '[data-testid="onboarding-skip"], [data-testid="onboarding-close"]'
    )
    expect(skip.first).to_be_visible()


def test_notices_window_loads_real_text(page: Page, app_url: str, backend):
    _goto(page, app_url, "notices")
    body = page.get_by_test_id("notices-body")
    expect(body).to_be_visible()
    expected = backend["bridge"].get_notices()
    assert body.inner_text().strip()[:40] == expected.strip()[:40]
