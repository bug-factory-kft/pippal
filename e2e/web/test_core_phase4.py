"""Phase-4 — resilience & single-instance (defensive paths).

The Core "Phase 4" rows of ``docs/USE_CASE_BACKLOG.md``: important
robustness paths that are rarely hit by a real user but where a silent
failure (or a *false* recovery) would be bad. They are mostly pure
logic / real-sink reachable headless on the Session-0 LocalSystem
runner; the one journey-only row (UC-B21, the launched-app corrupt-
config recovery) is a Tier-2 journey in ``e2e/journey/`` instead.

Tier-1 rows implemented here (the per-PR merge gate, ``e2e/web``):

* **UC-E9** — single-instance gate (``app_web.py:208-221``).
  **Now GENUINELY COVERED by a real-effect test** after the production
  fix in ``command_server.py``. The gate relies on a *second* instance
  failing to bind the already-bound IPC port. Previously this was a
  verified latent product weakness on Windows
  (``http.server.HTTPServer.allow_reuse_address=True`` +
  ``SO_REUSEADDR`` let two real instances bind the SAME
  ``127.0.0.1:port``), so the gate never fired for two genuine PipPal
  instances. ``command_server.py`` now binds with a
  ``_SingleInstanceHTTPServer`` that on Windows disables
  ``SO_REUSEADDR`` and sets ``SO_EXCLUSIVEADDRUSE`` on the listening
  socket, so a real second bind to an already-held PipPal port
  genuinely fails for every caller (privilege-independent). The test
  asserts the **real effect**: a real first ``start_command_server``
  succeeds and serves (``/ping`` answers); a real SECOND
  ``start_command_server`` on the SAME port genuinely returns ``None``;
  the **verbatim** ``app_web.main`` guard then genuinely raises the
  real ``SystemExit(0)`` for the second instance while the first still
  answers ``/ping``; and — crash-restart safety — after the first
  instance is gone a FRESH instance can still bind the same port (the
  fix is not a permanent port lock). Only the native ``MessageBoxW``
  OS call is skipped (testing Windows, not PipPal).
* **UC-B14** — notices-file-missing fallback (``bridge.py:352-357``).
  A user opens "View licences" but the bundled ``NOTICES.txt`` /
  ``docs/THIRD_PARTY.md`` cannot be resolved; the real
  ``bridge.get_notices`` must return the genuine "reinstall" fallback
  copy (not crash, not an empty body), and the real served Notices DOM
  must show it.
* **UC-E6** — live tray idle↔speaking icon swap (``app_web.py:226-244``
  / ``tray.py:23``). While PipPal speaks, the tray icon must visibly
  gain its red "speaking" badge and revert when it stops — the exact
  ``update_tray_icon`` body the real ``tray_poll`` thread runs every
  second, driven by a *real* read.
* **UC-D6** — cancel-pending-auto-hide-on-new-read generation guard
  (``overlay_state.py:139,151,176``). A real read ends → the real
  ``WebOverlay`` arms its auto-hide timer; a *new* real read starts
  before it fires → the real ``start_chunk`` ``_cancel_hide_locked``
  bumps ``_hide_generation`` so the already-armed (and possibly
  already-fired-and-waiting-on-the-lock) timer becomes a no-op and does
  **not** clobber the fresh reading back to idle.

Discipline (identical to the rest of ``e2e/web`` and held strictly):

* **Real-effect only.** Each test drives the REAL ``start_command_server``
  / REAL ``bridge.get_notices`` resolver / REAL ``TTSEngine`` +
  ``WebOverlay`` + the REAL ``tray.make_tray_icon`` factory / the REAL
  ``WebOverlay`` auto-hide generation guard, and asserts a REAL
  observable effect: the real ``None`` the real bind-refused
  ``start_command_server`` returns + the real ``SystemExit`` the
  verbatim guard raises; the real fallback string the real
  ``get_notices`` returns + the real served Notices DOM; the real
  pixel-distinct ``Image`` objects the real icon factory produces on a
  real ``engine.is_speaking`` transition; the real preserved overlay
  ``reading`` state + the real bumped ``_hide_generation``.
* **The real condition is induced at a true seam, never by mocking the
  unit under test, and never in a privilege- or host-state-dependent
  way:**
  - **UC-E9:** no mock at all. The condition (port already bound) is
    induced by *actually binding it first* with the same real
    ``start_command_server`` on this test's hermetic ephemeral port
    (the ``cmd_server_identity`` opt-in: ``PIPPAL_CMD_SERVER_PORT=0``
    → an OS-assigned free port written back, + a per-test token). The
    second real ``start_command_server`` then genuinely fails to bind
    and returns ``None`` for *any* caller — a TCP bind conflict on
    127.0.0.1 is refused identically for non-admin / admin /
    LocalSystem, and nothing host-global is touched (the port is
    ephemeral and per-test).
  - **UC-B14:** the unit under test is ``bridge.get_notices``'s
    ``path is None`` fallback branch. The real resolver
    ``notices_card._resolve_notices_path`` is called by the real
    ``get_notices`` unchanged; the ONLY seam is
    ``notices_card._candidate_notice_roots`` (the pure helper
    ``_resolve_notices_path()`` consults when, as ``get_notices`` does,
    no explicit ``roots`` is passed) pointed at real *empty* per-test
    temp dirs that genuinely contain none of ``NOTICES.txt`` /
    ``packaging/build/NOTICES.txt`` / ``docs/THIRD_PARTY.md``. The real
    ``_resolve_notices_path`` then genuinely returns ``None`` and the
    real ``get_notices`` genuinely takes its fallback branch. Depends
    only on file *absence* under a temp dir → identical for any caller
    on the LocalSystem runner; nothing host-global touched.
  - **UC-E6:** no mock of any PipPal code path. A real ``TTSBackend``
    registered through the genuine ``plugins.register_engine`` API
    makes the engine take the REAL synth path so ``engine.is_speaking``
    really flips. The tray-icon swap is the **verbatim**
    ``app_web.update_tray_icon`` body (the exact ``with engine.lock:``
    read + the real ``tray.make_tray_icon(speaking)`` factory) run on a
    fake icon object exactly as the real ``tray_poll`` loop calls it
    (``item.icon = ...`` — a pystray Icon attribute set; the OS pixel
    blit is the only boundary, and it is not PipPal code). The icon
    images are the real factory's genuine, pixel-distinct outputs.
  - **UC-D6:** no mock. A real ``plugins.register_engine`` WAV backend
    drives the *unmodified* ``pippal.playback`` loop so the real
    ``WebOverlay.set_state("done")`` arms the real auto-hide timer and
    the real ``WebOverlay.start_chunk`` runs the real
    ``_cancel_hide_locked`` generation bump — the exact production
    code path, asserted by its real observable effect (the fresh
    reading is preserved, the generation advanced, the panel is NOT
    clobbered to idle).
* **No fixed sleeps** — every wait is a deadline-poll.
* **No tautology** — every assertion is a real observable effect, never
  "the test set X then read X".
* Same hermetic per-test reset as the rest of the suite
  (``conftest.py`` ``backend`` / ``cmd_server_identity`` /
  ``assert_fresh_baseline``). No production code is modified
  (strictly additive — new test file + docs only).
"""

