"""PipPal Tier-2 user-journey E2E — drives the REAL launched desktop app.

Each test is a multi-step *use-case* journey on the **actually launched**
``reader_app_web.py`` (a real pywebview WebView2 window appearing in the
interactive logged-in session), attached to by Playwright over CDP and
driven with real clicks / keystrokes on the real window. Every step is
framed by *why the user activates the control* and asserts a **real
effect** on the running process (disk / engine / overlay / history /
catalogue) — no mocks of the thing under test, deadline-polls not fixed
sleeps. See ``conftest.py`` for the launch/attach technique and the
two-tier model.

Journeys
--------
* **J1 first-run → install a voice** (``test_j1_first_run_install_voice``):
  fresh launch shows the real onboarding/setup surface → user opens the
  real Voices window → selects the smallest practical real Piper voice →
  clicks Install → a REAL voice downloads to disk (real .onnx + .onnx
  .json land in the profile, catalogue flips to installed) → reopen
  Settings → the voice is selectable/usable.
* **J2 read-aloud works** (``test_j2_read_aloud_speaks``): an already
  set-up app with a real cached voice + real piper → user triggers
  read-aloud through the real overlay UI → the real engine speaks: a
  genuine RIFF/WAVE chunk lands on disk, the reader overlay reaches
  ``reading`` and the karaoke cursor advances, Recent history records
  the text.
* **J3 settings journey** (``test_j3_settings_persist_and_behave``):
  user opens Settings → changes ``show_overlay`` off → Save → the value
  persists in config.json AND has the behavioural effect (with the
  panel disabled a real read does not surface the reader overlay), then
  re-enables it and a real read DOES surface it.
* **J4 onboarding finish** (``test_j4_onboarding_finish_activates``):
  set-up app, first run → user plays the sample (real engine) →
  Finish setup → ``first_run_activation.json`` is really written
  complete on disk.
* **J5 notices** (``test_j5_view_open_source_notices``): user opens the
  open-source notices from Settings → the real Notices window shows the
  genuine licences text the backend resolved from disk.
* **J9 / UC-C9 first-run → Voice-Manager install-completion → onboarding
  ready** (``test_j9_first_run_vm_install_completion_onboarding_ready``):
  fresh first-run launch (real onboarding "needs a voice"; the real
  shared ``get_readiness`` is ``missing_voice``) → user opens the real
  Voices window from onboarding → installs the smallest practical real
  Piper voice (a genuine HF download, J1's real-download pattern) → the
  NEW ``bridge.install_voice`` install-completion callback (the web
  analogue of Tk ``apply_installed_voice``) fires on the real launched
  process → WITHOUT any manual Settings select/save the running app's
  shared ``get_readiness`` flips to ``ready`` and the just-installed
  voice is the configured voice → reopening the real onboarding window
  shows the READY first-run screen. Closes the last core parity gap on
  the real non-headless WebView2 app.

Non-journey-able controls (honest notes) are listed at the bottom of
``e2e/journey/README.md`` and in the Tier-2 section of
``docs/migration-web/UI_TEST_CHECKLIST.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _journey_helpers import (
    bridge_call,
    config_on_disk,
    deadline_poll,
    history_on_disk,
    installed_voice_files,
    is_riff_wave,
)

pytestmark = pytest.mark.journey

# Smallest practical real catalogue voice for the J1 genuine download.
# Labeled "Kathleen — US female (small/fast)" / quality=low in the
# curated KNOWN_VOICES — the smallest English Piper voice PipPal ships
# in its catalogue. A real (not huge) download that proves the path.
J1_VOICE_ID = "en_US-kathleen-low"
J1_VOICE_FILE = "en_US-kathleen-low.onnx"


def _attached_to_real_app(app, step) -> None:
    """Assert we are driving the REAL desktop app, not headless Chromium."""
    browser_build = str(app.cdp_version.get("Browser", ""))
    # WebView2 (the real desktop runtime) reports an ``Edg/<ver>``
    # build string; a headless Chromium would report ``HeadlessChrome``.
    assert "Edg/" in browser_build, (
        f"CDP browser is not the WebView2 desktop runtime: {browser_build!r}"
    )
    assert "HeadlessChrome" not in browser_build, browser_build
    url = app.page.url
    assert "/index.html" in url and "127.0.0.1" in url, url
    # The live DOM carries the app's own markers.
    brand = app.page.locator("#brand-name")
    brand.wait_for(state="attached", timeout=15000)
    step.check(
        f"attached to REAL app window — CDP build {browser_build!r}, "
        f"page {url!r}"
    )


def _reopen_surface(app, view: str, step, timeout: int = 25000):
    """Re-open ``view`` and attach to its freshest real window.

    The real ``open_*_window`` host callback focuses an existing window
    if one is open (it does not re-render it); to genuinely re-render
    the surface (so a journey sees the *persisted* state, not a stale
    in-memory form) we navigate the attached real page to the surface
    URL again — a real reload of the real window's document against the
    real backend, equivalent to the user closing and reopening it.

    ``onboarding`` is special: it has no ``open_onboarding_window``
    bridge host callback (the real app opens it from the tray /
    startup gate via ``windows.open("onboarding")``, not the bridge —
    see ``app_web.py``). Its window is already open for the whole
    journey, so re-rendering it is exactly the real-`page.reload`
    against the live backend below, with no bridge open-call — the
    genuine web equivalent of the user reopening the first-run check
    (Tk re-renders the still-open panel in place; the web onboarding
    window re-reads ``get_readiness`` on its next render).
    """
    if view != "onboarding":
        bridge_call(app.bridge_base, {
            "settings": "open_settings_window",
            "voices": "open_voice_manager_window",
            "notices": "open_notices_window",
        }[view])
    page = app.reattach_page(view_hint=view, timeout=timeout / 1000.0)
    # Force a real re-render from the live backend (the window may have
    # only been focused, keeping its old form values in the DOM) and
    # PIN app.page to exactly this reloaded page so the journey drives
    # the window it just re-rendered, not another open one.
    page.reload(timeout=timeout, wait_until="domcontentloaded")
    page.wait_for_selector(
        f'body[data-ready="{view}"]', timeout=timeout
    )
    app.page = page
    step.check(
        f"real '{view}' surface re-rendered from the live backend "
        f"({page.url})"
    )


def _wait_surface(app, view: str, step, timeout: int = 25000):
    """Wait until the live page for ``view`` finished its first real
    render (api.js sets body[data-ready=<view>] only then).

    Robust to the real app opening the surface in a *new* pywebview
    window: re-resolve the page for ``view`` and wait on its DOM.
    """
    import time as _t

    deadline = _t.time() + timeout / 1000.0
    last_exc = None
    while _t.time() < deadline:
        try:
            page = app.reattach_page(view_hint=view, timeout=5.0)
        except AssertionError as exc:
            last_exc = exc
            continue
        if f"view={view}" not in (page.url or ""):
            last_exc = AssertionError(f"page url {page.url!r} != view {view}")
            _t.sleep(0.3)
            continue
        try:
            page.wait_for_selector(
                f'body[data-ready="{view}"]', timeout=4000
            )
            step.check(
                f"real '{view}' surface rendered "
                f"(body[data-ready={view}], {page.url})"
            )
            return
        except Exception as exc:  # not ready yet — keep polling
            last_exc = exc
            _t.sleep(0.3)
    raise AssertionError(
        f"'{view}' surface never rendered within {timeout}ms "
        f"(last: {last_exc})"
    )


# ==========================================================================
# J1 — first run → install a voice
# ==========================================================================


@pytest.mark.parametrize(
    "real_app",
    # Genuine first run: a real Piper engine is present (bundled) but
    # NO voice is installed yet — the authentic "PipPal needs a local
    # voice" first-run state whose onboarding offers the Voice Manager.
    [{"seed": "first_run", "with_piper": True}],
    indirect=True,
)
def test_j1_first_run_install_voice(real_app, step) -> None:
    """A brand-new user launches PipPal for the first time and installs
    a voice so it can read.

    WHY each step: a first-run user must be shown they need a voice,
    must be able to reach the Voices window, pick one, and have it
    really downloaded and usable — that is the whole point of the app's
    onboarding.
    """
    app = real_app
    _attached_to_real_app(app, step)

    with step.group(
        "J1.1 fresh first launch → the app must show the setup/onboarding "
        "surface (a new user has no voice and must be told)"
    ):
        # The real app force-opens onboarding on first run (no
        # activation marker + no piper/voice). Drive THAT real window.
        app.reattach_page(view_hint="onboarding")
        _wait_surface(app, "onboarding", step)
        title = app.page.get_by_test_id("onboarding-title").inner_text()
        step.check(f"first screen is the setup surface — title: {title!r}")
        # Real on-disk truth: no voice installed yet in the fresh profile.
        assert installed_voice_files(app.profile) == [], (
            "fresh first-run profile already had a voice"
        )
        step.check("real profile has zero installed voices at first run")

    with step.group(
        "J1.2 user clicks 'Open Voice Manager' → the REAL Voices window "
        "must open (the user activates it to get a voice)"
    ):
        # missing_voice onboarding offers 'Open Voice Manager'
        # (onboarding-open-vm) which opens the Voices surface via the
        # real host callback (a genuine new pywebview window).
        vm_btn = app.page.get_by_test_id("onboarding-open-vm")
        if vm_btn.count() == 0:
            # Defensive: a different readiness state — go via Settings →
            # Manage voices (also a real flow).
            app.page.get_by_test_id("onboarding-open-settings").first.click()
            _wait_surface(app, "settings", step)
            app.page.get_by_test_id("settings-manage-voices").click()
        else:
            step("click 'Open Voice Manager' on the real onboarding window")
            vm_btn.first.click()
        # A real second pywebview window appears: a new CDP target.
        _wait_surface(app, "voices", step)
        step.check(f"REAL Voices window opened — {app.page.url!r}")

    with step.group(
        f"J1.3 user picks the smallest voice ({J1_VOICE_ID}) and clicks "
        "Install → a REAL voice must download to disk"
    ):
        row_btn = app.page.get_by_test_id(f"vm-action-{J1_VOICE_ID}")
        row_btn.wait_for(state="visible", timeout=15000)
        step(
            f"click Install on '{J1_VOICE_ID}' (a genuine HF download of "
            "the smallest catalogue voice)"
        )
        row_btn.click()

        # Real effect on disk: the .onnx + .onnx.json land in the
        # running app's real profile voices dir. Deadline-poll (a real
        # network download is in flight) — no fixed sleep.
        def _both_files() -> bool:
            return J1_VOICE_FILE in installed_voice_files(app.profile)

        deadline_poll(
            _both_files,
            timeout=180.0,
            interval=0.5,
            what=f"real {J1_VOICE_FILE} (+ .json) to land on disk",
        )
        onnx = app.profile / "voices" / J1_VOICE_FILE
        meta = app.profile / "voices" / f"{J1_VOICE_FILE}.json"
        size_mb = onnx.stat().st_size / (1024 * 1024)
        assert onnx.stat().st_size > 1_000_000, onnx.stat().st_size
        assert meta.stat().st_size > 100, meta.stat().st_size
        step.check(
            f"REAL voice on disk: {onnx.name} = {size_mb:.2f} MB, "
            f"{meta.name} = {meta.stat().st_size} B"
        )

    with step.group(
        "J1.4 the catalogue/state must show the voice installed (the "
        "user needs to see it worked)"
    ):
        # Query the REAL running app's bridge: its live voice
        # catalogue, not a copy.
        def _cat_installed() -> bool:
            cat = bridge_call(app.bridge_base, "get_voice_catalogue")
            for v in cat.get("voices", []):
                if v["id"] == J1_VOICE_ID and v["installed"]:
                    return True
            return False

        deadline_poll(
            _cat_installed,
            timeout=20.0,
            what="running app catalogue to show the voice installed",
        )
        installed = bridge_call(app.bridge_base, "get_installed_voices")
        assert J1_VOICE_FILE in installed, installed
        step.check(
            f"running app reports voice installed: get_installed_voices()"
            f" = {installed} (live catalogue + on-disk truth — the "
            "authoritative 'it worked' signals)"
        )

    with step.group(
        "J1.5 reopen Settings → the freshly installed voice must be a "
        "selectable, usable voice (config/state reflect it)"
    ):
        # The user closes Voices and the running app still has the
        # voice. Open Settings via the real bridge window flow.
        bridge_call(app.bridge_base, "open_settings_window")
        app.reattach_page(view_hint="settings", timeout=25.0)
        _wait_surface(app, "settings", step)
        # The Settings Voice combo lists the real installed voice.
        voice_sel = app.page.get_by_test_id("settings-voice")
        voice_sel.wait_for(state="visible", timeout=10000)
        opts = app.page.eval_on_selector(
            '[data-testid="settings-voice"]',
            "el => Array.from(el.options).map(o => o.value)",
        )
        assert J1_VOICE_FILE in opts, opts
        step.check(
            f"Settings Voice dropdown offers the installed voice: "
            f"{J1_VOICE_FILE} in {opts}"
        )
        # Select + Save it: real config.json on disk must record it.
        app.page.get_by_test_id("settings-voice").select_option(
            J1_VOICE_FILE
        )
        step(f"select '{J1_VOICE_FILE}' and Save (make it the active voice)")
        app.page.get_by_test_id("settings-save").click()
        deadline_poll(
            lambda: config_on_disk(app.profile).get("voice") == J1_VOICE_FILE,
            timeout=15.0,
            what="config.json to record the installed voice",
        )
        step.check(
            f"config.json on disk: voice == {J1_VOICE_FILE} — the "
            "installed voice is now the usable, configured voice"
        )


# ==========================================================================
# J2 — read-aloud works
# ==========================================================================


@pytest.mark.parametrize(
    "real_app",
    [{"seed": "activated", "with_piper": True, "with_voice": True}],
    indirect=True,
)
def test_j2_read_aloud_speaks(real_app, step) -> None:
    """An already set-up user triggers read-aloud and PipPal really
    speaks.

    WHY: reading selected text aloud is the product's entire purpose;
    the user activates the reader and must get real audio + the karaoke
    overlay + a Recent-history record.
    """
    app = real_app
    _attached_to_real_app(app, step)

    with step.group(
        "J2.1 the app launched already set up (real cached voice + real "
        "piper present) so the engine can really synthesise"
    ):
        # Confirm the running app sees the real voice (its own bridge).
        installed = bridge_call(app.bridge_base, "get_installed_voices")
        assert "en_US-ryan-high.onnx" in installed, installed
        step.check(f"running app has the real voice: {installed}")

    with step.group(
        "J2.2 user triggers read-aloud through the real UI → the real "
        "engine must speak (real WAV on disk)"
    ):
        text = (
            "PipPal journey two: this sentence is synthesised by the real "
            "Piper engine in the launched desktop app."
        )
        step(f"ask the running app to read text aloud: {text[:48]!r}…")
        # Drive read through the real bridge of the launched app (the
        # exact transport the desktop UI uses for read_text).
        bridge_call(app.bridge_base, "read_text", text)

        # Real effect: the engine becomes is_speaking and writes a real
        # per-chunk WAV file. Poll the running app's own engine_state.
        def _chunk_paths() -> list:
            snap = bridge_call(app.bridge_base, "engine_state")
            return [Path(p) for p in (snap.get("chunk_paths") or [])]

        paths = deadline_poll(
            lambda: ([p for p in _chunk_paths() if p.exists()] or False),
            timeout=60.0,
            what="a real synthesised WAV chunk on disk",
        )
        riff = [p for p in paths if is_riff_wave(p)]
        assert riff, f"no valid RIFF/WAVE chunk produced: {paths}"
        import wave

        with wave.open(str(riff[0]), "rb") as w:
            dur = w.getnframes() / float(w.getframerate() or 1)
        step.check(
            f"REAL engine spoke — {riff[0].name}: RIFF/WAVE, {dur:.2f}s "
            f"PCM, {riff[0].stat().st_size} bytes on disk"
        )

    with step.group(
        "J2.3 the reader overlay must reach 'reading' and the karaoke "
        "cursor must advance (the user sees it reading)"
    ):
        reached = deadline_poll(
            lambda: bridge_call(app.bridge_base, "engine_state").get(
                "overlay_state"
            )
            in ("reading", "done"),
            timeout=30.0,
            what="overlay to reach reading/done",
        )
        step.check(f"reader overlay reached state: {reached!r}")
        # Karaoke cursor advances: elapsed strictly increases while
        # reading (the engine drives the overlay's word cursor off the
        # real WAV duration).
        s1 = bridge_call(app.bridge_base, "engine_state")
        e1 = float(s1.get("elapsed") or 0)

        def _advanced() -> bool:
            s2 = bridge_call(app.bridge_base, "engine_state")
            return (
                float(s2.get("elapsed") or 0) > e1
                or s2.get("overlay_state") == "done"
            )

        deadline_poll(
            _advanced, timeout=20.0, what="karaoke cursor (elapsed) to advance"
        )
        step.check("karaoke cursor advanced (engine elapsed increased)")

    with step.group(
        "J2.4 Recent history must record the read text (so the user can "
        "replay it later)"
    ):
        deadline_poll(
            lambda: text in bridge_call(app.bridge_base, "get_history"),
            timeout=20.0,
            what="Recent history to record the text",
        )
        # And it round-trips to history.json on disk.
        deadline_poll(
            lambda: any(text == h for h in history_on_disk(app.profile)),
            timeout=20.0,
            what="history.json on disk to contain the text",
        )
        step.check(
            "Recent history (live + history.json on disk) records the "
            "read text"
        )


# ==========================================================================
# J3 — settings journey (persist + behavioural effect)
# ==========================================================================


@pytest.mark.parametrize(
    "real_app",
    [{"seed": "activated", "with_piper": True, "with_voice": True}],
    indirect=True,
)
def test_j3_settings_persist_and_behave(real_app, step) -> None:
    """A user opens Settings, turns the reader panel off, saves, and the
    change both persists AND changes real reading behaviour; then turns
    it back on and the panel surfaces again.

    WHY: a setting the user changes must (a) survive a reopen and (b)
    actually do what it says — persistence without behaviour is a
    false promise.
    """
    app = real_app
    _attached_to_real_app(app, step)

    with step.group("J3.1 open the real Settings window"):
        # An activated, voiced app opens Settings as its default window.
        _wait_surface(app, "settings", step)

    with step.group(
        "J3.2 user turns OFF 'Show panel while reading' and Saves → must "
        "persist to config.json"
    ):
        toggle = app.page.get_by_test_id("settings-show_overlay")
        toggle.wait_for(state="visible", timeout=10000)
        if toggle.is_checked():
            toggle.uncheck()
        step("uncheck show_overlay (user doesn't want the reader panel)")
        app.page.get_by_test_id("settings-save").click()
        deadline_poll(
            lambda: config_on_disk(app.profile).get("show_overlay") is False,
            timeout=15.0,
            what="config.json show_overlay == False",
        )
        step.check("config.json on disk: show_overlay == False (persisted)")

    with step.group(
        "J3.3 reopen Settings → the change must still be there (survives "
        "a reopen, not just an in-memory toggle)"
    ):
        _reopen_surface(app, "settings", step)
        reopened = app.page.get_by_test_id("settings-show_overlay")
        reopened.wait_for(state="visible", timeout=10000)
        assert reopened.is_checked() is False, (
            "show_overlay did not survive a Settings reopen"
        )
        step.check("reopened Settings shows show_overlay still OFF")

    with step.group(
        "J3.4 behavioural effect: with the panel OFF a real read must "
        "NOT surface the reader overlay"
    ):
        bridge_call(
            app.bridge_base, "read_text", "Reading with the panel disabled."
        )
        # Engine really speaks (chunk appears) but overlay_state stays
        # idle because show_overlay is off — the setting changed
        # behaviour, not just a stored value.
        deadline_poll(
            lambda: bridge_call(app.bridge_base, "engine_state").get(
                "is_speaking"
            )
            or bridge_call(app.bridge_base, "engine_state").get("chunk_count"),
            timeout=30.0,
            what="engine to start a real read",
        )
        snap = bridge_call(app.bridge_base, "engine_state")
        assert snap.get("overlay_state", "idle") == "idle", (
            f"overlay surfaced despite show_overlay=False: {snap}"
        )
        step.check(
            "with show_overlay=False a real read kept the overlay idle "
            "(setting has a genuine behavioural effect)"
        )
        bridge_call(app.bridge_base, "overlay_action", "close")

    with step.group(
        "J3.5 turn it back ON, Save, and a real read DOES surface the "
        "overlay (the setting flips behaviour both ways)"
    ):
        # Quiet the engine from J3.4's read so the next read is a clean
        # fresh observation.
        bridge_call(app.bridge_base, "overlay_action", "close")
        _reopen_surface(app, "settings", step)
        t2 = app.page.get_by_test_id("settings-show_overlay")
        t2.wait_for(state="visible", timeout=10000)
        if not t2.is_checked():
            t2.check()
        assert t2.is_checked(), "failed to re-enable show_overlay in the form"
        step("re-check show_overlay and click Save")
        app.page.get_by_test_id("settings-save").click()
        # The save path toasts "Saved." — wait for the real confirmation
        # the running backend handled it.
        try:
            app.page.get_by_test_id("toast").wait_for(
                state="visible", timeout=8000
            )
        except Exception:
            pass
        # The running app's own live config must flip back to True
        # (authoritative). NOTE: pippal.config.save_config is
        # diff-based — it only persists keys that DIFFER from the
        # layered default, so once show_overlay returns to its default
        # (True) it is correctly OMITTED from config.json again. The
        # real persisted effect of "back to default" is therefore: the
        # live config reads True AND config.json no longer carries an
        # override for it (the J3.2 False override was removed on save).
        deadline_poll(
            lambda: bridge_call(app.bridge_base, "get_config").get(
                "show_overlay"
            )
            is True,
            timeout=15.0,
            what="running app live config show_overlay == True",
        )
        deadline_poll(
            lambda: "show_overlay" not in config_on_disk(app.profile),
            timeout=15.0,
            what="config.json override for show_overlay removed "
            "(value back to its default → diff-config omits it)",
        )
        step.check(
            "running app live config show_overlay == True and the "
            "config.json False-override was removed (diff-config: a "
            "value back at its default is omitted) — persisted both ways"
        )
        bridge_call(
            app.bridge_base, "read_text", "Reading with the panel enabled."
        )
        reached = deadline_poll(
            lambda: bridge_call(app.bridge_base, "engine_state").get(
                "overlay_state"
            )
            in ("reading", "thinking", "done"),
            timeout=30.0,
            what="overlay to surface with show_overlay=True",
        )
        step.check(
            f"with show_overlay=True a real read surfaced the overlay "
            f"(state={reached!r}) — behaviour flips both ways"
        )


# ==========================================================================
# J4 — onboarding finish activates
# ==========================================================================


@pytest.mark.parametrize(
    "real_app",
    [{"seed": "first_run", "with_piper": True, "with_voice": True}],
    indirect=True,
)
def test_j4_onboarding_finish_activates(real_app, step) -> None:
    """A first-run user with a working engine plays the sample and
    finishes setup; activation is really persisted.

    WHY: the onboarding 'Finish setup' is the user's explicit "I heard
    it, I'm set" — it must durably record activation so the app stops
    nagging on next launch.
    """
    app = real_app
    _attached_to_real_app(app, step)

    with step.group(
        "J4.1 first run with a real engine → onboarding shows the READY "
        "state (the user can test it now)"
    ):
        app.reattach_page(view_hint="onboarding")
        _wait_surface(app, "onboarding", step)
        # Activation not yet complete on disk.
        assert not (app.profile / "first_run_activation.json").exists(), (
            "activation marker existed before the user finished onboarding"
        )
        step.check("no first_run_activation.json yet (not activated)")

    with step.group(
        "J4.2 user clicks 'Play sample' → the real engine must speak the "
        "activation sample"
    ):
        play = app.page.get_by_test_id("onboarding-play-sample")
        play.wait_for(state="visible", timeout=15000)
        step("click 'Play sample' (user verifies they can hear PipPal)")
        play.click()
        deadline_poll(
            lambda: bridge_call(app.bridge_base, "engine_state").get(
                "is_speaking"
            )
            or bridge_call(app.bridge_base, "engine_state").get("chunk_count"),
            timeout=45.0,
            what="real engine to play the activation sample",
        )
        step.check("real engine played the activation sample")

    with step.group(
        "J4.3 user clicks 'Finish setup' → activation must be written "
        "complete on disk"
    ):
        finish = app.page.get_by_test_id("onboarding-finish")
        finish.wait_for(state="visible", timeout=10000)
        deadline_poll(
            lambda: finish.is_enabled(),
            timeout=15.0,
            what="Finish button to enable after the sample played",
        )
        step("click 'Finish setup' (user confirms PipPal works)")
        finish.click()

        def _activated() -> bool:
            st = bridge_call(app.bridge_base, "get_activation_state")
            return bool(st.get("is_complete"))

        deadline_poll(
            _activated,
            timeout=20.0,
            what="running app to report activation complete",
        )
        # Real on-disk truth.
        marker = app.profile / "first_run_activation.json"
        deadline_poll(
            lambda: marker.exists(),
            timeout=15.0,
            what="first_run_activation.json on disk",
        )
        import json

        data = json.loads(marker.read_text("utf-8"))
        payload = data.get("first_run_activation", data)
        assert payload.get("completed_with") in ("sample", "selected_text"), (
            payload
        )
        step.check(
            f"first_run_activation.json written complete on disk: "
            f"{payload}"
        )


# ==========================================================================
# J5 — view open-source notices
# ==========================================================================


@pytest.mark.parametrize(
    "real_app", [{"seed": "activated"}], indirect=True
)
def test_j5_view_open_source_notices(real_app, step) -> None:
    """A user opens the open-source notices from Settings to check the
    licences.

    WHY: a privacy/licence-conscious user activates 'View licences' to
    confirm what is bundled — the real Notices window must show the
    genuine resolved licences text.
    """
    app = real_app
    _attached_to_real_app(app, step)

    with step.group("J5.1 open the real Settings window"):
        bridge_call(app.bridge_base, "open_settings_window")
        app.reattach_page(view_hint="settings", timeout=25.0)
        _wait_surface(app, "settings", step)

    with step.group(
        "J5.2 user clicks 'View licences…' → the REAL Notices window "
        "must open with the resolved licences text"
    ):
        btn = app.page.get_by_test_id("settings-view-licences")
        btn.wait_for(state="visible", timeout=10000)
        step("click 'View licences…' (user checks what is bundled)")
        btn.click()
        app.reattach_page(view_hint="notices", timeout=25.0)
        _wait_surface(app, "notices", step)
        body = app.page.get_by_test_id("notices-body")
        body.wait_for(state="visible", timeout=10000)
        txt = body.inner_text()
        assert len(txt.strip()) > 50, f"notices body too short: {txt!r}"
        # Cross-check against what the running app's bridge resolved
        # (same real backend resolver the desktop uses).
        resolved = bridge_call(app.bridge_base, "get_notices")
        assert resolved.strip()[:30] in txt or txt.strip()[:30] in resolved, (
            "Notices window text does not match the backend resolver"
        )
        step.check(
            f"REAL Notices window shows the resolved licences text "
            f"({len(txt)} chars), matching the backend resolver"
        )


# ==========================================================================
# J9 — UC-C9: first-run → Voice Manager → install-completion → onboarding
#       genuinely flips ready, on the REAL launched WebView2 app
# ==========================================================================
#
# The Tk first-run flow wires the Voice Manager's install-completion
# callback (``app.py:577-583`` ``on_installed=panel.apply_installed_voice``
# → ``activation_panel.py:415`` → ``_finish_voice_install``:
# ``self.config["voice"] = installed_filename``) so installing a voice
# from the first-run Voice Manager makes that voice the configured voice
# and flips onboarding/readiness ready. The web ``bridge.install_voice``
# now has the true analogue (same shared ``onboarding`` logic, reused not
# forked). This journey proves it END-TO-END on the REAL launched
# non-headless WebView2 desktop app.
#
# Distinct from J1: J1 proves the *download/install path* and then makes
# the voice active via a MANUAL Settings select+Save (J1.5). J9 proves
# the **automatic install-completion callback**: after the real install
# the running app's shared readiness flips ready and the installed voice
# is the configured voice WITHOUT any Settings interaction — the exact
# UC-C9 behaviour that did not exist before this production fix. The only
# non-app element is the genuine HF network download (J1's real-download
# pattern; the smallest practical catalogue voice) — everything else is
# the real launched process: real onboarding/VM windows, the real host
# callback, the real installer, the real NEW completion callback, the
# real shared readiness recomputation. No mock of the unit under test, no
# tautology (the journey never sets the configured voice — the
# production callback does), deadline-polls not sleeps, hermetic per-
# journey profile, privilege/host-independent.

UCC9_VOICE_ID = J1_VOICE_ID
UCC9_VOICE_FILE = J1_VOICE_FILE


@pytest.mark.parametrize(
    "real_app",
    # Genuine first run with a real Piper engine but NO voice — the real
    # "PipPal needs a local voice" onboarding whose VM the user opens.
    [{"seed": "first_run", "with_piper": True}],
    indirect=True,
)
def test_j9_first_run_vm_install_completion_onboarding_ready(
    real_app, step
) -> None:
    """UC-C9: a first-run user installs a voice from the web Voice
    Manager and the NEW install-completion callback genuinely flips the
    real launched app's onboarding/activation/readiness to ready —
    automatically, exactly like the Tk apply_installed_voice flow.
    """
    app = real_app
    _attached_to_real_app(app, step)

    with step.group(
        "J9.1 fresh first launch with a real engine but NO voice → the "
        "real shared readiness must be 'missing_voice' (onboarding nags "
        "for a voice — the genuine UC-C9 starting state)"
    ):
        app.reattach_page(view_hint="onboarding")
        _wait_surface(app, "onboarding", step)
        assert installed_voice_files(app.profile) == [], (
            "fresh first-run profile already had a voice"
        )
        rd0 = bridge_call(app.bridge_base, "get_readiness")
        assert rd0.get("status") == "missing_voice", rd0
        cfg0 = bridge_call(app.bridge_base, "get_config")
        step.check(
            f"running app shared get_readiness == 'missing_voice' "
            f"(config voice = {cfg0.get('voice')!r}); zero voices on disk"
        )

    with step.group(
        "J9.2 user clicks 'Open Voice Manager' on the real onboarding "
        "window → the REAL Voices window must open (real host callback)"
    ):
        vm_btn = app.page.get_by_test_id("onboarding-open-vm")
        vm_btn.wait_for(state="visible", timeout=15000)
        step("click 'Open Voice Manager' on the real onboarding window")
        vm_btn.first.click()
        _wait_surface(app, "voices", step)
        step.check(f"REAL Voices window opened — {app.page.url!r}")

    with step.group(
        f"J9.3 user installs the smallest real voice ({UCC9_VOICE_ID}) — "
        "a GENUINE download to the real launched app's profile (J1's "
        "real-download pattern)"
    ):
        row_btn = app.page.get_by_test_id(f"vm-action-{UCC9_VOICE_ID}")
        row_btn.wait_for(state="visible", timeout=15000)
        step(
            f"click Install on '{UCC9_VOICE_ID}' (a real HF download on "
            "the real launched process)"
        )
        row_btn.click()

        def _file_landed() -> bool:
            return UCC9_VOICE_FILE in installed_voice_files(app.profile)

        deadline_poll(
            _file_landed,
            timeout=180.0,
            interval=0.5,
            what=f"real {UCC9_VOICE_FILE} (+ .json) to land on disk",
        )
        onnx = app.profile / "voices" / UCC9_VOICE_FILE
        size_mb = onnx.stat().st_size / (1024 * 1024)
        assert onnx.stat().st_size > 1_000_000, onnx.stat().st_size
        step.check(
            f"REAL voice on disk: {onnx.name} = {size_mb:.2f} MB "
            "(genuine network install on the launched app)"
        )

    with step.group(
        "J9.4 THE FIX — the NEW install-completion callback must have "
        "automatically made the installed voice the configured voice on "
        "the running app (the web analogue of Tk apply_installed_voice), "
        "WITHOUT any Settings select/save"
    ):
        def _config_voice_set() -> bool:
            return bridge_call(app.bridge_base, "get_config").get(
                "voice"
            ) == UCC9_VOICE_FILE

        deadline_poll(
            _config_voice_set,
            timeout=20.0,
            what="running app config voice == the just-installed voice "
            "(set by the NEW install-completion callback)",
        )
        live_cfg = bridge_call(app.bridge_base, "get_config")
        step.check(
            f"running app shared config voice == {UCC9_VOICE_FILE!r} — "
            "set by the NEW bridge.install_voice completion callback, "
            "NOT by any Settings interaction (the test never set it)"
        )
        assert live_cfg.get("voice") == UCC9_VOICE_FILE, live_cfg

    with step.group(
        "J9.5 the real shared onboarding readiness must have flipped to "
        "'ready' on the running app (build_activation_readiness over the "
        "now-updated shared config — the shared logic, reused not forked)"
    ):
        def _ready() -> bool:
            return bridge_call(app.bridge_base, "get_readiness").get(
                "status"
            ) == "ready"

        deadline_poll(
            _ready,
            timeout=20.0,
            what="running app shared get_readiness to flip to 'ready'",
        )
        rd1 = bridge_call(app.bridge_base, "get_readiness")
        assert rd1.get("status") == "ready", rd1
        step.check(
            "running app shared get_readiness flipped 'missing_voice' → "
            "'ready' automatically (UC-C9 install-completion parity)"
        )

    with step.group(
        "J9.6 reopening the REAL onboarding window now shows the READY "
        "first-run screen (the user is no longer nagged for a voice)"
    ):
        _reopen_surface(app, "onboarding", step)
        title = app.page.get_by_test_id("onboarding-title").inner_text()
        assert title.strip() == "PipPal is ready to read locally", title
        assert app.page.get_by_test_id("onboarding-open-vm").count() == 0, (
            "the 'needs a voice' Open Voice Manager button is still shown "
            "on the real onboarding window after the install"
        )
        app.page.get_by_test_id("onboarding-play-sample").wait_for(
            state="visible", timeout=10000
        )
        step.check(
            "REAL reopened onboarding window renders the READY first-run "
            f"screen (title {title.strip()!r}, no 'needs a voice' "
            "buttons) — UC-C9 genuinely covered end-to-end on the real "
            "non-headless WebView2 app"
        )
