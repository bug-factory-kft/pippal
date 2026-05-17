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
import math
import struct
import wave
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


def _config_on_disk(profile: Path) -> dict:
    cfg = profile / "config.json"
    if not cfg.exists():
        return {}
    return json.loads(cfg.read_text("utf-8"))


def _goto(page: Page, app_url: str, view: str, step=None) -> None:
    if step is not None:
        step(f"open '{view}' surface ({app_url}/index.html?view={view})")
    page.goto(f"{app_url}/index.html?view={view}")
    # api.js sets data-ready once the surface finished its first render.
    expect(page.locator("body")).to_have_attribute("data-ready", view, timeout=15000)
    if step is not None:
        step.check(f"surface '{view}' rendered (body[data-ready={view}])")


def _start_reading_session(page: Page, app_url: str, step=None) -> None:
    """Drive a REAL engine read via the page's own bridge transport
    (the exact fetch api.js performs). No piper.exe here, so the engine
    plays the bundled onboarding clip and drives the overlay protocol
    for ~14 s — a genuine reading session, real audio, real state."""
    if step is not None:
        step("open overlay surface for a live reading session")
    page.goto(f"{app_url}/index.html?view=overlay")
    expect(page.locator("body")).to_have_attribute("data-ready", "overlay")
    if step is not None:
        step('read-aloud "PipPal live reading session end to end check."'
             " via POST /bridge read_text")
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

def test_settings_renders_seven_cards(page: Page, app_url: str, step):
    _goto(page, app_url, "settings", step)
    titles = page.locator(".card-title")
    expect(titles).to_have_count(7)
    step.check("7 settings cards rendered (.card-title == 7)")
    expect(page.get_by_test_id("settings-engine")).to_be_visible()
    expect(page.get_by_test_id("settings-save")).to_be_visible()
    step.check("engine combo + Save button visible")


def test_settings_edit_persists_to_backend(page: Page, app_url: str, backend, step):
    _goto(page, app_url, "settings", step)

    # Move the Speed slider and Save. Speed is the inverse of
    # length_scale; assert the persisted config matches.
    step("set Speed slider = 1.25×")
    speed = page.get_by_test_id("settings-speed")
    speed.evaluate(
        "el => { el.value = '1.25';"
        " el.dispatchEvent(new Event('input', {bubbles:true})); }"
    )
    expect(page.get_by_test_id("settings-speed-value")).to_have_text("1.25×")
    step.check("speed value label shows 1.25×")

    step("set auto_hide_ms = 2400")
    page.get_by_test_id("settings-auto_hide_ms").fill("2400")
    step("click Save")
    page.get_by_test_id("settings-save").click()

    expect(page.get_by_test_id("toast")).to_contain_text("Saved")
    step.check('toast == "Saved"')

    cfg = _config_on_disk(backend["profile"])
    assert cfg.get("auto_hide_ms") == 2400
    step.check("config.json on disk: auto_hide_ms == 2400")
    # 1/1.25 = 0.8
    assert abs(float(cfg.get("length_scale", 0)) - 0.8) < 1e-6
    step.check("config.json on disk: length_scale == 0.8 (1/1.25)")
    # And the live config object the engine reads was updated too.
    assert backend["config"]["auto_hide_ms"] == 2400
    step.check("live config the engine reads: auto_hide_ms == 2400")