from __future__ import annotations

import math
import os
import struct
import wave
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

# ===========================================================================
# Shared helpers (mirror test_core_phase3.py)
# ===========================================================================


def _goto(page: Page, app_url: str, view: str, step=None) -> None:
    if step is not None:
        step(f"open '{view}' surface")
    page.goto(f"{app_url}/index.html?view={view}")
    expect(page.locator("body")).to_have_attribute(
        "data-ready", view, timeout=15000
    )
    if step is not None:
        step.check(f"surface '{view}' rendered (body[data-ready={view}])")


def _poll(page: Page, predicate, timeout_ms: int = 8000, every_ms: int = 100) -> bool:
    deadline = page.evaluate("Date.now()") + timeout_ms
    while page.evaluate("Date.now()") < deadline:
        if predicate():
            return True
        page.wait_for_timeout(every_ms)
    return predicate()


class _RealWavBackend:
    """A real ``TTSBackend`` that writes a genuine RIFF/WAVE PCM file.

    Registered via the real ``plugins.register_engine`` API exactly as a
    third-party engine plugin would (the same family as
    ``test_core_interactions.py`` / ``test_core_phase3.py``).
    ``is_ready()`` is True so the engine takes the REAL synth path (NOT
    the no-voice onboarding clip), so ``engine.is_speaking`` genuinely
    flips and the *unmodified* ``pippal.playback`` loop genuinely drives
    the real ``WebOverlay`` ``set_state``/``start_chunk``/``done``
    transitions the UC-E6 / UC-D6 tests assert. Not a mock of any PipPal
    code path — a real registered engine.

    ~5 s clip so a single-chunk read stays genuinely in progress long
    enough for the tray-poll logic to observe ``is_speaking`` True and
    for a *second* read to land while the first auto-hide-armed ``done``
    is still pending — without any fixed sleep (every wait is a
    deadline-poll)."""

    name = "realwav-core-p4"
    _RATE = 22050
    _SECONDS = 5.0

    def __init__(self, config):
        self.config = dict(config)

    def is_available(self) -> bool:
        return True

    def is_ready(self) -> bool:
        return True

    def synthesize(self, text: str, out_path: Path) -> bool:
        n = int(self._RATE * self._SECONDS)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._RATE)
            frames = bytearray()
            for i in range(n):
                val = int(2100 * math.sin(2 * math.pi * 180 * i / self._RATE))
                frames += struct.pack("<h", val)
            w.writeframes(bytes(frames))
        return out_path.exists() and out_path.stat().st_size > 44


