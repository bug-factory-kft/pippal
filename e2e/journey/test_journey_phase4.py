"""PipPal Tier-2 user-journey E2E — Phase-4 resilience journey.

The Core "Phase 4" Tier-2 row of ``docs/USE_CASE_BACKLOG.md``:

* **J6 / UC-B21** — corrupt-``config.json`` ``.bak``-rename recovery as
  a real launched-app journey. A returning user's ``config.json`` got
  corrupted (a truncated/garbled write, a disk glitch). They launch
  PipPal. The real app must **not** lose all settings or crash: the
  real ``pippal.config.load_config`` (``config.py:84-96``) detects the
  parse error, renames the bad file to ``config.json.bak`` (so the user
  can recover it), tells them in stderr, and returns the layered
  defaults — so the **real launched app** comes up cleanly on defaults
  and the ``.bak`` exists on disk.

This is the same two-tier model as ``test_journeys.py`` (J1–J5): a
**real launched** ``app_web.main()`` pywebview/WebView2 desktop window,
attached over CDP and asserted against the *real running process* (its
live ``POST /bridge`` config + its on-disk profile), with a real
per-journey recording artifact (ffmpeg ``.mp4`` / contact-sheet,
exactly as the conftest wires for J1–J5).

WHY a dedicated self-contained launch fixture (additive, no conftest
change): the shared ``real_app`` fixture seeds a profile *first* and
launches *immediately*, with only ``first_run`` / ``activated`` seeds —
there is no hook to pre-write a CORRUPT ``config.json`` before the
launched ``app_web.main()`` runs ``load_config()``, which is exactly
when the real recovery happens. ``corrupt_config_app`` here replicates
the **identical** launch technique the conftest documents (flip on the
WebView2 CDP port via the unmodified ``app_launcher.py`` → the
**unmodified** ``pippal.web_ui.app_web.main()``; hermetic IPC via the
already-landed opt-in ``PIPPAL_CMD_SERVER_*`` core hooks; fresh temp
profile) and reuses the public ``_recording.JourneyRecorder`` for the
evidence artifact, mirroring J1–J5 — it only adds the one missing
ability: write the real corrupt ``config.json`` into the fresh profile
*before* the real app process starts. No production code is modified
(strictly additive — new test file + docs only). The seam is purely
profile *content* (a corrupt file on disk), identical for any caller —
privilege/host-independent.
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Reuse the journey package's own launch primitives + recorder (same
# directory; the journey conftest puts its dir on sys.path so the plain
# modules import cleanly regardless of pytest's rootdir — the same rule
# _journey_helpers / _recording rely on). The journey *conftest* is not
# importable by bare name (``from conftest import`` resolves to the
# PARENT e2e/conftest.py under pytest's conftest model), so load THIS
# directory's conftest explicitly by file path and reuse its documented
# launch helpers — additive, no conftest change.
from _journey_helpers import bridge_call, config_on_disk, deadline_poll
from _recording import JourneyRecorder

_JCONF_PATH = Path(__file__).resolve().parent / "conftest.py"
_spec = _ilu.spec_from_file_location("_journey_conftest_p4", _JCONF_PATH)
_jconf = _ilu.module_from_spec(_spec)
# Register before exec so the @dataclass RealApp's KW_ONLY processing
# can resolve its own module via sys.modules (stdlib dataclasses does
# ``sys.modules.get(cls.__module__).__dict__``).
sys.modules["_journey_conftest_p4"] = _jconf
_spec.loader.exec_module(_jconf)

CHECKOUT = _jconf.CHECKOUT
LAUNCHER = _jconf.LAUNCHER
RealApp = _jconf.RealApp
_free_port = _jconf._free_port
_resolve_app_page = _jconf._resolve_app_page
_wait_cdp = _jconf._wait_cdp

pytestmark = pytest.mark.journey


# A deliberately CORRUPT config.json: not valid JSON at all, so the real
# ``json.loads`` in ``pippal.config.load_config`` genuinely raises and
# the real recovery (.bak rename + layered defaults) genuinely runs. It
# also carries a recognisable marker so we can prove the EXACT bytes the
# user had were preserved into the .bak (not silently destroyed).
_CORRUPT_MARKER = "PIPPAL-UC-B21-CORRUPT-MARKER"
_CORRUPT_CONFIG_BYTES = (
    '{ "engine": "piper", "voice": "broken'  # unterminated string / object
    + f' {_CORRUPT_MARKER} <<< not valid JSON >>> \x00\x01\x02'
).encode("utf-8", "surrogatepass")


@pytest.fixture
def corrupt_config_app(request: pytest.FixtureRequest) -> Iterator[RealApp]:
    """Launch ONE fresh REAL PipPal desktop app whose profile already
    contains a CORRUPT ``config.json`` (written before the process
    starts, so the real ``load_config`` recovery genuinely runs at
    launch).

    Identical launch technique to the conftest ``real_app`` fixture
    (unmodified ``app_launcher.py`` → unmodified ``app_web.main()``;
    hermetic IPC via the opt-in core hooks; per-journey recording via
    the shared ``JourneyRecorder``) — the ONLY addition is the
    pre-launch corrupt-config write. Tears the app + temp profile down
    cleanly. Privilege/host-independent: the seam is just a file's
    bytes under a fresh temp dir."""
    profile = Path(tempfile.mkdtemp(prefix="pippal-journey-ucb21-"))
    os.environ["PIPPAL_DATA_DIR"] = str(profile)

    # Re-point the few path constants the pytest-process helpers touch
    # (the launched subprocess reads PIPPAL_DATA_DIR fresh, so it is
    # already correct there) — mirrors the conftest real_app fixture.
    import importlib

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

    # ---- THE Phase-4 seam: a REAL corrupt config.json on disk BEFORE
    #      the real app process starts (so the real load_config recovery
    #      genuinely runs during the real launch). Pure profile content;
    #      no production code touched.
    config_path = profile / "config.json"
    config_path.write_bytes(_CORRUPT_CONFIG_BYTES)

    cdp_port = _free_port()
    cmd_port = _free_port()
    token = "journey-ucb21-" + os.urandom(8).hex()

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
        page = _resolve_app_page(browser)
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

        # ---- Per-journey RECORDING (best-effort, never fails the
        # journey) — IDENTICAL wiring to the conftest real_app fixture
        # so UC-B21 attaches the same real evidence artifact as J1–J5.
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


def _attached_to_real_app(app: RealApp, step) -> None:
    """Assert we are driving the REAL desktop app, not headless Chromium
    (identical check to test_journeys.py's helper)."""
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


# ==========================================================================
# J6 — UC-B21: corrupt-config.json .bak-rename recovery (real launched app)
# ==========================================================================


def test_j6_corrupt_config_recovers_to_defaults_and_bak(
    corrupt_config_app, step
) -> None:
    """A returning user's ``config.json`` got corrupted. They launch
    PipPal — it must NOT crash or silently destroy their file: the real
    app comes up on the layered defaults and the corrupt file is
    preserved as ``config.json.bak`` so they can recover it.

    WHY each step: a real user whose config file is damaged (a power
    loss mid-write, a disk glitch) must still get a *working* PipPal,
    must not have their (possibly partially-recoverable) file silently
    deleted, and must not be shown a crash — that is the entire point of
    the ``load_config`` recovery (``config.py:84-96``). This asserts the
    REAL launched app's live config + its on-disk profile, not a mock.
    """
    app = corrupt_config_app
    _attached_to_real_app(app, step)

    profile: Path = app.profile
    config_path = profile / "config.json"
    bak_path = profile / "config.json.bak"

    with step.group(
        "J6.1 the real app launched at all — it did NOT crash on the "
        "corrupt config (a damaged file must never brick PipPal)"
    ):
        # Reaching _attached_to_real_app already proves the real
        # app_web.main() got past load_config() and rendered a real
        # window. Make the liveness explicit against the real process.
        assert app.proc.poll() is None, (
            f"the real app process exited (code {app.proc.returncode}) "
            f"— a corrupt config.json must NOT crash the launch; "
            f"app log:\n{app.app_log()[-2000:]}"
        )
        step.check(
            "the REAL launched app process is alive and rendered a real "
            "window despite the corrupt config.json (no crash)"
        )

    with step.group(
        "J6.2 the real load_config recovery renamed the corrupt file to "
        "config.json.bak (the user's bytes are preserved, not destroyed)"
    ):
        # The real load_config (config.py:89-91) does
        # path.replace(path + '.bak') on a parse error. Deadline-poll
        # the REAL on-disk profile (no fixed sleep).
        deadline_poll(
            lambda: bak_path.exists(),
            timeout=30.0,
            what="config.json.bak created by the real load_config "
                 "recovery",
        )
        assert bak_path.exists(), (
            f"config.json.bak was not created — the real load_config "
            f"recovery (config.py:89-91) did not run; "
            f"profile listing: {sorted(p.name for p in profile.iterdir())}"
        )
        # The .bak holds the user's EXACT original corrupt bytes (the
        # real recovery renames, it does not rewrite/sanitise) — so they
        # really can recover it.
        bak_bytes = bak_path.read_bytes()
        assert _CORRUPT_MARKER.encode() in bak_bytes, (
            "config.json.bak does not contain the user's original "
            "bytes — the recovery must PRESERVE the file, not "
            "regenerate it"
        )
        assert bak_bytes == _CORRUPT_CONFIG_BYTES, (
            "config.json.bak is not a byte-for-byte copy of the user's "
            "original corrupt file — the recovery must rename, not "
            "rewrite"
        )
        step.check(
            "REAL config.json.bak exists on disk and is a byte-for-byte "
            "copy of the user's original corrupt file "
            "(config.py:89-91) — their data is preserved, recoverable"
        )

    with step.group(
        "J6.3 the real app is running on the LAYERED DEFAULTS — the "
        "corrupt override did NOT leak into the live config"
    ):
        # The running app's OWN live config, read via the same real
        # POST /bridge transport the desktop UI uses (not a copy).
        live_cfg = bridge_call(app.bridge_base, "get_config")
        defaults = bridge_call(app.bridge_base, "get_defaults")
        assert isinstance(live_cfg, dict) and live_cfg, (
            f"the real bridge returned no live config: {live_cfg!r}"
        )
        # Every key the corrupt file tried to set must equal the real
        # layered default (recovery returned dict(defaults), not the
        # garbled data). 'voice' is the recognisable corrupt key.
        assert live_cfg.get("voice") == defaults.get("voice"), (
            f"the live 'voice' is {live_cfg.get('voice')!r}, not the "
            f"layered default {defaults.get('voice')!r} — the corrupt "
            f"config leaked into the running app"
        )
        assert live_cfg.get("engine") == defaults.get("engine"), (
            f"live 'engine'={live_cfg.get('engine')!r} != default "
            f"{defaults.get('engine')!r}"
        )
        # The corrupt marker must appear NOWHERE in the live config.
        assert _CORRUPT_MARKER not in json.dumps(live_cfg), (
            f"the corrupt marker leaked into the live config: "
            f"{live_cfg!r}"
        )
        step.check(
            "the REAL running app's live config equals the layered "
            "defaults (corrupt 'voice'/'engine' did NOT leak; the "
            "marker is absent) — load_config returned dict(defaults)"
        )

    with step.group(
        "J6.4 no corrupt config.json remains in place — only the "
        "recovered .bak (a fresh save would write clean defaults-only)"
    ):
        # After the real recovery, config.json was renamed AWAY. The app
        # may or may not have re-persisted (it only writes on a real
        # Save); whatever is at config.json now must NOT be the corrupt
        # bytes — the user is never silently left on a broken file.
        if config_path.exists():
            now_bytes = config_path.read_bytes()
            assert now_bytes != _CORRUPT_CONFIG_BYTES, (
                "config.json is STILL the original corrupt bytes — the "
                "recovery did not move it out of the way"
            )
            assert _CORRUPT_MARKER.encode() not in now_bytes, (
                "the corrupt marker is still in config.json — recovery "
                "did not replace/remove the bad file"
            )
            # If it exists it must be valid JSON (a real clean rewrite).
            parsed = json.loads(now_bytes.decode("utf-8"))
            assert isinstance(parsed, dict), parsed
            assert _CORRUPT_MARKER not in json.dumps(parsed)
            on_disk_note = "config.json was cleanly rewritten (valid JSON)"
        else:
            on_disk_note = (
                "config.json is absent (renamed to .bak; the app runs "
                "on in-memory defaults until a real Save)"
            )
        # Cross-check via the helper the other journeys use.
        disk_cfg = config_on_disk(profile)
        assert _CORRUPT_MARKER not in json.dumps(disk_cfg), disk_cfg
        step.check(
            f"no corrupt config.json remains — {on_disk_note}; the user "
            f"is on a working PipPal with their original file safe in "
            f".bak (UC-B21 proven on the REAL launched app)"
        )