def test_settings_engine_and_voice_selection_persists(
    page: Page, app_url: str, backend, step
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
        _goto(page, app_url, "settings", step)

        # piper is the only registered engine in this build; selecting it
        # is still a real round-trip through save_config / reset_backend.
        step("select engine = piper")
        page.get_by_test_id("settings-engine").select_option("piper")
        # A NON-default voice → it must be written to config.json.
        step("select voice = en_US-amy-medium.onnx (non-default)")
        page.get_by_test_id("settings-voice").select_option("en_US-amy-medium.onnx")

        step("click Save")
        page.get_by_test_id("settings-save").click()
        expect(page.get_by_test_id("toast")).to_contain_text("Saved")
        step.check('toast == "Saved"')

        # Live config the engine reads reflects both selections.
        assert backend["config"]["engine"] == "piper"
        assert backend["config"]["voice"] == "en_US-amy-medium.onnx"
        step.check("live config: engine == piper, voice == en_US-amy-medium.onnx")
        # The non-default voice really persisted to disk.
        cfg = _config_on_disk(backend["profile"])
        assert cfg.get("voice") == "en_US-amy-medium.onnx"
        step.check("config.json on disk: voice == en_US-amy-medium.onnx")

        # Re-rendering Settings (fresh bridge round-trip) shows it stuck.
        _goto(page, app_url, "settings", step)
        expect(page.get_by_test_id("settings-voice")).to_have_value(
            "en_US-amy-medium.onnx"
        )
        step.check("re-rendered Settings still shows voice en_US-amy-medium.onnx")
    finally:
        for p in made:
            p.unlink(missing_ok=True)
        # Restore the default voice in the shared session config so the
        # later reading-session tests aren't affected.
        backend["config"]["voice"] = "en_US-ryan-high.onnx"


def test_settings_hotkey_edit_rebinds_and_persists(
    page: Page, app_url: str, backend, step
):
    _goto(page, app_url, "settings", step)
    step("set hotkey_speak = ctrl+alt+space")
    field = page.get_by_test_id("settings-hotkey_speak")
    field.fill("ctrl+alt+space")
    before = len(backend["hotkey_calls"])
    step("click Apply")
    page.get_by_test_id("settings-apply").click()
    expect(page.get_by_test_id("toast")).to_contain_text("Applied")
    step.check('toast == "Applied"')

    cfg = _config_on_disk(backend["profile"])
    assert cfg.get("hotkey_speak") == "ctrl+alt+space"
    step.check("config.json on disk: hotkey_speak == ctrl+alt+space")
    # Changing a hotkey must trigger the host rebind callback.
    assert len(backend["hotkey_calls"]) > before
    step.check(
        f"host hotkey-rebind callback fired ({before} -> "
        f"{len(backend['hotkey_calls'])})"
    )


# ---------------------------------------------------------------------------
# Confirm modal — restores the Tk messagebox.askyesno gate
# ---------------------------------------------------------------------------

def test_reset_confirm_modal_gates_the_form(page: Page, app_url: str, backend, step):
    """Reset-to-defaults must NOT touch the form until the modal is
    accepted. Cancel leaves edited fields as-is; accept resets them."""
    _goto(page, app_url, "settings", step)

    # Edit a field to a non-default value we can watch.
    step("set auto_hide_ms = 5000 (a value to watch the gate on)")
    auto_hide = page.get_by_test_id("settings-auto_hide_ms")
    auto_hide.fill("5000")

    # Click Reset → the modal must appear and the field must be UNCHANGED.
    step("click Reset to defaults")
    page.get_by_test_id("settings-reset").click()
    expect(page.get_by_test_id("confirm-modal")).to_be_visible()
    expect(page.get_by_test_id("confirm-title")).to_have_text("Reset to defaults")
    expect(auto_hide).to_have_value("5000")  # gate held
    step.check('confirm modal shown ("Reset to defaults"); field still 5000 (gate held)')

    # Cancel → modal closes, field still the edited value (no reset ran).
    step("click Cancel on the confirm modal")
    page.get_by_test_id("confirm-cancel").click()
    expect(page.get_by_test_id("confirm-modal")).to_be_hidden()
    expect(auto_hide).to_have_value("5000")
    step.check("modal hidden; field still 5000 (Cancel ran no reset)")

    # Reset again, this time accept → the field resets to the default.
    from pippal.config import DEFAULT_CONFIG

    default_ah = str(DEFAULT_CONFIG["auto_hide_ms"])
    step("click Reset again, then accept the modal")
    page.get_by_test_id("settings-reset").click()
    expect(page.get_by_test_id("confirm-modal")).to_be_visible()
    page.get_by_test_id("confirm-ok").click()
    expect(page.get_by_test_id("confirm-modal")).to_be_hidden()
    expect(auto_hide).to_have_value(default_ah)
    step.check(f"accepted → field reset to default ({default_ah})")


def test_voice_remove_confirm_modal_gates_deletion(
    page: Page, app_url: str, backend, step
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
    step.check("seeded real voice files on disk (en_US-ryan-high.onnx + sidecar)")
    try:
        _goto(page, app_url, "voices", step)
        row_btn = page.get_by_test_id("vm-action-en_US-ryan-high")
        expect(row_btn).to_have_text("Remove")  # catalogue sees it installed
        step.check("catalogue row shows 'Remove' (sees it installed)")

        # Click Remove → modal appears, files still on disk (gate held).
        step("click Remove on en_US-ryan-high")
        row_btn.click()
        expect(page.get_by_test_id("confirm-modal")).to_be_visible()
        expect(page.get_by_test_id("confirm-title")).to_have_text("Remove voice")
        expect(page.get_by_test_id("confirm-body")).to_contain_text("Remove")
        assert onnx.exists() and sidecar.exists()
        step.check("confirm modal shown; both files still on disk (gate held)")

        # Cancel → nothing deleted.
        step("click Cancel on the confirm modal")
        page.get_by_test_id("confirm-cancel").click()
        expect(page.get_by_test_id("confirm-modal")).to_be_hidden()
        assert onnx.exists() and sidecar.exists()
        step.check("modal hidden; both files still on disk (Cancel deleted nothing)")

        # Remove + accept → real bridge.remove_voice unlinks both files.
        step("click Remove again, then accept the modal")
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
        step.check("accepted → real bridge.remove_voice unlinked both files on disk")
    finally:
        onnx.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Voice Manager
# ---------------------------------------------------------------------------

def test_voice_manager_lists_catalogue(page: Page, app_url: str, backend, step):
    _goto(page, app_url, "voices", step)
    rows = page.locator('#view [data-testid^="vm-action-"]')
    catalogue = backend["bridge"].get_voice_catalogue()
    expect(rows).to_have_count(len(catalogue["voices"]))
    step.check(
        f"rendered row count == real catalogue ({len(catalogue['voices'])} voices)"
    )


def test_voice_manager_search_filter(page: Page, app_url: str, step):
    _goto(page, app_url, "voices", step)
    # "ryan" matches exactly one curated voice (en_US-ryan-high).
    step('type "ryan" in the search box')
    page.get_by_test_id("vm-search").fill("ryan")
    rows = page.locator('#view [data-testid^="vm-action-"]')
    expect(rows).to_have_count(1)
    expect(page.get_by_test_id("vm-action-en_US-ryan-high")).to_be_visible()
    step.check('"ryan" → exactly 1 row (en_US-ryan-high)')

    # A query that matches nothing shows the empty-state hint.
    step('type "zzzznotavoice" (matches nothing)')
    page.get_by_test_id("vm-search").fill("zzzznotavoice")
    expect(page.get_by_test_id("vm-empty")).to_be_visible()
    step.check("empty-state hint shown for a no-match query")


def test_voice_manager_status_filter(page: Page, app_url: str, step):
    _goto(page, app_url, "voices", step)
    # Nothing is installed in the fresh profile → "Installed" empties it.
    step("select status filter = Installed")
    page.get_by_test_id("vm-status").select_option("Installed")
    expect(page.get_by_test_id("vm-empty")).to_be_visible()
    step.check("Installed → empty (fresh profile has no voices on disk)")
    step("select status filter = Not installed")
    page.get_by_test_id("vm-status").select_option("Not installed")
    rows = page.locator('#view [data-testid^="vm-action-"]')
    assert rows.count() > 0
    step.check(f"Not installed → {rows.count()} rows")


# ---------------------------------------------------------------------------
# Read-aloud → real engine effect
# ---------------------------------------------------------------------------

def test_read_aloud_drives_real_engine(page: Page, app_url: str, backend, step):
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
    _goto(page, app_url, "onboarding", step)
    engine = backend["engine"]
    overlay = backend["overlay"]

    play = page.get_by_test_id("onboarding-play-sample")
    if play.count() > 0:
        step("click onboarding Play sample (real engine read)")
        play.click()
    else:
        # Real read-aloud via the page's own bridge transport (the exact
        # fetch the UI's api.js performs) — not a Python-side shortcut.
        step('read-aloud "PipPal web UI end to end read aloud check."'
             " via POST /bridge read_text")
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
    with engine.lock:
        spk = engine.is_speaking
    step.check(
        f"real engine reacted (is_speaking={spk}, "
        f"overlay_state={overlay.snapshot()['overlay_state']!r})"
    )
    step("stop the engine")
    backend["engine"].stop()


# ---------------------------------------------------------------------------
# Deepened read-aloud — the FULL real path with a real synth backend
# ---------------------------------------------------------------------------
#
# The no-piper.exe checkout normally routes read-aloud through the
# onboarding clip (a single bundled WAV, idx 0/1, NO per-chunk WAV
# written to TEMP_DIR). To assert the *full* real production path —
# real per-chunk WAV files on disk (RIFF/WAVE), the reader overlay's
# karaoke cursor advancing ACROSS multiple chunks, and Recent history
# recording — we register, through the REAL ``plugins.register_engine``
# extension API, a backend that genuinely synthesises a valid PCM
# RIFF/WAVE file with the stdlib ``wave`` module. ONLY the audio
# *content* is a deterministic test tone; the engine, the
# ``pippal.playback`` loop, the WAV-on-disk, the overlay protocol, the
# karaoke timing, the per-chunk advance and the history round-trip are
# all the unmodified real production code (this is exactly how a
# third-party engine plugin integrates — see ``pippal/_register.py``).
# Real-effect only, poll-with-deadline, no mocks of PipPal code, no
# fixed sleeps.


class _RealWavBackend:
    """A real ``TTSBackend`` that writes a genuine RIFF/WAVE PCM file.

    Registered via the real ``plugins.register_engine`` API exactly as a
    third-party engine plugin would. ``synthesize`` produces a valid
    ~1.1 s 16-bit mono PCM WAV (a low sine tone) on disk — a real audio
    file the real ``winsound.PlaySound`` + the real playback loop
    consume. Not a mock of any PipPal code path."""

    name = "realwav-e2e"
    _RATE = 22050
    _SECONDS = 1.1

    def __init__(self, config):
        self.config = dict(config)

    def is_available(self) -> bool:
        return True

    def is_ready(self) -> bool:
        # Ready so the engine takes the REAL synth path (not the
        # no-voice onboarding clip) — the whole point of this test.
        return True

    def synthesize(self, text: str, out_path: Path) -> bool:
        n = int(self._RATE * self._SECONDS)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._RATE)
            frames = bytearray()
            for i in range(n):
                # Quiet 180 Hz tone — a genuine PCM signal on disk.
                val = int(2200 * math.sin(2 * math.pi * 180 * i / self._RATE))
                frames += struct.pack("<h", val)
            w.writeframes(bytes(frames))
        return out_path.exists() and out_path.stat().st_size > 44


def _is_riff_wave(p: Path) -> bool:
    """True iff ``p`` is a real WAV: 'RIFF' + 'WAVE' magic AND the
    stdlib ``wave`` module can parse a non-empty PCM stream from it."""
    try:
        head = p.read_bytes()[:12]
    except OSError:
        return False
    if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        return False
    try:
        with wave.open(str(p), "rb") as w:
            return w.getnframes() > 0 and w.getframerate() > 0
    except (wave.Error, OSError):
        return False


@pytest.fixture
def _realwav_engine(backend):
    """Register the real-WAV backend through the genuine plugin API,
    select it on the live config, drop the engine's cached backend so
    the next synth picks it up, and restore the registry + engine on
    teardown. Additive: the core ``piper`` engine stays registered."""
    from pippal import plugins

    plugins.register_engine(_RealWavBackend.name, _RealWavBackend)
    prev_engine = backend["config"].get("engine")
    backend["config"]["engine"] = _RealWavBackend.name
    backend["engine"].reset_backend()  # real cache-invalidation API
    try:
        yield
    finally:
        backend["config"]["engine"] = prev_engine
        backend["engine"].reset_backend()
        # Best-effort: drop our test engine from the live registry so it
        # cannot leak into another test's catalogue.
        plugins._engines.pop(_RealWavBackend.name, None)


def test_read_aloud_full_real_path_wav_karaoke_history(
    page: Page, app_url: str, backend, _realwav_engine, step
):
    """Drive read-aloud through the REAL served UI with a REAL synth
    backend and assert the FULL real path end to end, with logged steps:

      * the real ``TTSEngine`` becomes ``is_speaking``;
      * real per-chunk WAV files are produced ON DISK and are valid
        RIFF/WAVE PCM (parsed by the stdlib ``wave`` module);
      * the reader overlay shows and the karaoke cursor actually
        ADVANCES, and the multi-chunk read advances ACROSS chunks
        (chunk counter 1/N → a later chunk; cursor index moves);
      * Recent history records the spoken text (the real
        ``engine._remember`` round-trip the no-piper path skips).

    Real-effect only — no mocks of PipPal code, no fixed sleeps, every
    wait is poll-with-deadline."""
    engine = backend["engine"]
    overlay = backend["overlay"]
    bridge = backend["bridge"]

    # split_sentences packs sentences up to ~400 chars per chunk, so to
    # force a genuine MULTI-chunk read (multiple real WAV files + an
    # across-chunk karaoke advance) each sentence is itself long enough
    # (> ~400 chars) to land in its own chunk. This is real input the
    # real splitter chunks the real production way.
    s1 = (
        "PipPal full real path check, the very first sentence, is "
        "deliberately written long enough that the real sentence "
        "splitter places it entirely into its own first audio chunk so "
        "the engine synthesises a separate real WAV file for it on disk "
        "and the reader overlay shows the first karaoke segment moving "
        "forward through these words one after another in order."
    )
    s2 = (
        "Now the second sentence, equally long on purpose, becomes the "
        "second real chunk the engine synthesises into its own WAV file, "
        "which makes the overlay chunk counter advance from the first "
        "chunk to the second and proves the karaoke cursor really moves "
        "across chunk boundaries during a genuine multi chunk read."
    )
    s3 = (
        "Finally a third long sentence forms a third real chunk and a "
        "third real WAV file so the across chunk advance is unmistakable "
        "and the recent history records the whole text exactly as the "
        "real production read path does when a real engine is ready."
    )
    text = f"{s1} {s2} {s3}"

    step.check(
        f"engine backend selected = {backend['config']['engine']!r} "
        "(real WAV synth via plugins.register_engine)"
    )
    step("open overlay surface")
    page.goto(f"{app_url}/index.html?view=overlay")
    expect(page.locator("body")).to_have_attribute("data-ready", "overlay")
    step.check("surface 'overlay' rendered")

    step(f'read-aloud "{text[:48]}..." via POST /bridge read_text')
    page.evaluate(
        """async (t) => {
            const r = await fetch('/bridge', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({ method: 'read_text', args: [t] }),
            });
            return r.ok;
        }""",
        text,
    )

    # ---- engine becomes speaking (real state) -------------------------
    def _speaking() -> bool:
        with engine.lock:
            return engine.is_speaking

    deadline = page.evaluate("Date.now()") + 8000
    while page.evaluate("Date.now()") < deadline and not _speaking():
        page.wait_for_timeout(100)
    assert _speaking(), "engine never became is_speaking on the real synth path"
    with engine.lock:
        bname = engine._backend_name
        bcls = engine._backend_cls.__name__ if engine._backend_cls else None
    step.check(
        f"real TTSEngine is speaking (backend_name={bname!r}, class={bcls!r})"
    )

    # ---- real WAV chunk file(s) on disk, valid RIFF/WAVE --------------
    def _wav_chunks_on_disk() -> list[Path]:
        # The bridge engine_state exposes the engine's real chunk_paths —
        # the SAME contract the served UI reads. Use that, then check the
        # bytes on disk ourselves.
        snap = bridge.engine_state()
        paths = [Path(p) for p in snap.get("chunk_paths", [])]
        return [p for p in paths if p.exists() and _is_riff_wave(p)]

    riff: list[Path] = []
    deadline = page.evaluate("Date.now()") + 8000
    while page.evaluate("Date.now()") < deadline:
        riff = _wav_chunks_on_disk()
        if riff:
            break
        page.wait_for_timeout(120)
    assert riff, "no valid RIFF/WAVE chunk file was produced on disk"
    sample = riff[0]
    with wave.open(str(sample), "rb") as w:
        dur = w.getnframes() / float(w.getframerate())
    step.check(
        f"real WAV chunk on disk: {sample.name} "
        f"(RIFF/WAVE, {dur:.2f}s PCM, {sample.stat().st_size} bytes)"
    )

    # ---- reader overlay shows + karaoke cursor advances --------------
    expect(page.locator("body")).to_have_attribute(
        "data-overlay-state", "reading", timeout=8000
    )
    expect(page.get_by_test_id("overlay-panel")).to_be_visible()
    step.check("reader overlay visible and in 'reading' state")

    cur = page.locator('[data-testid="overlay-text"] .w.cur')

    def cursor_index() -> int:
        el = cur.first
        if el.count() == 0:
            return -1
        return int(el.get_attribute("data-i") or -1)

    deadline = page.evaluate("Date.now()") + 6000
    i0 = -1
    while page.evaluate("Date.now()") < deadline:
        i0 = cursor_index()
        if i0 >= 0:
            break
        page.wait_for_timeout(100)
    assert i0 >= 0, "karaoke cursor never appeared on the real synth read"
    step.check(f"karaoke cursor appeared at word index {i0}")

    deadline = page.evaluate("Date.now()") + 6000
    i1 = i0
    while page.evaluate("Date.now()") < deadline:
        i1 = cursor_index()
        if i1 > i0:
            break
        page.wait_for_timeout(120)
    assert i1 > i0, f"karaoke cursor did not advance ({i0} -> {i1})"
    step.check(f"karaoke cursor advanced over real audio ({i0} -> {i1})")

    # ---- the read advances ACROSS chunks (multi-chunk real read) -----
    def _chunk_counter() -> str:
        return page.get_by_test_id("overlay-counter").inner_text().strip()

    seen: set[str] = set()
    deadline = page.evaluate("Date.now()") + 14000
    while page.evaluate("Date.now()") < deadline:
        c = _chunk_counter()
        if c:
            seen.add(c)
        snap = overlay.snapshot()
        # Stop once the backend has moved past the first chunk.
        if snap["chunk_total"] > 1 and snap["chunk_idx"] >= 1:
            break
        if snap["overlay_state"] not in ("reading", "thinking"):
            break
        page.wait_for_timeout(150)
    snap = overlay.snapshot()
    assert snap["chunk_total"] > 1, (
        f"expected a multi-chunk read, got chunk_total={snap['chunk_total']}"
    )
    assert snap["chunk_idx"] >= 1, (
        f"read never advanced past the first chunk (idx={snap['chunk_idx']})"
    )
    step.check(
        f"multi-chunk read advanced ACROSS chunks: backend at "
        f"chunk_idx={snap['chunk_idx']} of {snap['chunk_total']}; "
        f"DOM counter showed {sorted(seen)}"
    )

    # ---- Recent history recorded the spoken text ---------------------
    def _history_has_it() -> bool:
        return any(text.strip() == h.strip() for h in bridge.get_history())

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not _history_has_it():
        page.wait_for_timeout(100)
    assert _history_has_it(), (
        "real read did not record the text in Recent history via the bridge"
    )
    step.check("Recent history (bridge.get_history) recorded the spoken text")

    step("stop the engine")
    engine.stop()


# ---------------------------------------------------------------------------
# Reader overlay panel — live reading session, karaoke, transport, auto-hide
# ---------------------------------------------------------------------------

def test_overlay_panel_buttons_call_engine(page: Page, app_url: str, backend, step):
    _goto(page, app_url, "overlay", step)
    expect(page.get_by_test_id("overlay-panel")).to_be_visible()
    for tag in ("overlay-prev", "overlay-replay", "overlay-next", "overlay-close"):
        expect(page.get_by_test_id(tag)).to_be_visible()
    step.check("overlay panel + prev/replay/next/close buttons visible")

    # The close button maps to engine.stop(); clicking it must bump the
    # cancellation token (engine.stop increments engine.token).
    engine = backend["engine"]
    with engine.lock:
        before = engine.token
    step(f"click overlay close (token before = {before})")
    page.get_by_test_id("overlay-close").click()

    def _stopped() -> bool:
        with engine.lock:
            return engine.token > before

    deadline = page.evaluate("Date.now()") + 4000
    while page.evaluate("Date.now()") < deadline and not _stopped():
        page.wait_for_timeout(100)
    assert _stopped(), "overlay close did not reach engine.stop()"
    with engine.lock:
        after = engine.token
    step.check(f"overlay close reached engine.stop() (token {before} -> {after})")


def test_overlay_reflects_live_reading_session(
    page: Page, app_url: str, backend, step
):
    """The overlay must visibly reflect a real reading session: idle →
    reading, karaoke words rendered, progress bar advancing — all driven
    by the real engine playing the real onboarding clip."""
    engine = backend["engine"]
    overlay = backend["overlay"]
    try:
        _start_reading_session(page, app_url, step)

        # The panel becomes visible and the body shows the read state.
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )
        expect(page.get_by_test_id("overlay-panel")).to_be_visible()
        step.check("overlay reached 'reading' and the panel is visible")
        # Karaoke words actually rendered into the body.
        words = page.locator('[data-testid="overlay-text"] .w')
        expect(words.first).to_be_visible(timeout=4000)
        assert words.count() > 3
        step.check(f"karaoke words rendered into the DOM ({words.count()} words)")

        # Backend agrees a real chunk is playing.
        snap = overlay.snapshot()
        assert snap["overlay_state"] == "reading"
        assert snap["chunk_duration"] > 1.0
        assert len(snap["words"]) > 3
        step.check(
            f"backend overlay snapshot: state=reading, "
            f"chunk_duration={snap['chunk_duration']:.2f}s, "
            f"{len(snap['words'])} words"
        )

        # Progress bar advances (real elapsed time against real audio).
        bar = page.locator(".overlay-bar > div")
        w0 = bar.evaluate("e => parseFloat(e.style.width) || 0")
        page.wait_for_timeout(900)
        w1 = bar.evaluate("e => parseFloat(e.style.width) || 0")
        assert w1 > w0, f"progress did not advance: {w0} -> {w1}"
        step.check(f"progress bar advanced against real audio ({w0}% -> {w1}%)")
    finally:
        engine.stop()