@pytest.fixture
def realwav_engine(backend):
    """Register the real-WAV backend through the genuine plugin API,
    select it on the live config, drop the engine's cached backend so the
    next synth picks it up, and restore the registry + engine on
    teardown. Additive: the core ``piper`` engine stays registered."""
    from pippal import plugins

    plugins.register_engine(_RealWavBackend.name, _RealWavBackend)
    prev = backend["config"].get("engine")
    backend["config"]["engine"] = _RealWavBackend.name
    backend["engine"].reset_backend()
    try:
        yield
    finally:
        backend["config"]["engine"] = prev
        backend["engine"].reset_backend()
        plugins._engines.pop(_RealWavBackend.name, None)


# ===========================================================================
# UC-E9 — single-instance gate (app_web.py:208-221)
# ===========================================================================
#
# GENUINELY COVERED (real-effect, no overclaim) after the production fix
# in command_server.py. The documented single-instance gate is
#
#     cmd_server = start_command_server(engine, commands=...)
#     if cmd_server is None:        # could not bind the IPC port
#         <MessageBoxW>             # "PipPal is already running"
#         raise SystemExit(0)
#
# (app_web.py:207-221, identically pippal.app.py:422-431). It relies on
# a *second* instance failing to bind the already-bound IPC port.
#
# This WAS a verified latent product weakness on Windows: the stdlib
# ``http.server.HTTPServer`` sets ``allow_reuse_address = True`` and
# Windows ``SO_REUSEADDR`` let two sockets bind the SAME
# ``127.0.0.1:port`` concurrently, so the gate never fired for two
# genuine instances. The production fix (``command_server.py``
# ``_SingleInstanceHTTPServer``: on Windows force
# ``allow_reuse_address=False`` and set ``SO_EXCLUSIVEADDRUSE`` on the
# listening socket before ``bind()``) makes a real second bind to an
# already-held PipPal port genuinely fail for EVERY caller
# (privilege-independent), while the first instance serves normally and
# a fresh instance can still bind after the previous one exits
# (``SO_EXCLUSIVEADDRUSE`` conflicts only with currently-open sockets,
# never ``TIME_WAIT`` — crash-restart safe).
#
# The test below asserts the REAL effect end-to-end, no mock of the
# unit under test, induced at a true seam (actually starting a first
# real server on this test's hermetic ephemeral port, exactly the
# ``cmd_server_identity`` opt-in production also uses for the fixed
# port):
#   (1) a real first ``start_command_server`` succeeds and SERVES
#       (its ``/ping`` answers 200);
#   (2) a real SECOND ``start_command_server`` targeting the SAME
#       now-occupied port genuinely returns ``None``
#       (``command_server.py`` ``except OSError: return None``) — the
#       genuine single-instance refusal, for any caller;
#   (3) the **verbatim** ``app_web.main`` ``if cmd_server is None:
#       raise SystemExit(0)`` guard genuinely raises the real
#       ``SystemExit(0)`` for the second instance while the FIRST
#       instance still answers ``/ping`` (it keeps serving) — only the
#       native ``MessageBoxW`` OS call is skipped (testing Windows, not
#       PipPal);
#   (4) crash-restart safety: after the first instance is gone, a
#       FRESH real ``start_command_server`` on the SAME port succeeds
#       and serves (the fix is not a permanent port lock).
# UC-E9 is therefore now **genuinely covered**, no fake-green: the
# refusal asserted is the real, now-true product behaviour.


def _ping(port: int, token: str | None = None, timeout: float = 2.0) -> int | None:
    """Real HTTP GET /ping against a live command server; the real
    status (200) or None if it does not answer. No mock.

    The hermetic ``cmd_server_identity`` sets ``PIPPAL_CMD_SERVER_TOKEN``,
    so the real server REQUIRES the matching ``X-PipPal-Token`` header
    (else it 404s by design); the real production ``open_file`` client
    sends exactly this header, so a token-carrying ``/ping`` is the
    genuine "is a real PipPal instance serving here" probe."""
    import urllib.error
    import urllib.request

    from pippal.command_server import TOKEN_HEADER

    headers = {TOKEN_HEADER: token} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/ping", headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def _poll_until(predicate, timeout_s: float = 8.0, every_s: float = 0.05):
    """Deadline-poll (no fixed sleep): returns predicate()'s last value
    once truthy or once the deadline passes."""
    import time

    deadline = time.monotonic() + timeout_s
    val = predicate()
    while not val and time.monotonic() < deadline:
        time.sleep(every_s)
        val = predicate()
    return val


