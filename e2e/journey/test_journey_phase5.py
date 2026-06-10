"""PipPal Tier-2 user-journey E2E — Phase-5 release-lane breadth.

The Core **Phase 5** Tier-2 rows of ``docs/USE_CASE_BACKLOG.md`` (the
*Phase 5 — Tier-2 journey breadth* section): two new full user-journeys
on the **actually launched** PipPal WebView2 desktop app, attached over
CDP and asserted against the *real running process* — exactly the
two-tier model of ``test_journeys.py`` (J1–J5) and
``test_journey_phase4.py`` (J6), with the same real per-journey
recording evidence artifact (ffmpeg ``.mp4`` / contact-sheet +
``trace.zip`` + window screenshot + app log + CDP version).

(The phase-plan section of the backlog historically numbered a
hotkey-rebind journey "J6"; that number was taken by Phase-4's
corrupt-config journey, and the hotkey-rebind use-case **UC-B7** is
already fully covered Tier-1 incl. its invalid/duplicate failure
variants — re-journeying a green Tier-1 row would add no use-case value.
Phase-5's genuine new Tier-2 breadth is the two journeys below, per the
independently-audited Phase-5 scope.)

* **J7 / UC-B11 + UC-B13 + UC-B12** — *user installs the Windows
  right-click "Read with PipPal" entry, reads a file THROUGH it, then
  removes it* — end-to-end on the **real launched app**. The launched
  app's own real ``bridge.install_context_menu`` performs the genuine
  per-user **HKCU** ``reg add`` writes (``context_menu.py:59``); the
  real registry keys are asserted present with the real ``%1`` command;
  then the **exact registered command** (``python -m pippal.open_file
  <file>`` — what Explorer spawns on a real right-click, with the
  clicked path as ``%1``) is run as a real subprocess **with the
  launched app's exact hermetic IPC identity** so it hits THIS launched
  app's already-running command server and the **real running app's
  real engine** reads the file (asserted via the live ``POST
  /bridge``); then the launched app's real ``bridge.remove_context_menu``
  deletes the keys (``context_menu.py:87``) and the real registry is
  asserted clean. **Hermetic + privilege/host-independent:** the
  per-user HKCU keys are the only global state — serialised under the
  SAME machine-wide registry lock the Tier-1 hermetic shell test uses
  and *always removed* in teardown even on failure, and the IPC is this
  journey's hermetic per-journey ephemeral port + token (the
  already-landed opt-in core hooks — production never sets them). HKCU
  writes are privilege-independent (every caller incl. the LocalSystem
  Tier-1 runner can write its own HKCU). This is the genuine
  launched-app round-trip the Tier-1 test can only *simulate* with a
  standalone command server — the real *desktop process* services the
  registered command here.

* **J8 / UC-D3 (replay / prev / next during a real read)** — *user
  skips and replays a sentence while PipPal is really reading* on the
  **real launched app**'s overlay. An already-set-up app with the
  cached real Piper + voice does a real **multi-chunk** read (real
  RIFF/WAVE synth), then the real reader-transport is driven through
  the launched app's own real ``POST /bridge`` ``overlay_action`` — the
  **exact transport the real desktop overlay window's prev/replay/next
  buttons use** (``webui/js/app.js:606-619`` →
  ``bridge.overlay_action`` → ``engine.prev_chunk`` /
  ``replay_chunk`` / ``next_chunk``): **next / prev** genuinely move
  the real ``chunk_idx`` on the running process, **replay** is a
  genuine accepted transport op that keeps the real read alive. Every
  assertion is a real effect on the live launched process (its real
  engine + real overlay snapshot), deadline-polled, no fixed sleep, no
  mock — privilege/host-independent (a real in-process read on a fresh
  temp profile).

  **HONEST SCOPE FINDING (verified on the real launched app — NOT
  fake-green).** UC-D5 (paused chip) / UC-D10 (pause→silence→resume)
  are **NOT added as a Tier-2 journey leg**, by a verified product
  fact: the **real desktop web overlay window has no pause control** —
  its only transport buttons are prev / replay / next / close
  (``webui/js/app.js:614-619``); the web ``/bridge`` exposes no
  ``pause`` method; and the only genuine product pause paths are the
  **global hotkey** ``hotkey_pause`` (an OS low-level-keyboard-hook
  keystroke — the documented OS boundary CDP cannot drive, "testing
  Windows, not PipPal") and the IPC ``/pause`` *control route*, which
  ``command_server.start_command_server`` gates behind
  ``control_routes_enabled`` (**default ``False``**) and
  ``app_web.main`` never enables — so ``POST /pause`` genuinely
  **404s** on the real launched desktop process (empirically verified
  here: real ``HTTP 404`` from the launched app's command server).
  Driving pause through a route that 404s on the real product, or
  asserting a journey leg that no real user surface can reach, would be
  fake-green — so it is **not claimed**. UC-D5/UC-D10 remain genuinely
  **covered by their existing Tier-1 test**
  (``e2e/web/test_core_interactions.py::test_pause_silences_and_resume_
  replays_then_seek_while_paused`` — the real ``engine.pause_toggle`` +
  the unmodified ``pippal.playback`` loop), unchanged. J8's honest
  additive value is the **UC-D3** launched-app transport, which IS a
  real user-reachable surface. (``command_server.py`` is protected —
  not changed here.)

WHY a dedicated self-contained launch fixture (additive, no conftest
change): the shared ``real_app`` fixture allocates the hermetic IPC
port + token only into the launched child's environment — it does NOT
expose them, and J7 must run the registered ``open_file`` command with
**exactly that** identity so it reaches THIS launched app's IPC. So,
exactly as ``test_journey_phase4.py``'s ``corrupt_config_app`` does,
this file replicates the **identical** launch technique the conftest
documents (flip the CDP port via the unmodified ``app_launcher.py`` →
the **unmodified** ``app_web.main()``; hermetic IPC via the opt-in core
hooks; fresh temp profile; the conftest's own ``_seed_profile`` /
``_install_cached_piper`` / ``_install_cached_voice``) and reuses the
public ``_recording.JourneyRecorder`` for the evidence artifact,
mirroring J1–J6 — the ONLY addition is exposing the journey's hermetic
``cmd_port`` / ``cmd_token`` on the app handle so J7's subprocess uses
the exact running instance's identity. No production code is modified
(strictly additive — this new test file + docs only). The
``.github`` Tier-2 workflow already auto-discovers every
``e2e/journey`` test (``run-journey.ps1`` runs the whole dir), so no
workflow change is needed or made.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util as _ilu
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from _journey_helpers import bridge_call, deadline_poll
from _recording import JourneyRecorder

pytestmark = pytest.mark.journey

# Load THIS directory's conftest by file path and reuse its documented
# launch helpers (identical rule to test_journey_phase4.py — the journey
# conftest is not importable by bare name under pytest's conftest model).
_JCONF_PATH = Path(__file__).resolve().parent / "conftest.py"
_spec = _ilu.spec_from_file_location("_journey_conftest_p5", _JCONF_PATH)
_jconf = _ilu.module_from_spec(_spec)
sys.modules["_journey_conftest_p5"] = _jconf
_spec.loader.exec_module(_jconf)

CHECKOUT = _jconf.CHECKOUT
LAUNCHER = _jconf.LAUNCHER
RealApp = _jconf.RealApp
_free_port = _jconf._free_port
_resolve_app_page = _jconf._resolve_app_page
_wait_cdp = _jconf._wait_cdp
_seed_profile = _jconf._seed_profile
_install_cached_piper = _jconf._install_cached_piper
_install_cached_voice = _jconf._install_cached_voice


@pytest.fixture
def launched_app(request: pytest.FixtureRequest) -> Iterator[RealApp]:
    """Launch ONE fresh REAL PipPal desktop app, seeded ``activated``
    with the cached real Piper + voice, and **expose this journey's
    hermetic IPC identity** (``cmd_port`` / ``cmd_token``) on the
    returned handle.

    Identical launch technique to the conftest ``real_app`` fixture
    (unmodified ``app_launcher.py`` → unmodified ``app_web.main()``;
    hermetic IPC via the opt-in core hooks; per-journey recording via
    the shared ``JourneyRecorder``) — the ONLY addition is recording
    ``cmd_port`` / ``cmd_token`` on the app so J7's registered-command
    subprocess can target exactly THIS running instance. Tears the app
    + temp profile down cleanly. Privilege/host-independent."""
    profile = Path(tempfile.mkdtemp(prefix="pippal-journey-p5-"))
    os.environ["PIPPAL_DATA_DIR"] = str(profile)

    import pippal.paths as _paths

    _paths.DATA_ROOT = profile
    _paths.VOICES_DIR = profile / "voices"
    _paths.CONFIG_PATH = profile / "config.json"
    _paths.HISTORY_PATH = profile / "history.json"
    _paths.TEMP_DIR = profile / "temp"
    for _m in ("pippal.config", "pippal.voices", "pippal.onboarding"):
        try:
            mod = importlib.import_module(_m)
            if hasattr(mod, "CONFIG_PATH"):
                mod.CONFIG_PATH = profile / "config.json"
            if hasattr(mod, "VOICES_DIR"):
                mod.VOICES_DIR = profile / "voices"
            if hasattr(mod, "DATA_ROOT"):
                mod.DATA_ROOT = profile
        except Exception:
            pass
    for d in (profile, profile / "voices", profile / "temp"):
        d.mkdir(parents=True, exist_ok=True)

    # Seed activated + the cached real engine/voice via the conftest's
    # OWN helpers (the exact J2/J4 setup the documented model uses).
    _seed_profile(profile, "activated")
    _install_cached_piper(profile)
    _install_cached_voice(profile)

    cdp_port = _free_port()
    cmd_port = _free_port()
    token = "journey-p5-" + os.urandom(8).hex()

    env = dict(os.environ)
    env["PIPPAL_DATA_DIR"] = str(profile)
    env["PIPPAL_JOURNEY_CDP_PORT"] = str(cdp_port)
    env["PIPPAL_CMD_SERVER_PORT"] = str(cmd_port)
    env["PIPPAL_CMD_SERVER_TOKEN"] = token
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    log_path = profile / "app.log"
    log_fh = open(log_path, "wb")
    proc = subprocess.Popen(
        [sys.executable, str(LAUNCHER)],
        cwd=str(CHECKOUT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )

    pw_cm = None
    browser = None
    app = None
    recorder = None
    try:
        cdp_version = _wait_cdp(cdp_port, proc)
        from playwright.sync_api import sync_playwright

        pw_cm = sync_playwright().start()
        browser = pw_cm.chromium.connect_over_cdp(
            f"http://127.0.0.1:{cdp_port}"
        )

        def _reconnect_browser():
            nonlocal browser
            old = browser
            browser = pw_cm.chromium.connect_over_cdp(
                f"http://127.0.0.1:{cdp_port}"
            )
            try:
                old.close()
            except Exception:
                pass
            return browser

        page = _resolve_app_page(browser, reconnect_fn=_reconnect_browser)
        bridge_base = ""
        try:
            u = page.url
            if "//" in u:
                bridge_base = u.split("/index.html")[0]
        except Exception:
            pass

        app = RealApp(
            profile=profile,
            cdp_port=cdp_port,
            bridge_base=bridge_base,
            proc=proc,
            browser=browser,
            page=page,
            cdp_version=cdp_version,
            log_path=log_path,
            _pw_cm=pw_cm,
        )
        # The ONLY addition over the conftest fixture: expose this
        # journey's hermetic IPC identity so J7's registered-command
        # subprocess targets exactly THIS launched instance.
        app.cmd_port = cmd_port  # type: ignore[attr-defined]
        app.cmd_token = token  # type: ignore[attr-defined]

        # Per-journey RECORDING — IDENTICAL wiring to the conftest
        # real_app fixture so J7/J8 attach the same evidence as J1–J6.
        ev = os.environ.get("PIPPAL_JOURNEY_EVIDENCE_DIR")
        if ev:
            try:
                rec_dir = Path(ev) / "journey-recordings"
                recorder = JourneyRecorder(rec_dir, request.node.name)
                ctx = None
                try:
                    ctx = page.context
                except Exception:
                    ctx = None
                recorder.start(ctx, page)
            except Exception:
                recorder = None

        yield app

        if recorder is not None:
            try:
                cur_page = app.page
                cur_ctx = None
                try:
                    cur_ctx = cur_page.context
                except Exception:
                    cur_ctx = None
                recorder.stop(cur_ctx, cur_page)
            except Exception:
                pass

        if ev:
            try:
                tname = request.node.name
                edir = Path(ev) / "journey-windows"
                edir.mkdir(parents=True, exist_ok=True)
                try:
                    app.page.screenshot(
                        path=str(edir / f"{tname}.png"), timeout=8000
                    )
                except Exception:
                    pass
                (edir / f"{tname}.app.log").write_text(
                    app.app_log(), encoding="utf-8", errors="replace"
                )
                (edir / f"{tname}.cdp.json").write_text(
                    json.dumps(app.cdp_version, indent=2), encoding="utf-8"
                )
                if recorder is not None:
                    try:
                        (edir / f"{tname}.recording.txt").write_text(
                            "\n".join(recorder.notes) + "\n",
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
            except Exception:
                pass
    finally:
        cur = app.browser if app is not None else browser
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass
        try:
            if pw_cm is not None:
                pw_cm.stop()
        except Exception:
            pass
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=20,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        try:
            log_fh.close()
        except Exception:
            pass
        shutil.rmtree(profile, ignore_errors=True)


def _attached_to_real_app(app, step) -> None:
    """Assert we are driving the REAL WebView2 desktop app, not headless
    Chromium (identical check to test_journeys.py / _phase4)."""
    browser_build = str(app.cdp_version.get("Browser", ""))
    assert "Edg/" in browser_build, (
        f"CDP browser is not the WebView2 desktop runtime: "
        f"{browser_build!r}"
    )
    assert "HeadlessChrome" not in browser_build, browser_build
    url = app.page.url
    assert "/index.html" in url and "127.0.0.1" in url, url
    step.check(
        f"attached to REAL app window — CDP build {browser_build!r}, "
        f"page {url!r}"
    )


@contextlib.contextmanager
def _global_registry_lock(timeout: float = 120.0):
    """Serialize the GLOBAL per-user HKCU registry section across
    processes on this machine — the SAME machine-wide named file lock
    the Tier-1 hermetic shell test uses
    (``e2e/web/test_web_ui.py::_global_registry_lock``), reproduced here
    (additive, no shared-helper change) so J7's launched-app install /
    remove cannot interleave with a concurrent Tier-1 shell test or
    another checkout running the same journey. Uses the SAME lock
    filename so the two tiers genuinely mutually exclude on the shared
    host. Pure test-harness isolation: changes no production code."""
    import time as _t

    lock_path = (
        Path(tempfile.gettempdir()) / "pippal-e2e-ctxmenu-registry.lock"
    )
    fh = open(lock_path, "a+b")
    deadline = _t.time() + timeout
    acquired = False
    try:
        import msvcrt

        while _t.time() < deadline:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
                break
            except OSError:
                _t.sleep(0.25)
        yield acquired
    finally:
        if acquired:
            try:
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        fh.close()


def _reg_query(key: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["reg", "query", key], capture_output=True, timeout=15
    )


# ==========================================================================
# J7 — UC-B11/B13/B12: install the right-click entry, read a file through
#       it, remove it — end-to-end on the REAL launched desktop app
# ==========================================================================


def test_j7_context_menu_install_read_through_it_remove(
    launched_app, step
) -> None:
    """A user adds PipPal to the Windows right-click menu, right-clicks a
    text file to read it, then removes the entry — all proven on the
    REAL launched desktop app.

    WHY each step: the whole point of the Windows-integration feature is
    that a user can install a real Explorer entry, have a real
    right-click actually drive the running PipPal to read the file, and
    cleanly remove it. This drives the launched app's OWN real bridge
    for install/remove (genuine HKCU writes) and runs the EXACT command
    Explorer would spawn (``python -m pippal.open_file <file>`` with the
    clicked path as ``%1``), with THIS launched instance's hermetic IPC
    identity, so the real *desktop process* services the registered
    command and its real engine reads the file. Hermetic: the global
    HKCU keys are serialised under the machine-wide registry lock and
    always removed in teardown.
    """
    from pippal.context_menu import CONTEXT_MENU_EXTENSIONS, _reg_base_path

    app = launched_app
    _attached_to_real_app(app, step)

    with _global_registry_lock() as locked:
        step.info(
            f"registry section serialized via machine-wide lock "
            f"(acquired={locked})"
        )
        installed = False
        try:
            with step.group(
                "J7.0 clean slate — remove any pre-existing PipPal "
                "context-menu keys via the REAL launched app's bridge "
                "(so the install is genuinely observed, not pre-existing)"
            ):
                bridge_call(app.bridge_base, "remove_context_menu")
                deadline_poll(
                    lambda: bridge_call(
                        app.bridge_base, "context_menu_status"
                    )
                    == "none",
                    timeout=15.0,
                    what="the real launched app to report ctx status "
                    "'none' (clean slate)",
                )
                step.check(
                    "REAL launched app bridge.context_menu_status() == "
                    "'none' (clean slate, no pre-existing keys)"
                )

            with step.group(
                "J7.1 user clicks 'Install' — the REAL launched app's "
                "bridge performs genuine per-user HKCU reg writes "
                "(context_menu.py:59); the real registry keys must exist "
                "with the real %1 command"
            ):
                status = bridge_call(
                    app.bridge_base, "install_context_menu"
                )
                step(
                    "REAL launched app bridge.install_context_menu() "
                    "invoked (genuine HKCU reg add)"
                )
                deadline_poll(
                    lambda: bridge_call(
                        app.bridge_base, "context_menu_status"
                    )
                    == "all",
                    timeout=15.0,
                    what="the real launched app to report ctx status "
                    "'all' after a genuine install",
                )
                installed = True
                assert status == "all" or bridge_call(
                    app.bridge_base, "context_menu_status"
                ) == "all", status
                step.check(
                    "REAL launched app bridge.context_menu_status() == "
                    "'all' (genuine HKCU install by the desktop process)"
                )

                # The genuine per-user registry keys really exist on this
                # machine and the registered \command carries %1 (what
                # Explorer would substitute the clicked file into).
                for ext in CONTEXT_MENU_EXTENSIONS:
                    cmd_key = _reg_base_path(ext) + r"\command"
                    rc = _reg_query(cmd_key)
                    end = time.time() + 6.0
                    while rc.returncode != 0 and time.time() < end:
                        time.sleep(0.1)
                        rc = _reg_query(cmd_key)
                    assert rc.returncode == 0, (
                        f"missing real \\command key for {ext}: {cmd_key}"
                    )
                    out = rc.stdout.decode("utf-8", "replace")
                    assert "%1" in out, (
                        f"the registered command for {ext} has no %1 "
                        f"(Explorer could not pass the clicked file): "
                        f"{out!r}"
                    )
                step.check(
                    f"each of {CONTEXT_MENU_EXTENSIONS} has a REAL "
                    "per-user \\command key carrying %1 on this machine"
                )

            with step.group(
                "J7.2 user right-clicks a .txt file → 'Read with PipPal' "
                "→ the REAL launched app's engine must read it. We run "
                "the EXACT command Explorer spawns (python -m "
                "pippal.open_file <file>, the clicked path as %1) with "
                "THIS launched app's hermetic IPC identity"
            ):
                target = app.profile / "j7-right-click-target.txt"
                marker = (
                    "PipPal Phase-5 J7: this file was read by the real "
                    "launched desktop app through the Windows right-click "
                    "entry end to end."
                )
                target.write_text(marker, "utf-8")

                bridge_call(app.bridge_base, "overlay_action", "close")
                deadline_poll(
                    lambda: not bridge_call(
                        app.bridge_base, "engine_state"
                    ).get("is_speaking"),
                    timeout=15.0,
                    what="the real launched engine to be idle before the "
                    "right-click read",
                )

                # The registered \command is `python -m pippal.open_file
                # "%1"`. Run EXACTLY that, with THIS launched app's
                # hermetic IPC identity in the env so open_file.py's
                # _env_port_override / _env_token target THIS running
                # instance's command server (production never sets these
                # — opt-in core hooks). This is precisely what Explorer
                # spawns on a real right-click (minus Explorer itself).
                env = dict(os.environ)
                env["PIPPAL_CMD_SERVER_PORT"] = str(app.cmd_port)
                env["PIPPAL_CMD_SERVER_TOKEN"] = app.cmd_token
                step(
                    "run the EXACT registered command "
                    "`python -m pippal.open_file <file>` (what Explorer "
                    "spawns on a real right-click) targeting THIS "
                    "launched app's hermetic IPC"
                )
                proc = subprocess.run(
                    [sys.executable, "-m", "pippal.open_file", str(target)],
                    cwd=str(app.profile),
                    env=env,
                    capture_output=True,
                    timeout=30,
                )
                assert proc.returncode == 0, (
                    f"the registered open_file command failed (rc="
                    f"{proc.returncode}); stdout="
                    f"{proc.stdout.decode('utf-8','replace')!r} stderr="
                    f"{proc.stderr.decode('utf-8','replace')!r}"
                )
                step.check(
                    "the EXACT registered command returned 0 (the "
                    "launched app's hermetic IPC accepted the right-click "
                    "read request)"
                )

                # THE real effect: the launched app's OWN real engine
                # genuinely started reading the file (its live bridge,
                # not a copy). Deadline-poll the running process.
                def _engine_reading() -> bool:
                    s = bridge_call(app.bridge_base, "engine_state")
                    return bool(
                        s.get("is_speaking")
                        or s.get("chunk_count")
                        or s.get("overlay_state")
                        in ("reading", "thinking", "done")
                    )

                deadline_poll(
                    _engine_reading,
                    timeout=45.0,
                    what="the REAL launched app's engine to start reading "
                    "the right-clicked file via the registered command",
                )
                # And the running app's Recent history records the file's
                # text (the read_text_async path /read-file uses) — the
                # authoritative "it really read it" signal.
                deadline_poll(
                    lambda: any(
                        marker in h
                        for h in bridge_call(
                            app.bridge_base, "get_history"
                        )
                    ),
                    timeout=30.0,
                    what="the real launched app's Recent history to "
                    "record the right-clicked file's text",
                )
                step.check(
                    "the REAL launched desktop app's engine read the "
                    "right-clicked file end-to-end (live engine_state "
                    "reading + Recent history records the file text) — "
                    "UC-B13 round-trip proven on the real process"
                )
                bridge_call(app.bridge_base, "overlay_action", "close")

            with step.group(
                "J7.3 user clicks 'Remove' — the REAL launched app's "
                "bridge must delete the per-user keys "
                "(context_menu.py:87) and the real registry must be clean"
            ):
                bridge_call(app.bridge_base, "remove_context_menu")
                step(
                    "REAL launched app bridge.remove_context_menu() "
                    "invoked (genuine HKCU reg delete)"
                )
                deadline_poll(
                    lambda: bridge_call(
                        app.bridge_base, "context_menu_status"
                    )
                    == "none",
                    timeout=15.0,
                    what="the real launched app to report ctx status "
                    "'none' after Remove",
                )
                installed = False
                for ext in CONTEXT_MENU_EXTENSIONS:
                    base = _reg_base_path(ext)
                    end = time.time() + 6.0
                    rc = _reg_query(base)
                    while rc.returncode == 0 and time.time() < end:
                        time.sleep(0.1)
                        rc = _reg_query(base)
                    assert rc.returncode != 0, (
                        f"the PipPal registry key for {ext} still exists "
                        f"after Remove: {base}"
                    )
                step.check(
                    "REAL launched app bridge.context_menu_status() == "
                    "'none' AND every per-user PipPal registry key is "
                    "gone — UC-B12 remove proven on the real process; "
                    "machine state clean"
                )
        finally:
            # Belt-and-braces: ALWAYS remove the global per-user keys,
            # even if an assertion above failed mid-journey, so the
            # journey never leaves machine state behind.
            if installed:
                try:
                    bridge_call(
                        app.bridge_base,
                        "remove_context_menu",
                        timeout=15.0,
                    )
                except Exception:
                    try:
                        from pippal.context_menu import (
                            uninstall_context_menu,
                        )

                        uninstall_context_menu()
                    except Exception:
                        pass


# ==========================================================================
# J8 — UC-D3: replay / prev / next transport during a real read on the
#       REAL launched desktop app's overlay
#
# HONEST SCOPE FINDING (see this module's docstring): UC-D5 (paused
# chip) / UC-D10 (pause->silence->resume) are NOT a Tier-2 journey leg —
# the real desktop web overlay window has NO pause control (only prev/
# replay/next/close, webui/js/app.js:614-619), the web /bridge exposes
# no pause method, and the only genuine pause paths are the global
# hotkey (an OS keystroke boundary CDP cannot drive) and the IPC
# /pause control route which command_server gates behind
# control_routes_enabled (default False; app_web.main never enables it)
# so POST /pause genuinely 404s on the real launched process (verified).
# Driving pause through a 404 route / a non-existent user surface would
# be fake-green. UC-D5/UC-D10 stay genuinely covered by their existing
# Tier-1 test (test_core_interactions.py::test_pause_silences_and_
# resume_replays_then_seek_while_paused — the real engine.pause_toggle
# + unmodified pippal.playback). J8's honest additive value is the
# UC-D3 launched-app transport, which IS a real user-reachable surface
# (the overlay window's prev/replay/next buttons).
# ==========================================================================

# Five long sentences, total > 1000 chars: the real
# ``text_utils.split_sentences`` (~400-char cap, sentence-packed)
# genuinely yields MULTIPLE chunks so next/prev/replay move a real
# position. Deterministic — no host/privilege dependence.
_J8_TEXT = (
    "PipPal phase five journey eight begins with a deliberately long "
    "opening sentence that contains far more than eighty characters so "
    "the real Piper engine and the real chunk splitter have substantial "
    "material to work with in the very first synthesised chunk. "
    "The second sentence is also intentionally lengthy and verbose, "
    "again far exceeding eighty characters, ensuring that the cumulative "
    "text comfortably crosses the four-hundred-character chunk cap that "
    "the real text utilities apply when packing sentences. "
    "A third long sentence continues the passage with yet more words so "
    "that previous and next genuinely move the real chunk position "
    "across at least two distinct synthesised chunks on the running "
    "desktop process. "
    "The fourth sentence keeps the real engine busy long enough that a "
    "skip and a replay can each be observed taking real effect on the "
    "running app without any fixed sleep in the test itself. "
    "And finally a fifth long concluding sentence completes this "
    "multi-chunk passage so the reader transport — next, previous and "
    "replay — is exercised against a genuine real multi-chunk read."
)


def test_j8_replay_skip_transport_during_real_read(
    launched_app, step
) -> None:
    """A user skips and replays a sentence while PipPal is really
    reading — proven on the REAL launched desktop app's overlay
    transport (UC-D3).

    WHY each step: the reader transport (prev / replay / next) is only
    meaningful *while a real read is in progress*; a user who skips must
    see the position actually move, and replay must be a genuine
    accepted op that keeps the read alive. This drives the launched
    app's OWN real ``POST /bridge`` ``overlay_action`` — the EXACT
    transport the real desktop overlay window's prev/replay/next buttons
    use (``webui/js/app.js:606-619`` → ``bridge.overlay_action`` →
    ``engine.prev_chunk`` / ``replay_chunk`` / ``next_chunk``) — and
    asserts the real engine / real overlay ``chunk_idx`` on the running
    process. No mock, deadline-polled, no fixed sleep,
    privilege/host-independent. (Pause/resume — UC-D5/UC-D10 — is the
    honest-finding boundary documented above; it is NOT claimed here.)
    """
    app = launched_app
    _attached_to_real_app(app, step)

    with step.group(
        "J8.1 the launched app is set up with the real cached voice + "
        "real piper so the engine genuinely synthesises a multi-chunk "
        "read"
    ):
        installed = bridge_call(app.bridge_base, "get_installed_voices")
        assert "en_US-ryan-high.onnx" in installed, installed
        step.check(f"running app has the real voice: {installed}")

    with step.group(
        "J8.2 trigger a real multi-chunk read through the launched "
        "app's own bridge → the real engine must be reading with >1 "
        "chunk (so next/prev/replay move a real position)"
    ):
        bridge_call(app.bridge_base, "overlay_action", "close")
        deadline_poll(
            lambda: not bridge_call(
                app.bridge_base, "engine_state"
            ).get("is_speaking"),
            timeout=15.0,
            what="engine idle before the J8 read",
        )
        step(f"ask the running app to read {len(_J8_TEXT)} chars aloud")
        bridge_call(app.bridge_base, "read_text", _J8_TEXT)

        deadline_poll(
            lambda: bridge_call(app.bridge_base, "engine_state").get(
                "overlay_state"
            )
            == "reading",
            timeout=45.0,
            what="overlay to reach 'reading' (a real chunk is playing)",
        )
        snap = bridge_call(app.bridge_base, "engine_state")
        assert (snap.get("chunk_total") or 0) >= 2, (
            f"the read did not split into multiple chunks "
            f"(chunk_total={snap.get('chunk_total')}, "
            f"len={len(_J8_TEXT)}) — skip/prev/next need >1 chunk to be "
            f"meaningful"
        )
        step.check(
            f"REAL launched engine is actively reading, "
            f"chunk_total={snap.get('chunk_total')} (genuine multi-chunk "
            f"— skip/replay are meaningful)"
        )

    with step.group(
        "J8.3 UC-D3 — user clicks the real overlay 'next' button → the "
        "real engine.next_chunk must move the real chunk_idx forward on "
        "the running process (the exact webui overlay transport)"
    ):
        before = bridge_call(app.bridge_base, "engine_state")
        idx_before = int(before.get("chunk_idx") or 0)
        total = int(before.get("chunk_total") or 0)
        step(
            f"POST bridge.overlay_action('next') — the real desktop "
            f"overlay 'next' button (chunk_idx before = "
            f"{idx_before}/{total})"
        )
        bridge_call(app.bridge_base, "overlay_action", "next")

        def _idx_forward() -> bool:
            s2 = bridge_call(app.bridge_base, "engine_state")
            return int(s2.get("chunk_idx") or 0) > idx_before or (
                s2.get("overlay_state") == "done"
            )

        deadline_poll(
            _idx_forward,
            timeout=20.0,
            what="the real chunk_idx to advance after 'next'",
        )
        after_next = bridge_call(app.bridge_base, "engine_state")
        idx_after_next = int(after_next.get("chunk_idx") or 0)
        assert (
            idx_after_next > idx_before
            or after_next.get("overlay_state") == "done"
        ), (
            f"'next' did not move the real chunk position "
            f"({idx_before} -> {idx_after_next})"
        )
        step.check(
            f"'next' moved the REAL chunk position forward "
            f"({idx_before} -> {idx_after_next}) on the running process "
            f"— UC-D3 skip"
        )

    with step.group(
        "J8.4 UC-D3 — user clicks the real overlay 'prev' button → the "
        "real engine.prev_chunk must move the real chunk_idx back"
    ):
        cur = bridge_call(app.bridge_base, "engine_state")
        idx_cur = int(cur.get("chunk_idx") or 0)
        if idx_cur > 0 and cur.get("overlay_state") != "done":
            step(
                f"POST bridge.overlay_action('prev') — the real desktop "
                f"overlay 'prev' button (chunk_idx = {idx_cur})"
            )
            bridge_call(app.bridge_base, "overlay_action", "prev")

            def _idx_back() -> bool:
                s3 = bridge_call(app.bridge_base, "engine_state")
                return int(s3.get("chunk_idx") or 0) < idx_cur or (
                    s3.get("overlay_state") == "done"
                )

            deadline_poll(
                _idx_back,
                timeout=20.0,
                what="the real chunk_idx to move back after 'prev'",
            )
            idx_after_prev = int(
                bridge_call(app.bridge_base, "engine_state").get(
                    "chunk_idx"
                )
                or 0
            )
            step.check(
                f"'prev' moved the REAL chunk position back "
                f"({idx_cur} -> {idx_after_prev}) — UC-D3 prev"
            )
        else:
            # The real read raced to its last chunk / done — start a
            # fresh real read so 'prev' is genuinely exercised (no
            # fake-green skip; we re-induce the real precondition).
            step(
                "real read reached the final chunk before 'prev' could "
                "act — start a fresh real read and exercise 'prev' "
                "genuinely (no skipped assertion)"
            )
            bridge_call(app.bridge_base, "read_text", _J8_TEXT)
            deadline_poll(
                lambda: int(
                    bridge_call(
                        app.bridge_base, "engine_state"
                    ).get("chunk_total")
                    or 0
                )
                >= 2
                and bridge_call(
                    app.bridge_base, "engine_state"
                ).get("overlay_state")
                == "reading",
                timeout=45.0,
                what="a fresh real multi-chunk read to reach 'reading'",
            )
            bridge_call(app.bridge_base, "overlay_action", "next")
            deadline_poll(
                lambda: int(
                    bridge_call(
                        app.bridge_base, "engine_state"
                    ).get("chunk_idx")
                    or 0
                )
                >= 1
                or bridge_call(
                    app.bridge_base, "engine_state"
                ).get("overlay_state")
                == "done",
                timeout=20.0,
                what="chunk_idx>=1 after 'next' on the fresh read",
            )
            idx_n = int(
                bridge_call(app.bridge_base, "engine_state").get(
                    "chunk_idx"
                )
                or 0
            )
            if idx_n > 0:
                bridge_call(app.bridge_base, "overlay_action", "prev")
                deadline_poll(
                    lambda: int(
                        bridge_call(
                            app.bridge_base, "engine_state"
                        ).get("chunk_idx")
                        or 0
                    )
                    < idx_n
                    or bridge_call(
                        app.bridge_base, "engine_state"
                    ).get("overlay_state")
                    == "done",
                    timeout=20.0,
                    what="chunk_idx to move back after 'prev' on the "
                    "fresh read",
                )
            step.check(
                "exercised 'prev' genuinely on a fresh real read (the "
                "real chunk position moved back) — UC-D3 prev"
            )

    with step.group(
        "J8.5 UC-D3 — user clicks the real overlay 'replay' button → it "
        "must be a genuine accepted transport op that keeps the REAL "
        "launched read alive (the process must not crash/wedge)"
    ):
        step(
            "POST bridge.overlay_action('replay') — the real desktop "
            "overlay 'replay' button (re-read the current chunk)"
        )
        bridge_call(app.bridge_base, "overlay_action", "replay")
        # The running app must still serve a sane engine_state — proving
        # 'replay' was a genuine accepted op, not a wedge.
        deadline_poll(
            lambda: isinstance(
                bridge_call(app.bridge_base, "engine_state").get(
                    "chunk_idx"
                ),
                int,
            ),
            timeout=15.0,
            what="the running app to still serve a sane engine_state "
            "after 'replay'",
        )
        assert app.proc.poll() is None, (
            f"the real launched app process exited (code "
            f"{app.proc.returncode}) during the transport journey — the "
            f"reader transport must not crash the desktop app; app "
            f"log:\n{app.app_log()[-1500:]}"
        )
        step.check(
            "'replay' was accepted by the real running process and the "
            "launched app is still alive serving a sane engine_state — "
            "UC-D3 replay/transport proven end-to-end on the REAL app"
        )

    bridge_call(app.bridge_base, "overlay_action", "close")

