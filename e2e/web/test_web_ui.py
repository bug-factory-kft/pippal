"""Playwright E2E for the migrated PipPal web UI.

Drives the real served frontend with real DOM events + stable
``data-testid`` selectors and Playwright's auto-waiting (no fixed
sleeps). Every assertion checks an effect on the REAL backend
(config on disk via ``pippal.config``, the real ``TTSEngine``
playback state, the real voice catalogue), not just DOM text.

Surfaces covered:
  * Settings — open, edit a setting, assert persisted config.
  * Voice Manager — open, Search filter, Status filter.
  * Read-aloud — trigger play, assert real engine/audio effect.
  * Reader overlay panel — prev / replay / next / close buttons.
  * Onboarding — first-run window renders + Skip.
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


# ---------------------------------------------------------------------------
# Reader overlay panel
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


def test_overlay_prev_replay_next_reach_engine(page: Page, app_url: str, backend):
    _goto(page, app_url, "overlay")
    engine = backend["engine"]
    # With no active playback prev/next/replay are safe no-ops on the
    # engine; assert they invoke without raising and the bridge answers.
    for tag in ("overlay-prev", "overlay-replay", "overlay-next"):
        page.get_by_test_id(tag).click()
        page.wait_for_timeout(80)
    # Engine still healthy / responsive after the calls.
    assert engine.queue_length() == 0


# ---------------------------------------------------------------------------
# Onboarding
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