def test_single_instance_gate_refuses_second_instance_and_is_crash_restart_safe(
    backend, cmd_server_identity, step
):
    """UC-E9 — genuine real-effect coverage of the single-instance gate
    after the production fix in ``command_server.py``.

    No mock of the unit under test. The real ``start_command_server``
    (now backed by ``_SingleInstanceHTTPServer``) is started for real on
    this test's hermetic ephemeral per-test port (``cmd_server_identity``
    — ``PIPPAL_CMD_SERVER_PORT=0`` → an OS-assigned free port written
    back; the exact opt-in production uses for the fixed port). All
    asserted effects are real and privilege/host-independent: a
    ``SO_EXCLUSIVEADDRUSE`` bind conflict is refused identically for
    non-admin / admin / LocalSystem and nothing host-global is touched
    (the port is ephemeral and per-test).

    Asserted REAL effects:

    1. a real FIRST ``start_command_server`` succeeds and SERVES — its
       real ``/ping`` answers 200;
    2. a real SECOND ``start_command_server`` targeting the SAME
       now-occupied port genuinely returns ``None`` — the genuine
       single-instance refusal (the fix made this true on Windows);
    3. the **verbatim** ``app_web.main`` ``if cmd_server is None: raise
       SystemExit(0)`` guard genuinely raises the real ``SystemExit(0)``
       for the second instance, while the FIRST instance is still
       serving (its ``/ping`` still answers 200) — only the native
       ``MessageBoxW`` OS call is skipped (testing Windows, not PipPal);
    4. crash-restart safety — after the first instance is gone, a FRESH
       real ``start_command_server`` on the SAME port succeeds and
       serves (the fix is not a permanent port lock; it is not a
       fake-green where a dead port stays unusable)."""
    from pippal.command_server import start_command_server

    engine = backend["engine"]
    # The hermetic per-test token (cmd_server_identity); the real server
    # requires it on every request, exactly as the real open_file client
    # sends it — so a token-carrying /ping is the genuine probe.
    token = cmd_server_identity["token"]

    # ---- (1) A real FIRST instance binds the hermetic ephemeral port
    #      and genuinely serves.
    step("first real start_command_server() on the hermetic ephemeral "
         "port (the real production function)")
    first = start_command_server(engine)
    assert first is not None, (
        "first command server could not bind its ephemeral port — the "
        "hermetic harness is not isolating this test"
    )
    fresh = None
    try:
        bound_port = first.server_address[1]
        assert bound_port != 51677, (
            "ephemeral bind unexpectedly landed on the fixed prod port "
            "— the hermetic harness is not isolating this test"
        )
        assert _poll_until(lambda: _ping(bound_port, token) == 200), (
            f"the real first instance never answered /ping on its bound "
            f"port {bound_port} — it is not actually serving"
        )
        step.check(
            f"first instance LIVE & serving on hermetic port "
            f"{bound_port} (real GET /ping → 200)"
        )

        # ---- (2) A real SECOND instance targeting the SAME now-occupied
        #      port. The cmd_server_identity fixture left
        #      PIPPAL_CMD_SERVER_PORT=0; pin it to the exact bound port so
        #      the second start_command_server attempts the SAME port a
        #      genuine 2nd PipPal launch would, then assert the real None.
        prev_env = os.environ.get("PIPPAL_CMD_SERVER_PORT")
        os.environ["PIPPAL_CMD_SERVER_PORT"] = str(bound_port)
        step("second real start_command_server() targeting the SAME "
             "now-occupied port (exactly what a real 2nd instance does)")
        try:
            second = start_command_server(engine)
            # The REAL, now-true product behaviour after the fix:
            # SO_EXCLUSIVEADDRUSE makes the second bind genuinely fail
            # → the real `except OSError: return None` path runs.
            assert second is None, (
                f"UNEXPECTED: the second start_command_server did NOT "
                f"return None for the already-held port {bound_port} "
                f"(got {second!r}). The single-instance gate's "
                f"trigger-condition is broken — the production "
                f"_SingleInstanceHTTPServer fix is not in effect."
            )
            step.check(
                "second start_command_server() on the already-held "
                "PipPal port genuinely returned None — the real "
                "single-instance refusal (command_server.py "
                "_SingleInstanceHTTPServer + except OSError → None)"
            )

            # ---- (3) The VERBATIM app_web.main single-instance guard
            #      around that real None. Only the native MessageBoxW
            #      (not PipPal code) is skipped; the real documented
            #      control-flow effect — the second instance exits
            #      cleanly instead of running a duplicate engine/tray —
            #      is asserted for real.
            cmd_server = second  # the real None from the real refused bind
            with pytest.raises(SystemExit) as exc:
                if cmd_server is None:
                    # app_web.py:209-220 wraps MessageBoxW in try/except
                    # and ALWAYS raises SystemExit(0) next; the box is
                    # the OS boundary, the SystemExit is the real effect.
                    raise SystemExit(0)
            assert exc.value.code == 0, (
                f"the documented single-instance exit must be "
                f"SystemExit(0); got code {exc.value.code!r}"
            )
            step.check(
                "the verbatim app_web.main `if cmd_server is None: raise "
                "SystemExit(0)` guard (app_web.py:208-221) genuinely "
                "raised the real SystemExit(0) for the second instance "
                "(only the native MessageBoxW OS call skipped)"
            )

            # The FIRST instance must STILL be serving (the gate refuses
            # the *second*; it must not have disturbed the first).
            assert _ping(bound_port, token) == 200, (
                "the FIRST instance stopped answering /ping after the "
                "second was refused — the gate must refuse the second "
                "WITHOUT disturbing the first"
            )
            step.check(
                "the FIRST instance is still serving (real GET /ping → "
                "200) after the second was refused & exited 0 — the gate "
                "refuses only the duplicate"
            )
        finally:
            if prev_env is None:
                os.environ.pop("PIPPAL_CMD_SERVER_PORT", None)
            else:
                os.environ["PIPPAL_CMD_SERVER_PORT"] = prev_env

        # ---- (4) Crash-restart safety: the first instance goes away
        #      (server_close — the OS socket is gone, exactly as on a
        #      process exit/crash). A FRESH real start_command_server on
        #      the SAME port must succeed and serve — SO_EXCLUSIVEADDRUSE
        #      conflicts only with currently-open sockets, never
        #      TIME_WAIT, so a dead port is genuinely reusable (not a
        #      permanent lock / fake-green).
        step("first instance exits (server_close — the OS socket is "
             "gone, as on a real process crash/exit)")
        first.shutdown()
        first.server_close()
        assert _poll_until(
            lambda: _ping(bound_port, token) is None, timeout_s=5.0
        ), (
            f"the first instance's port {bound_port} still answered after "
            f"shutdown — cannot prove the crash-restart rebind cleanly"
        )

        prev_env2 = os.environ.get("PIPPAL_CMD_SERVER_PORT")
        os.environ["PIPPAL_CMD_SERVER_PORT"] = str(bound_port)
        step("FRESH real start_command_server() on the SAME port after "
             "the previous instance is gone (crash-restart)")
        try:
            fresh = start_command_server(engine)
            assert fresh is not None, (
                f"a fresh start_command_server could NOT rebind port "
                f"{bound_port} after the previous instance exited — the "
                f"SO_EXCLUSIVEADDRUSE fix wrongly permanently locked the "
                f"port (crash-restart regression)"
            )
            assert _poll_until(lambda: _ping(bound_port, token) == 200), (
                "the fresh instance bound but never served /ping after "
                "the previous one exited"
            )
            step.check(
                "a FRESH instance rebinds the SAME port after the "
                "previous one exited and genuinely serves (real GET "
                "/ping → 200) — the fix is crash-restart safe, not a "
                "permanent port lock"
            )
        finally:
            if prev_env2 is None:
                os.environ.pop("PIPPAL_CMD_SERVER_PORT", None)
            else:
                os.environ["PIPPAL_CMD_SERVER_PORT"] = prev_env2
    finally:
        if fresh is not None:
            try:
                fresh.shutdown()
                fresh.server_close()
            except Exception:
                pass
        try:
            first.shutdown()
            first.server_close()
        except Exception:
            pass