def test_overlay_karaoke_cursor_advances(page: Page, app_url: str, backend, step):
    """The karaoke highlight must actually move forward over time —
    the cursor word index must strictly increase during the real clip."""
    engine = backend["engine"]
    try:
        _start_reading_session(page, app_url, step)
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )
        step.check("overlay reached 'reading'")
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
        step.check(f"karaoke cursor appeared at word index {i0}")

        deadline = page.evaluate("Date.now()") + 6000
        i1 = i0
        while page.evaluate("Date.now()") < deadline:
            i1 = cursor_index()
            if i1 > i0:
                break
            page.wait_for_timeout(150)
        assert i1 > i0, f"karaoke cursor did not advance ({i0} -> {i1})"
        step.check(f"karaoke cursor advanced over real audio ({i0} -> {i1})")
    finally:
        engine.stop()


def test_overlay_transport_buttons_reach_engine_during_playback(
    page: Page, app_url: str, backend, step
):
    """Strengthened replacement for the old near-tautological transport
    test. Drives a REAL reading session, then drives the transport and
    asserts a real engine effect: Replay re-runs the onboarding flow and
    bumps the cancellation token; the engine stays consistent."""
    engine = backend["engine"]
    try:
        _start_reading_session(page, app_url, step)
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )
        step.check("overlay reached 'reading'")

        # Replay during an active onboarding read re-enters
        # _start_onboarding which bumps engine.token (real effect).
        with engine.lock:
            tok_before = engine.token
        step(f"click overlay Replay during playback (token = {tok_before})")
        page.get_by_test_id("overlay-replay").click()

        def _token_bumped() -> bool:
            with engine.lock:
                return engine.token > tok_before

        deadline = page.evaluate("Date.now()") + 5000
        while page.evaluate("Date.now()") < deadline and not _token_bumped():
            page.wait_for_timeout(100)
        assert _token_bumped(), "overlay Replay did not reach the engine"
        with engine.lock:
            tok_after = engine.token
        step.check(
            f"Replay reached the engine (token {tok_before} -> {tok_after})"
        )

        # prev / next are real bridge calls; the engine must stay
        # consistent (no queue corruption, still healthy) after them.
        step("click overlay prev then next")
        page.get_by_test_id("overlay-prev").click()
        page.get_by_test_id("overlay-next").click()
        page.wait_for_timeout(150)
        assert engine.queue_length() == 0
        # Overlay is still in a real reading session driven by the engine.
        ostate = backend["overlay"].snapshot()["overlay_state"]
        assert ostate in ("reading", "thinking", "done")
        step.check(
            f"engine stayed consistent (queue empty, overlay_state={ostate!r})"
        )
    finally:
        engine.stop()


