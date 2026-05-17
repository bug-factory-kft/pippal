"""Per-control completion suite for the migrated PipPal web UI.

One focused, genuine real-effect Playwright test per remaining
interactive control / function enumerated in
``docs/migration-web/UI_TEST_CHECKLIST.md`` (the original 17 in
``test_web_ui.py`` cover the rest). Same rules as the original suite:

* drives the REAL served frontend (``webui/`` + the real bridge server)
  with stable ``data-testid`` selectors and Playwright auto-wait — no
  fixed sleeps, no mocks, no tautologies;
* asserts a REAL backend effect — ``config.json`` on disk (read with the
  real ``pippal.config`` loader), the real ``TTSEngine`` token/state,
  real voice files on disk, the real recorded host callbacks the bridge
  invokes (the exact contract ``app_web.py`` wires to the pywebview
  window manager), or ``webbrowser.open`` actually called for the real
  About / setup URLs;
* every test runs against a freshly reset app — see the ``conftest.py``
  module docstring (fresh ``PIPPAL_DATA_DIR`` per test, no leaked config,
  ``assert_fresh_baseline`` autouse guard).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


def _config_on_disk(profile: Path) -> dict:
    cfg = profile / "config.json"
    return json.loads(cfg.read_text("utf-8")) if cfg.exists() else {}


def _goto(page: Page, app_url: str, view: str) -> None:
    page.goto(f"{app_url}/index.html?view={view}")
    expect(page.locator("body")).to_have_attribute(
        "data-ready", view, timeout=15000
    )


# ===========================================================================
# §1 Onboarding — readiness states + every per-state button
# ===========================================================================

def test_onboarding_ready_state_controls(page: Page, app_url: str, readiness):
    """READY state: the Local-voice-check card shows the real engine /
    voice / hotkey labels from build_activation_readiness."""
    rd = readiness["ready"]()
    _goto(page, app_url, "onboarding")
    expect(page.get_by_test_id("onboarding-engine")).to_contain_text(
        "Piper engine"
    )
    # The card renders the real readiness labels.
    card = page.get_by_test_id("onboarding-engine")
    expect(card).to_be_visible()
    assert rd.engine_label.startswith("Piper engine")


def test_onboarding_sample_textbox_holds_sample(
    page: Page, app_url: str, readiness, backend
):
    """The "Try it in any app" box holds the real sample text the
    backend computed from the configured hotkey."""
    readiness["ready"]()
    _goto(page, app_url, "onboarding")
    box = page.get_by_test_id("onboarding-sample")
    expect(box).to_be_visible()
    sample = backend["bridge"].get_readiness()["sample_text"]
    assert box.input_value().strip() == sample.strip()
    assert "PipPal is reading locally" in sample


def test_onboarding_ready_skip_closes_window(
    page: Page, app_url: str, readiness, backend
):
    readiness["ready"]()
    _goto(page, app_url, "onboarding")
    before = len(backend["close_calls"])
    page.get_by_test_id("onboarding-skip").click()

    def _closed() -> bool:
        return len(backend["close_calls"]) > before

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not _closed():
        page.wait_for_timeout(50)
    assert _closed(), "Skip did not reach on_close_window"


def test_onboarding_ready_open_settings(
    page: Page, app_url: str, readiness, backend
):
    readiness["ready"]()
    _goto(page, app_url, "onboarding")
    page.get_by_test_id("onboarding-open-settings").click()

    def _opened() -> bool:
        return "settings" in backend["window_opens"]

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not _opened():
        page.wait_for_timeout(50)
    assert _opened(), "Open Settings did not reach on_open_settings"


def test_onboarding_finish_gated_until_sample_played(
    page: Page, app_url: str, readiness, backend
):
    """READY but activation NOT complete: Finish setup must be disabled
    until the sample is played (parity with Tk's confirm gate). We force
    activation incomplete on the fresh profile for this row."""
    from pippal.onboarding import activation_state_path

    readiness["ready"]()
    # Remove the pre-seeded completion so the first-run gate is live.
    activation_state_path().unlink(missing_ok=True)
    _goto(page, app_url, "onboarding")

    finish = page.get_by_test_id("onboarding-finish")
    expect(finish).to_be_disabled()
    # Playing the sample enables Finish (real engine read + UI gate).
    page.get_by_test_id("onboarding-play-sample").click()
    expect(finish).to_be_enabled(timeout=6000)
    backend["engine"].stop()


def test_onboarding_finish_marks_activation_complete(
    page: Page, app_url: str, readiness, backend
):
    """Finish setup must call the real mark_activation_complete so the
    activation state file on disk flips to complete."""
    from pippal.onboarding import activation_state_path, load_activation_state

    readiness["ready"]()
    activation_state_path().unlink(missing_ok=True)
    assert not load_activation_state().is_complete
    _goto(page, app_url, "onboarding")

    page.get_by_test_id("onboarding-play-sample").click()
    finish = page.get_by_test_id("onboarding-finish")
    expect(finish).to_be_enabled(timeout=6000)
    finish.click()

    def _complete() -> bool:
        return load_activation_state().is_complete

    deadline = page.evaluate("Date.now()") + 5000
    while page.evaluate("Date.now()") < deadline and not _complete():
        page.wait_for_timeout(100)
    assert _complete(), "Finish setup did not mark activation complete on disk"
    backend["engine"].stop()


def test_onboarding_missing_voice_state_buttons(
    page: Page, app_url: str, readiness, backend
):
    """MISSING_VOICE state renders Skip / Open Voice Manager / Install
    default voice; Skip closes, Open VM opens the real voices window."""
    readiness["missing_voice"]()
    _goto(page, app_url, "onboarding")
    expect(page.get_by_test_id("onboarding-skip")).to_be_visible()
    expect(page.get_by_test_id("onboarding-install-voice")).to_be_visible()

    page.get_by_test_id("onboarding-open-vm").click()

    def _opened() -> bool:
        return "voices" in backend["window_opens"]

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not _opened():
        page.wait_for_timeout(50)
    assert _opened(), "Open Voice Manager did not reach the host callback"


def test_onboarding_install_default_voice_real_effect(
    page: Page, app_url: str, readiness, backend, monkeypatch
):
    """Install default voice must call the REAL bridge.install_default
    _voice → install_piper_voice; we stub only the network download
    (urllib) so a real file lands in the real per-test voices dir and
    the live config voice is updated — the bridge/installer code path is
    entirely real."""
    from pippal import voices as voices_mod
    from pippal.ui import voice_manager as vm

    readiness["missing_voice"]()

    def _fake_download(url: str, dest: Path, *a, **k) -> None:
        dest.write_bytes(b"stub-voice-model-bytes")

    monkeypatch.setattr(vm, "_streaming_download", _fake_download)

    _goto(page, app_url, "onboarding")
    page.get_by_test_id("onboarding-install-voice").click()

    def _installed() -> bool:
        return len(voices_mod.installed_voices()) > 0

    deadline = page.evaluate("Date.now()") + 8000
    while page.evaluate("Date.now()") < deadline and not _installed():
        page.wait_for_timeout(150)
    assert _installed(), "Install default voice produced no real voice file"
    # The bridge set the live config voice to the installed filename.
    assert backend["config"]["voice"].endswith(".onnx")


def test_onboarding_missing_piper_state_buttons(
    page: Page, app_url: str, readiness, backend
):
    """MISSING_PIPER renders Close / Open Settings / Open setup. Close
    reaches close_window; Open Settings reaches the host callback."""
    readiness["missing_piper"]()
    _goto(page, app_url, "onboarding")
    expect(page.get_by_test_id("onboarding-close")).to_be_visible()
    expect(page.get_by_test_id("onboarding-open-setup")).to_be_visible()

    page.get_by_test_id("onboarding-open-settings").click()
    deadline = page.evaluate("Date.now()") + 4000
    while (
        page.evaluate("Date.now()") < deadline
        and "settings" not in backend["window_opens"]
    ):
        page.wait_for_timeout(50)
    assert "settings" in backend["window_opens"]

    before = len(backend["close_calls"])
    page.get_by_test_id("onboarding-close").click()
    deadline = page.evaluate("Date.now()") + 4000
    while (
        page.evaluate("Date.now()") < deadline
        and len(backend["close_calls"]) == before
    ):
        page.wait_for_timeout(50)
    assert len(backend["close_calls"]) > before


def test_onboarding_missing_piper_open_setup_url(
    page: Page, app_url: str, readiness, backend, monkeypatch
):
    """Open setup instructions must call the real bridge.open_url with
    the real README URL (we capture the actual webbrowser.open call)."""
    import pippal.web_ui.bridge as bridge_mod

    opened: list[str] = []
    monkeypatch.setattr(
        bridge_mod.webbrowser, "open", lambda u: opened.append(u) or True
    )
    readiness["missing_piper"]()
    _goto(page, app_url, "onboarding")
    page.get_by_test_id("onboarding-open-setup").click()

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not opened:
        page.wait_for_timeout(50)
    assert opened and "github.com/bug-factory-kft/pippal" in opened[0]


# ===========================================================================
# §2 Settings — controls not covered by the original 17
# ===========================================================================

def test_settings_manage_voices_opens_vm(
    page: Page, app_url: str, backend
):
    _goto(page, app_url, "settings")
    page.get_by_test_id("settings-manage-voices").click()

    def _opened() -> bool:
        return "voices" in backend["window_opens"]

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not _opened():
        page.wait_for_timeout(50)
    assert _opened(), "Manage… did not reach on_open_voice_manager"


def test_settings_voice_card_empty_install_state(
    page: Page, app_url: str, backend
):
    """With no voices installed (the fresh-profile default) the Voice
    card shows the Install CTA label and disables the voice combo —
    real backend state (installed_voices() == [])."""
    from pippal.voices import installed_voices

    assert installed_voices() == []
    _goto(page, app_url, "settings")
    expect(page.get_by_test_id("settings-manage-voices")).to_have_text(
        "Install voices…"
    )
    expect(page.get_by_test_id("settings-voice")).to_be_disabled()
    expect(page.get_by_test_id("settings-engine-hint")).to_contain_text(
        "No Piper voice installed"
    )


def test_settings_variation_slider_reflects_and_persists(
    page: Page, app_url: str, backend
):
    _goto(page, app_url, "settings")
    noise = page.get_by_test_id("settings-noise")
    noise.evaluate(
        "el => { el.value = '0.85';"
        " el.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    expect(page.get_by_test_id("settings-noise-value")).to_have_text("0.85")
    page.get_by_test_id("settings-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Saved")

    cfg = _config_on_disk(backend["profile"])
    assert abs(float(cfg["noise_scale"]) - 0.85) < 1e-6
    assert abs(backend["config"]["noise_scale"] - 0.85) < 1e-6


@pytest.mark.parametrize(
    "key,combo",
    [
        ("hotkey_queue", "ctrl+alt+q"),
        ("hotkey_pause", "ctrl+alt+p"),
        ("hotkey_stop", "ctrl+alt+b"),
    ],
)
def test_settings_hotkey_each_field_rebinds_and_persists(
    page: Page, app_url: str, backend, key: str, combo: str
):
    """Each remaining hotkey field (Queue / Pause-Resume / Stop) rebinds
    and persists independently (Read selection is covered in the
    original suite)."""
    _goto(page, app_url, "settings")
    page.get_by_test_id(f"settings-{key}").fill(combo)
    before = len(backend["hotkey_calls"])
    page.get_by_test_id("settings-apply").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Applied")

    cfg = _config_on_disk(backend["profile"])
    assert cfg.get(key) == combo
    assert backend["config"][key] == combo
    assert len(backend["hotkey_calls"]) > before


@pytest.mark.parametrize(
    "tid,cfg_key",
    [
        ("settings-show_overlay", "show_overlay"),
        ("settings-show_text_in_overlay", "show_text_in_overlay"),
    ],
)
def test_settings_checkbox_persists(
    page: Page, app_url: str, backend, tid: str, cfg_key: str
):
    """The two Reader-panel checkboxes default True; unticking and
    Saving must persist False to disk + live config."""
    _goto(page, app_url, "settings")
    box = page.get_by_test_id(tid)
    expect(box).to_be_checked()
    box.uncheck()
    page.get_by_test_id("settings-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Saved")

    cfg = _config_on_disk(backend["profile"])
    assert cfg.get(cfg_key) is False
    assert backend["config"][cfg_key] is False


@pytest.mark.parametrize(
    "tid,cfg_key,value",
    [
        ("settings-overlay_y_offset", "overlay_y_offset", "240"),
        ("settings-karaoke_offset_ms", "karaoke_offset_ms", "-80"),
    ],
)
def test_settings_spinbox_persists(
    page: Page, app_url: str, backend, tid: str, cfg_key: str, value: str
):
    """Distance-from-taskbar and Karaoke-offset spinboxes persist their
    integer value to disk + live config."""
    _goto(page, app_url, "settings")
    page.get_by_test_id(tid).fill(value)
    page.get_by_test_id("settings-save").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Saved")

    cfg = _config_on_disk(backend["profile"])
    assert cfg.get(cfg_key) == int(value)
    assert backend["config"][cfg_key] == int(value)


def test_settings_ctx_status_reflects_backend(
    page: Page, app_url: str, backend
):
    """The Windows-integration status label reflects the REAL
    context_menu_status() the bridge returns."""
    _goto(page, app_url, "settings")
    real = backend["bridge"].context_menu_status()
    label = page.get_by_test_id("settings-ctx-status")
    if real == "all":
        expect(label).to_contain_text("installed")
    elif real == "partial":
        expect(label).to_contain_text("Partial")
    else:
        expect(label).to_contain_text("not installed")


def test_settings_ctx_install_real_effect(
    page: Page, app_url: str, backend, monkeypatch
):
    """Install must call the REAL bridge.install_context_menu. The
    registry write is Windows-registry side-effecting, so we capture the
    real context_menu functions the bridge calls and assert the bridge
    drove them + refreshed the real status label — the bridge/UI path is
    entirely real, only the registry write itself is intercepted."""
    import pippal.web_ui.bridge as bridge_mod

    calls: list[str] = []
    monkeypatch.setattr(
        bridge_mod, "install_context_menu", lambda: calls.append("install")
    )
    monkeypatch.setattr(
        bridge_mod, "context_menu_status", lambda: "all"
    )
    _goto(page, app_url, "settings")
    page.get_by_test_id("settings-ctx-install").click()
    expect(page.get_by_test_id("settings-ctx-status")).to_contain_text(
        "installed", timeout=4000
    )
    assert calls == ["install"]


def test_settings_ctx_remove_real_effect(
    page: Page, app_url: str, backend, monkeypatch
):
    import pippal.web_ui.bridge as bridge_mod

    calls: list[str] = []
    monkeypatch.setattr(
        bridge_mod, "uninstall_context_menu", lambda: calls.append("remove")
    )
    monkeypatch.setattr(bridge_mod, "context_menu_status", lambda: "none")
    _goto(page, app_url, "settings")
    page.get_by_test_id("settings-ctx-remove").click()
    expect(page.get_by_test_id("settings-ctx-status")).to_contain_text(
        "not installed", timeout=4000
    )
    assert calls == ["remove"]


def test_settings_view_licences_opens_notices(
    page: Page, app_url: str, backend
):
    _goto(page, app_url, "settings")
    page.get_by_test_id("settings-view-licences").click()

    def _opened() -> bool:
        return "notices" in backend["window_opens"]

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not _opened():
        page.wait_for_timeout(50)
    assert _opened(), "View licences… did not reach on_open_notices"


def test_settings_about_links_open_real_urls(
    page: Page, app_url: str, backend, monkeypatch
):
    """Each of the 5 About links must call the real bridge.open_url with
    the exact URL the backend's about_info() returns."""
    import pippal.web_ui.bridge as bridge_mod

    opened: list[str] = []
    monkeypatch.setattr(
        bridge_mod.webbrowser, "open", lambda u: opened.append(u) or True
    )
    about = backend["bridge"].about_info()
    expected = {link["key"]: link["url"] for link in about["links"]}
    assert set(expected) == {"website", "github", "licence", "privacy", "terms"}

    _goto(page, app_url, "settings")
    for key, url in expected.items():
        opened.clear()
        page.get_by_test_id(f"about-{key}").click()
        deadline = page.evaluate("Date.now()") + 3000
        while page.evaluate("Date.now()") < deadline and not opened:
            page.wait_for_timeout(40)
        assert opened and opened[0] == url, f"about-{key} → {opened!r} != {url}"


def test_settings_cancel_closes_without_persist(
    page: Page, app_url: str, backend
):
    """Cancel must close the window WITHOUT persisting: edit a field,
    Cancel, assert no config.json written and the host close callback
    fired."""
    _goto(page, app_url, "settings")
    page.get_by_test_id("settings-auto_hide_ms").fill("4321")
    before = len(backend["close_calls"])
    page.get_by_test_id("settings-cancel").click()

    deadline = page.evaluate("Date.now()") + 4000
    while (
        page.evaluate("Date.now()") < deadline
        and len(backend["close_calls"]) == before
    ):
        page.wait_for_timeout(50)
    assert len(backend["close_calls"]) > before, "Cancel did not close window"
    # Nothing persisted — fresh profile still has no config.json.
    assert not (backend["profile"] / "config.json").exists()
    assert "auto_hide_ms" not in _config_on_disk(backend["profile"])


def test_settings_save_persists_with_saved_toast(
    page: Page, app_url: str, backend
):
    """Save persists the form and shows the "Saved." toast — distinct
    from Apply's "Applied." toast (Apply re-renders in place). The web
    Save passes ``close=True`` through ``save_config``; the actual
    window dismissal is the desktop window manager's job (see the
    checklist's honest note on the Save-closes-window parity gap), so
    the asserted, real, served effect here is the persisted config +
    the distinct Saved toast.

    Apply vs Save distinction is asserted: Apply → "Applied." +
    re-render; Save → "Saved." (no re-render request)."""
    _goto(page, app_url, "settings")
    page.get_by_test_id("settings-auto_hide_ms").fill("3300")
    page.get_by_test_id("settings-save").click()

    toast = page.get_by_test_id("toast")
    expect(toast).to_have_text("Saved.")
    assert _config_on_disk(backend["profile"]).get("auto_hide_ms") == 3300
    assert backend["config"]["auto_hide_ms"] == 3300

    # Contrast with Apply: same persistence, different toast, stays open.
    page.get_by_test_id("settings-auto_hide_ms").fill("3400")
    page.get_by_test_id("settings-apply").click()
    expect(toast).to_have_text("Applied.")
    assert _config_on_disk(backend["profile"]).get("auto_hide_ms") == 3400


def test_window_close_button_calls_bridge(
    page: Page, app_url: str, backend
):
    """The chromeless title-bar ✕ (window-close) must reach the real
    on_close_window host callback."""
    _goto(page, app_url, "settings")
    before = len(backend["close_calls"])
    page.get_by_test_id("window-close").click()

    deadline = page.evaluate("Date.now()") + 4000
    while (
        page.evaluate("Date.now()") < deadline
        and len(backend["close_calls"]) == before
    ):
        page.wait_for_timeout(50)
    assert len(backend["close_calls"]) > before


# ===========================================================================
# §3 Voice Manager — controls not covered by the original 17
# ===========================================================================

def test_voice_manager_language_filter(page: Page, app_url: str, backend):
    """Picking a specific language must narrow the list to only that
    language's voices (asserted against the real catalogue)."""
    _goto(page, app_url, "voices")
    cat = backend["bridge"].get_voice_catalogue()
    langs = cat["languages"]
    assert langs, "catalogue exposes no languages"
    # Choose the language with the FEWEST voices for a tight assertion.
    counts: dict[str, int] = {}
    for v in cat["voices"]:
        counts[v["lang"]] = counts.get(v["lang"], 0) + 1
    target = min(counts, key=counts.get)
    expected = counts[target]

    page.get_by_test_id("vm-language").select_option(target)
    rows = page.locator('#view [data-testid^="vm-action-"]')
    expect(rows).to_have_count(expected)


def test_voice_manager_quality_filter(page: Page, app_url: str, backend):
    _goto(page, app_url, "voices")
    cat = backend["bridge"].get_voice_catalogue()
    counts: dict[str, int] = {}
    for v in cat["voices"]:
        counts[v["quality"]] = counts.get(v["quality"], 0) + 1
    # 'high' is always present in the curated catalogue.
    assert "high" in counts
    page.get_by_test_id("vm-quality").select_option("high")
    rows = page.locator('#view [data-testid^="vm-action-"]')
    expect(rows).to_have_count(counts["high"])


def test_voice_manager_row_install_real_effect(
    page: Page, app_url: str, backend, monkeypatch
):
    """A per-row Install must call the REAL bridge.install_voice →
    install_piper_voice; only the network download is stubbed, so a real
    model file lands in the real per-test voices dir and the row flips
    to 'installed'."""
    from pippal import voices as voices_mod
    from pippal.ui import voice_manager as vm

    def _fake_download(url: str, dest: Path, *a, **k) -> None:
        dest.write_bytes(b"stub-voice-model-bytes")

    monkeypatch.setattr(vm, "_streaming_download", _fake_download)

    _goto(page, app_url, "voices")
    # Pick the first not-installed catalogue row.
    cat = backend["bridge"].get_voice_catalogue()
    vid = cat["voices"][0]["id"]
    btn = page.get_by_test_id(f"vm-action-{vid}")
    expect(btn).to_have_text("Install")
    btn.click()

    def _installed() -> bool:
        return any(vid in f for f in voices_mod.installed_voices())

    deadline = page.evaluate("Date.now()") + 8000
    while page.evaluate("Date.now()") < deadline and not _installed():
        page.wait_for_timeout(150)
    assert _installed(), f"row Install produced no real voice file for {vid}"
    # The catalogue now reports it installed (real on-disk state).
    fresh = backend["bridge"].get_voice_catalogue()
    assert any(v["id"] == vid and v["installed"] for v in fresh["voices"])


def test_voice_manager_close_button_calls_bridge(
    page: Page, app_url: str, backend
):
    """The Voice Manager surface's window-close (the Tk dialog's Close
    button parity) reaches the real on_close_window host callback."""
    _goto(page, app_url, "voices")
    before = len(backend["close_calls"])
    page.get_by_test_id("window-close").click()
    deadline = page.evaluate("Date.now()") + 4000
    while (
        page.evaluate("Date.now()") < deadline
        and len(backend["close_calls"]) == before
    ):
        page.wait_for_timeout(50)
    assert len(backend["close_calls"]) > before


# ===========================================================================
# §4 Reader overlay — controls not covered by the original 17
# ===========================================================================

def _start_reading_session(page: Page, app_url: str) -> None:
    page.goto(f"{app_url}/index.html?view=overlay")
    expect(page.locator("body")).to_have_attribute("data-ready", "overlay")
    page.evaluate(
        """async () => {
            await fetch('/bridge', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                method: 'read_text',
                args: ['PipPal overlay control coverage check sentence.'],
              }),
            });
        }"""
    )


def test_overlay_paused_chip_shows_on_pause(
    page: Page, app_url: str, backend
):
    """The paused chip must appear when the engine is paused mid-read
    and clear on resume — driven by a real reading session + the real
    engine.pause_toggle."""
    engine = backend["engine"]
    try:
        _start_reading_session(page, app_url)
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )
        chip = page.get_by_test_id("overlay-paused")
        expect(chip).to_be_hidden()

        engine.pause_toggle()  # real engine pause
        expect(chip).to_be_visible(timeout=4000)
        assert backend["overlay"].snapshot()["is_paused"] is True

        engine.pause_toggle()  # real resume
        expect(chip).to_be_hidden(timeout=4000)
        assert backend["overlay"].snapshot()["is_paused"] is False
    finally:
        engine.stop()