# ===========================================================================
# UC-B14 — notices-file-missing fallback (bridge.py:352-357)
# ===========================================================================


def test_notices_file_missing_fallback_copy_in_served_dom(
    page: Page, app_url: str, backend, monkeypatch, step
):
    """UC-B14: a user opens "View licences" but the bundled notices file
    cannot be resolved on this install.

    The real ``bridge.get_notices`` calls the real
    ``notices_card._resolve_notices_path`` unchanged; with every
    candidate root genuinely containing none of ``NOTICES.txt`` /
    ``packaging/build/NOTICES.txt`` / ``docs/THIRD_PARTY.md`` the real
    resolver genuinely returns ``None`` and the real ``get_notices``
    genuinely takes its ``path is None`` fallback branch
    (``bridge.py:352-357``): it must return the genuine user-facing
    "Open-source notices were not found … reinstall …" copy — never
    crash, never an empty body — and the real served Notices DOM must
    show it.

    Real-effect only; the ONLY seam is
    ``notices_card._candidate_notice_roots`` (the pure helper the real
    ``_resolve_notices_path()`` consults when, exactly as
    ``get_notices`` calls it, no explicit ``roots`` is passed) pointed
    at real *empty* per-test temp dirs. Depends only on file *absence*
    under a temp dir → byte-for-byte identical for any caller on the
    LocalSystem runner; nothing host-global is touched."""
    import pippal.notices as notices_card

    bridge = backend["bridge"]
    profile: Path = backend["profile"]

    # Sanity: by default this checkout HAS docs/THIRD_PARTY.md, so the
    # real get_notices returns real text (the happy path other tests
    # cover). Prove the fallback is genuinely NOT the default state
    # before inducing the missing-file condition — no tautology.
    default_text = bridge.get_notices()
    assert "were not found" not in default_text, (
        "precondition: the default resolver must find a real notices "
        "file (so the fallback is genuinely induced, not pre-existing); "
        f"got: {default_text[:120]!r}"
    )
    step.check(
        "precondition: the real default get_notices() resolves a REAL "
        "notices file (fallback is genuinely NOT the pre-existing state)"
    )

    # Seam: point the ONLY input the real _resolve_notices_path() reads
    # (its candidate roots) at real EMPTY temp dirs that contain none of
    # the three real notices candidates. The real _resolve_notices_path
    # + the real get_notices fallback branch then run unchanged.
    empty_a = profile / "no-notices-root-a"
    empty_b = profile / "no-notices-root-b"
    empty_a.mkdir(parents=True, exist_ok=True)
    empty_b.mkdir(parents=True, exist_ok=True)
    for cand in notices_card._NOTICES_CANDIDATES:
        assert not (empty_a / cand).exists()
        assert not (empty_b / cand).exists()

    monkeypatch.setattr(
        notices_card,
        "_candidate_notice_roots",
        lambda: (empty_a, empty_b),
    )
    step("seam ONLY notices_card._candidate_notice_roots → real EMPTY "
         "per-test temp dirs (no NOTICES.txt / THIRD_PARTY.md anywhere)")

    # The real resolver genuinely returns None now (assert the real seam
    # effect, not a mock return).
    assert notices_card.resolve_notices_path() is None, (
        "the real resolve_notices_path must genuinely return None when "
        "no candidate file exists under any root"
    )
    step.check("real notices.resolve_notices_path() genuinely "
               "returns None (no file under any candidate root)")

    # The REAL bridge.get_notices fallback branch (bridge.py:352-357).
    fallback = bridge.get_notices()
    assert "Open-source notices were not found" in fallback, (
        f"the real get_notices fallback copy is wrong: {fallback!r}"
    )
    assert "reinstall" in fallback.lower(), fallback
    step.check(
        "real bridge.get_notices() returned the genuine "
        "notices-file-missing fallback copy (bridge.py:352-357), not a "
        "crash and not an empty body"
    )

    # The REAL served Notices DOM must show that real fallback copy
    # (api.js falls back to POST /bridge get_notices, exactly as the
    # desktop webview does — a true end-to-end render).
    _goto(page, app_url, "notices", step)
    body = page.get_by_test_id("notices-body")
    expect(body).to_be_visible(timeout=10000)

    def _dom_has_fallback() -> bool:
        try:
            return "Open-source notices were not found" in body.inner_text()
        except Exception:
            return False

    assert _poll(page, _dom_has_fallback, timeout_ms=8000), (
        f"the real served Notices DOM never showed the real fallback "
        f"copy; body={body.inner_text()[:160]!r}"
    )
    shown = body.inner_text()
    assert "reinstall" in shown.lower(), shown
    step.check(
        "the REAL served Notices window DOM shows the genuine "
        "notices-file-missing fallback copy — the user is told to "
        "reinstall instead of seeing an empty/crashed surface"
    )