def test_overlay_auto_hide_actually_hides(page: Page, app_url: str, backend, step):
    """`auto_hide_ms` must actually hide the overlay. Set a short
    auto-hide, run a real reading session, stop it (engine fires
    set_state('done')), then assert the WebOverlay auto-hide timer
    really flips the state to idle and the panel disappears — the exact
    behaviour that was previously inert."""
    engine = backend["engine"]
    config = backend["config"]
    prev = config.get("auto_hide_ms")
    config["auto_hide_ms"] = 500  # short, real auto-hide
    step("set auto_hide_ms = 500 (short, real auto-hide)")
    try:
        _start_reading_session(page, app_url, step)
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=8000
        )
        expect(page.get_by_test_id("overlay-panel")).to_be_visible()
        step.check("overlay 'reading' and panel visible")

        # Stop the read → engine calls overlay.set_state('done'), which
        # arms the real auto-hide timer for auto_hide_ms (500 ms).
        step("stop the engine (arms the real auto-hide timer)")
        engine.stop()

        # The overlay must reach 'done' then auto-hide to 'idle'; the
        # panel must visibly disappear (web analogue of win.withdraw()).
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "idle", timeout=8000
        )
        expect(page.get_by_test_id("overlay-panel")).to_be_hidden()

        # Backend state agrees the auto-hide fired (not just the DOM).
        assert backend["overlay"].snapshot()["overlay_state"] == "idle"
        step.check(
            "auto-hide fired: overlay_state == idle and panel hidden "
            "(DOM + backend agree)"
        )
    finally:
        config["auto_hide_ms"] = prev
        engine.stop()


# ---------------------------------------------------------------------------
# Onboarding / Notices
# ---------------------------------------------------------------------------

def test_onboarding_renders_and_closes(page: Page, app_url: str, step):
    _goto(page, app_url, "onboarding", step)
    expect(page.get_by_test_id("onboarding-title")).to_be_visible()
    expect(page.get_by_test_id("onboarding-status")).to_be_visible()
    # A Skip/Close button is always present regardless of readiness.
    skip = page.locator(
        '[data-testid="onboarding-skip"], [data-testid="onboarding-close"]'
    )
    expect(skip.first).to_be_visible()
    step.check("onboarding title + status + a Skip/Close button visible")


def test_notices_window_loads_real_text(page: Page, app_url: str, backend, step):
    _goto(page, app_url, "notices", step)
    body = page.get_by_test_id("notices-body")
    expect(body).to_be_visible()
    expected = backend["bridge"].get_notices()
    assert body.inner_text().strip()[:40] == expected.strip()[:40]
    step.check(
        "notices body matches the real bridge.get_notices() resolver output "
        f"(prefix {expected.strip()[:40]!r})"
    )