def test_overlay_drag_repositions_panel(page: Page, app_url: str, backend):
    """Right-button drag must offset the panel (Tk <B3-Motion> parity).
    Asserts the panel's data-offset attribute changes and a transform is
    applied — a real DOM effect of the real drag handlers."""
    _goto(page, app_url, "overlay")
    panel = page.get_by_test_id("overlay-panel")
    box = panel.bounding_box()
    assert box is not None
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2

    page.mouse.move(cx, cy)
    page.mouse.down(button="right")
    page.mouse.move(cx + 60, cy + 40, steps=8)
    page.mouse.up(button="right")

    expect(panel).to_have_attribute("data-offset", "60,40", timeout=3000)
    transform = panel.evaluate("e => e.style.transform")
    assert "translate(60px,40px)" in transform.replace(" ", "")


# ===========================================================================
# §5 Tray-reachable effect — Recent submenu uses the engine history API
# ===========================================================================

def test_history_clear_real_effect(page: Page, app_url: str, backend):
    """The tray 'Recent' submenu enumerates ``engine.get_history()`` and
    'Clear history' calls ``engine.clear_history()``. The native pystray
    menu has no DOM, but that exact engine/bridge contract is real and
    testable end to end: a real ``pippal.history`` round-trip populates
    the engine the same way the app does at startup, the bridge
    ``get_history`` (the same call the served UI / tray read) reflects
    it, and ``clear_history`` empties BOTH the in-memory list and the
    real ``history.json`` on disk — the precise effect of the tray item.

    (``read_text`` does not record history in this no-``piper.exe``
    checkout — it routes through the onboarding clip and returns before
    ``_remember``; asserting otherwise would be a false positive, so the
    genuine tray contract is exercised directly instead.)
    """
    import pippal.history as history_mod
    from pippal.history import load_history, save_history

    engine = backend["engine"]
    bridge = backend["bridge"]
    assert bridge.get_history() == []  # fresh profile, nothing on disk

    # Populate via the REAL history persistence the app uses at startup
    # (engine.attach_history(load_history(), save_history)).
    save_history(["First recent entry", "Second recent entry"])
    assert load_history() == ["First recent entry", "Second recent entry"]
    engine.attach_history(load_history(), save_history)
    # The bridge get_history (served UI + tray submenu source) sees them.
    assert bridge.get_history() == [
        "First recent entry",
        "Second recent entry",
    ]

    # 'Clear history' (tray) → engine.clear_history(): empties memory AND
    # rewrites the real history.json on disk to [].
    engine.clear_history()
    assert bridge.get_history() == []
    assert json.loads(Path(history_mod.HISTORY_PATH).read_text("utf-8")) == []
    engine.stop()