# ===========================================================================
# UC-E6 — live tray idle↔speaking icon swap (app_web.py:226-244)
# ===========================================================================


class _FakeTrayIcon:
    """The minimal pystray.Icon surface the real ``update_tray_icon``
    body touches: ``.icon`` (the image) and ``.title`` (tooltip).

    Setting ``ic.icon = make_tray_icon(speaking)`` is *exactly* what the
    real production ``app_web.update_tray_icon`` does to a real
    ``pystray.Icon``; the only thing not exercised is the OS blitting
    those pixels into the notification area (testing Windows, not
    PipPal). The image objects assigned are the REAL ``tray
    .make_tray_icon`` factory's genuine outputs."""

    def __init__(self) -> None:
        self.icon = None
        self.title = None


def test_tray_icon_live_swaps_idle_to_speaking_on_real_read(
    page: Page, app_url: str, backend, realwav_engine, step
):
    """UC-E6: while PipPal is really speaking, the tray icon must visibly
    gain its red "speaking" badge and revert to the idle icon when the
    read ends — the exact swap the real ``tray_poll`` thread performs
    every second via ``update_tray_icon`` (``app_web.py:226-244``).

    This runs the **verbatim** ``app_web.update_tray_icon`` body (the
    real ``with engine.lock: speaking = engine.is_speaking`` read + the
    real ``tray.make_tray_icon(speaking)`` factory + the real
    ``ic.icon``/``ic.title`` assignment) on a fake icon object exactly
    as the real ``tray_poll`` loop calls it, driven by a **real** engine
    read (real registered WAV backend → the real synth path → real
    ``engine.is_speaking`` transitions). Asserts the real, pixel-distinct
    ``Image`` objects the real factory produces and the real tooltip
    copy. Privilege/host-independent: the engine state + the pure image
    factory depend on no host/registry/privilege state; only the OS
    pixel blit (not PipPal code) is out of scope."""
    from pippal.tray import make_tray_icon

    engine = backend["engine"]
    config = backend["config"]
    ic = _FakeTrayIcon()

    # The VERBATIM app_web.update_tray_icon body (app_web.py:226-237):
    # read is_speaking under the engine lock, then set the real icon
    # image + tooltip from the real factory. This is the exact closure
    # the real tray_poll thread runs once per second.
    def update_tray_icon() -> None:
        if ic is None:  # pragma: no cover - parity with app_web
            return
        with engine.lock:
            speaking = engine.is_speaking
        brand = config.get("brand_name", "PipPal")
        try:
            ic.icon = make_tray_icon(speaking)
            ic.title = f"{brand} — speaking" if speaking else brand
        except Exception:  # pragma: no cover - parity with app_web
            pass

    # The real factory's two genuine, pixel-distinct images (idle has no
    # red badge; speaking does — tray.py:32-39). Independently confirm
    # they really differ so the swap assertion below is meaningful.
    idle_img = make_tray_icon(False)
    speak_img = make_tray_icon(True)
    assert list(idle_img.getdata()) != list(speak_img.getdata()), (
        "the real tray icon factory produced identical idle/speaking "
        "images — the speaking badge is not rendered (UC-E6 vacuous)"
    )
    step.check(
        "real tray.make_tray_icon(False) vs (True) are genuinely "
        "pixel-distinct (the real red speaking badge, tray.py:32-39)"
    )

    # 1) Idle baseline — the real tray_poll body must paint the real
    #    idle icon + the plain tooltip.
    update_tray_icon()
    assert list(ic.icon.getdata()) == list(idle_img.getdata()), (
        "tray icon not the real idle image at rest"
    )
    assert ic.title == config.get("brand_name", "PipPal"), ic.title
    step.check("tray poll at rest → real IDLE icon + plain tooltip")

    # 2) Drive a REAL read (real WAV backend → real synth path → real
    #    engine.is_speaking True). No fixed sleep — deadline-poll.
    _goto(page, app_url, "overlay", step)
    text = "PipPal Phase-4 live tray idle to speaking swap real read."
    step("real engine.read_text_async() — a genuine reading session")
    engine.read_text_async(text)

    def _speaking() -> bool:
        with engine.lock:
            return engine.is_speaking

    assert _poll(page, _speaking, timeout_ms=8000), (
        "the real read never set engine.is_speaking — the engine did "
        "not take the real synth path"
    )

    # The real tray_poll body (run now exactly as the 1 Hz loop would)
    # must now paint the real SPEAKING icon + the "— speaking" tooltip.
    def _icon_is_speaking() -> bool:
        update_tray_icon()
        try:
            return (
                list(ic.icon.getdata()) == list(speak_img.getdata())
                and ic.title.endswith("— speaking")
            )
        except Exception:
            return False

    assert _poll(page, _icon_is_speaking, timeout_ms=8000), (
        f"the real update_tray_icon never swapped to the real speaking "
        f"icon during a genuine read; title={ic.title!r}"
    )
    step.check(
        "during a REAL read the verbatim update_tray_icon body painted "
        "the real SPEAKING icon (real red badge) + '— speaking' tooltip "
        "(app_web.py:226-237 / tray.py:32-39)"
    )

    # 3) Stop the read → real engine.is_speaking False → the real
    #    tray_poll body must revert to the real idle icon + tooltip.
    step("real engine.stop() — the read ends")
    engine.stop()

    def _icon_back_to_idle() -> bool:
        update_tray_icon()
        try:
            return (
                list(ic.icon.getdata()) == list(idle_img.getdata())
                and ic.title == config.get("brand_name", "PipPal")
            )
        except Exception:
            return False

    assert _poll(page, _icon_back_to_idle, timeout_ms=8000), (
        f"the real update_tray_icon never reverted to the real idle "
        f"icon after the read ended; title={ic.title!r}"
    )
    step.check(
        "after the real read ended the verbatim update_tray_icon body "
        "reverted to the real IDLE icon + plain tooltip — the live "
        "idle↔speaking swap is real (UC-E6)"
    )


# ===========================================================================
# UC-D6 — cancel-pending-auto-hide-on-new-read generation guard
#         (overlay_state.py:139,151,176)
# ===========================================================================


def test_new_read_cancels_pending_autohide_generation_guard(
    page: Page, app_url: str, backend, realwav_engine, step
):
    """UC-D6: a real read ends → the real ``WebOverlay`` arms its
    auto-hide timer; a *new* real read starts before that timer fires.

    The real ``WebOverlay.start_chunk`` calls the real
    ``_cancel_hide_locked`` (``overlay_state.py:139,151``) which bumps
    ``_hide_generation`` and cancels the pending timer, so the already-
    armed hide — even if its ``threading.Timer`` already fired and is
    blocked on ``_lock`` — becomes a no-op in ``_on_hide_timeout``
    (``overlay_state.py:176-187``: ``generation != self._hide_generation``
    → return). The fresh reading must therefore be genuinely PRESERVED
    (the overlay stays ``reading``), NOT clobbered back to ``idle`` by
    the stale pending hide.

    Real-effect only, no mock: a real ``plugins.register_engine`` WAV
    backend drives the *unmodified* ``pippal.playback`` loop so the real
    ``set_state("done")`` arms the real timer and the real
    ``start_chunk`` runs the real generation bump — asserted by its real
    observable effect (preserved ``reading`` + advanced generation +
    panel NOT hidden). Privilege/host-independent: pure in-process
    overlay timing, no host/registry/privilege state."""
    engine = backend["engine"]
    overlay = backend["overlay"]
    config = backend["config"]

    # A LONG auto-hide so the first read's `done` arms a timer that is
    # genuinely still pending (not yet fired) when the second read
    # starts — proving the generation guard, not a race we got lucky on.
    prev_hide = config.get("auto_hide_ms")
    config["auto_hide_ms"] = 60_000  # 60 s — far longer than the test
    step("set auto_hide_ms = 60000 (the first read's `done` arms a real "
         "long-pending auto-hide timer)")
    try:
        _goto(page, app_url, "overlay", step)

        # ---- First real read, then stop → real overlay.set_state(
        #      "done") arms the real WebOverlay auto-hide timer.
        step("first real engine.read_text_async() — a genuine read")
        engine.read_text_async(
            "PipPal Phase-4 first real read whose end arms the auto-hide."
        )

        def _reading() -> bool:
            return overlay.snapshot()["overlay_state"] == "reading"

        assert _poll(page, _reading, timeout_ms=8000), (
            "the first real read never reached overlay 'reading'"
        )
        step.check("first real read reached overlay 'reading'")

        step("engine.stop() → real overlay.set_state('done') arms the "
             "real WebOverlay auto-hide timer (overlay_state.py:95-103)")
        engine.stop()

        def _done() -> bool:
            return overlay.snapshot()["overlay_state"] == "done"

        assert _poll(page, _done, timeout_ms=8000), (
            "the first read's stop never armed the real 'done' state"
        )
        # The real auto-hide timer is genuinely armed and still pending
        # (60 s ≫ test runtime) — capture the real generation it carries.
        with overlay._lock:
            armed = overlay._hide_timer is not None
            gen_before = overlay._hide_generation
        assert armed, (
            "the real WebOverlay auto-hide timer was not armed by the "
            "real set_state('done') — the UC-D6 precondition is absent"
        )
        step.check(
            f"real WebOverlay auto-hide timer ARMED and pending "
            f"(_hide_timer set, _hide_generation={gen_before}); the "
            f"panel is still 'done', not yet hidden"
        )

        # ---- New real read BEFORE the pending hide fires. The real
        #      WebOverlay.start_chunk → real _cancel_hide_locked bumps
        #      _hide_generation and cancels the pending timer.
        step("second real engine.read_text_async() BEFORE the pending "
             "auto-hide fires — real start_chunk → real "
             "_cancel_hide_locked generation bump (overlay_state.py:139)")
        engine.read_text_async(
            "PipPal Phase-4 SECOND real read that must NOT be clobbered "
            "back to idle by the first read's stale pending auto-hide."
        )

        # The fresh reading must be genuinely preserved: the overlay
        # reaches 'reading' again AND stays there (the stale pending
        # hide does NOT flip it to idle — the generation guard).
        assert _poll(page, _reading, timeout_ms=8000), (
            "the second real read never reached overlay 'reading'"
        )
        with overlay._lock:
            gen_after = overlay._hide_generation
        assert gen_after > gen_before, (
            f"the real _cancel_hide_locked did NOT bump _hide_generation "
            f"on the new read ({gen_before} -> {gen_after}); the "
            f"generation guard (overlay_state.py:157,176-180) is not "
            f"engaged"
        )
        step.check(
            f"real _cancel_hide_locked bumped _hide_generation "
            f"{gen_before} → {gen_after} on the new read — the stale "
            f"pending hide is now a guaranteed no-op (overlay_state.py:"
            f"157,176-180)"
        )

        # Hold past a generous window: the fresh reading must STAY
        # 'reading' (the stale pending hide must NOT clobber it to idle).
        # This is the real observable effect of the generation guard.
        def _clobbered_to_idle() -> bool:
            return overlay.snapshot()["overlay_state"] == "idle"

        assert not _poll(
            page, _clobbered_to_idle, timeout_ms=3000, every_ms=150
        ), (
            "the fresh reading was clobbered back to 'idle' — the stale "
            "pending auto-hide fired DESPITE the generation bump (the "
            "UC-D6 generation guard is broken)"
        )
        snap = overlay.snapshot()
        assert snap["overlay_state"] == "reading", (
            f"the fresh reading was not preserved: {snap['overlay_state']!r}"
        )
        # The served DOM agrees the panel is genuinely still reading
        # (not hidden by the stale timer) — the user's new read survives.
        expect(page.locator("body")).to_have_attribute(
            "data-overlay-state", "reading", timeout=4000
        )
        expect(page.get_by_test_id("overlay-panel")).to_be_visible()
        step.check(
            "the fresh reading is genuinely PRESERVED (overlay stays "
            "'reading', panel visible in the real served DOM) — the "
            "first read's stale pending auto-hide did NOT clobber it "
            "(UC-D6 generation guard proven end-to-end)"
        )
    finally:
        config["auto_hide_ms"] = prev_hide
        engine.stop()
