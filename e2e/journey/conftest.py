"""Pytest fixtures for the PipPal **Tier-2 user-journey** suite.

==========================================================================
TWO-TIER MODEL — why this package exists separately from e2e/web
==========================================================================

* **Tier-1 (``e2e/web``)** — per-control real-effect E2E driven in
  *served / headless* mode (a local server + headless Chromium + the
  real ``/bridge`` backend). It is the **per-PR merge gate**
  (``ui-web-e2e.yml`` → required check *Web UI E2E (served, headless
  Chromium)*). It is fast, deterministic, runnable on the Session-0 CI
  runner, and is **not** modified by this package.

* **Tier-2 (this package, ``e2e/journey``)** — genuine *user-journey /
  use-case* tests that drive the **actually launched desktop app**: a
  real ``reader_app_web.py`` process, a real pywebview **WebView2**
  window appearing in the interactive logged-in session, attached to
  by Playwright over the Chrome DevTools Protocol and driven with real
  clicks / keystrokes on the real window. Each journey is framed by
  *why the user activates each control* and asserts a **real effect**
  at every step (disk / engine / state / overlay / history). It is the
  **release / journey lane**, run on-demand by the logged-in user (or a
  user-session scheduled task) via ``e2e/journey/run-journey.ps1`` — it
  CANNOT run on the Session-0 CI runner, which has no visible desktop.

==========================================================================
HOW A JOURNEY DRIVES THE REAL WINDOW
==========================================================================

``real_app`` (the per-journey fixture) does, per journey:

1. allocate a fresh isolated ``PIPPAL_DATA_DIR`` temp profile (first-run
   journeys: NOT pre-seeded, so the real app shows its real onboarding
   surface; "already set up" journeys: pre-seeded via the ``seed=``
   request param);
2. allocate a free TCP port for the WebView2 CDP endpoint and a free
   port + random token for the hermetic IPC command server (the
   already-landed opt-in ``PIPPAL_CMD_SERVER_PORT`` /
   ``PIPPAL_CMD_SERVER_TOKEN`` core hooks — production never sets them,
   so ``command_server.py`` / ``open_file.py`` behaviour is unchanged);
3. spawn ``e2e/journey/app_launcher.py`` (a test-only shim that flips on
   ``webview.settings['REMOTE_DEBUGGING_PORT']`` and then calls the
   **unmodified** ``pippal.web_ui.app_web.main()``) as a fresh
   subprocess with that environment, from THIS checkout (its own
   ``src`` — never a globally installed pippal);
4. deadline-poll the CDP ``/json/version`` endpoint, then Playwright
   ``chromium.connect_over_cdp`` and attach to the real pywebview page;
5. assert it really is the **real app** window (not headless): the CDP
   browser build string is ``Edg/...`` (the WebView2 runtime; headless
   Chromium reports ``HeadlessChrome``), the page URL is the app's
   ``http://127.0.0.1:<bridge>/index.html?view=...`` and the live DOM
   carries the app's ``#brand-name`` / ``data-ready`` markers;
6. yield a small ``RealApp`` handle (the connected page + helpers);
7. tear the app down cleanly (terminate the process tree, close the
   Playwright connection, delete the temp profile).

Journeys are independent and order-independent — every journey is its
own fresh real app instance + fresh profile.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_THIS_DIR = Path(__file__).resolve().parent
CHECKOUT = Path(__file__).resolve().parents[2]
LAUNCHER = _THIS_DIR / "app_launcher.py"

# Make the journey package dir importable so test modules can
# ``from _journey_helpers import ...`` regardless of pytest's rootdir.
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Make THIS checkout's src importable in the pytest process too, so the
# fixtures can use the real pippal.onboarding to pre-seed a profile with
# the exact schema the launched app's loader expects.
_SRC = CHECKOUT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ==========================================================================
# Human-readable step logging (mirrors e2e/web/conftest.py so a passing
# journey run narrates exactly what the real flow did).
# ==========================================================================

_STEP_LOG = logging.getLogger("e2e.journey.step")


class _StepLogger:
    """Concise per-journey step recorder.

    ``step("...")`` logs a user ACTION (``→``) with the *why*;
    ``step.check("...")`` logs an asserted REAL effect (``✓``);
    ``step.group("...")`` brackets a multi-step journey leg.
    """

    def __init__(self, log: logging.Logger, nodeid: str) -> None:
        self._log = log
        self._nodeid = nodeid
        self._depth = 0

    def _emit(self, mark: str, msg: str) -> None:
        indent = "  " * (self._depth + 1)
        self._log.info("%s%s %s", indent, mark, msg)

    def __call__(self, msg: str) -> None:
        self._emit("→", msg)

    def check(self, msg: str) -> None:
        self._emit("✓", msg)

    def info(self, msg: str) -> None:
        self._emit(" ", msg)

    class _Group:
        def __init__(self, outer: _StepLogger, msg: str) -> None:
            self._outer = outer
            self._msg = msg

        def __enter__(self) -> None:
            self._outer._emit("→", self._msg)
            self._outer._depth += 1

        def __exit__(self, *exc: object) -> None:
            self._outer._depth -= 1

    def group(self, msg: str) -> _StepLogger._Group:
        return _StepLogger._Group(self, msg)


@pytest.fixture
def step(request: pytest.FixtureRequest) -> _StepLogger:
    logger = _StepLogger(_STEP_LOG, request.node.nodeid)
    logger.info(f"start {request.node.name}")
    return logger


def pytest_configure(config: pytest.Config) -> None:
    """Scope the step-log formatting to the journey run ONLY.

    This conftest is loaded *only* when pytest collects ``e2e/journey``
    (the default ``pytest`` runs ``tests/`` and never imports this
    file), so configuring the live-log format here cannot affect the
    default suite or the Tier-1 ``e2e/web`` suite.
    """
    config.option.log_cli_format = "%(message)s"
    config.option.log_cli_date_format = "%H:%M:%S"
    if not config.getoption("log_cli_level"):
        config.option.log_cli_level = "INFO"
    config.addinivalue_line(
        "markers", "journey: a Tier-2 real-launched-app user-journey test"
    )


@pytest.fixture(scope="session", autouse=True)
def require_live_windows() -> None:
    """Override the parent ``e2e/conftest.py`` Tk-live gate.

    That gate is for the Tk live-desktop suite. The journey suite has
    its own requirement: a Windows host with a *visible* interactive
    session (a real pywebview WebView2 window must be able to appear).
    It does NOT need ``PIPPAL_E2E_LIVE``; the runner script sets the
    journey-specific opt-in instead.
    """
    if sys.platform != "win32":
        pytest.skip("Tier-2 journeys drive the real Windows desktop app")
    if os.environ.get("PIPPAL_JOURNEY_LIVE") != "1":
        pytest.skip(
            "set PIPPAL_JOURNEY_LIVE=1 or run e2e/journey/run-journey.ps1 "
            "(Tier-2 needs a visible interactive desktop session)"
        )
    return None


# ==========================================================================
# Real launched-app harness
# ==========================================================================


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _seed_profile(profile: Path, seed: str) -> None:
    """Pre-seed a profile for an "already set up" journey.

    ``seed='first_run'`` (default) → leave the profile EMPTY: the real
    app then shows its genuine first-run onboarding surface (no
    activation marker, no voice).

    ``seed='activated'`` → write a *complete* ``first_run_activation``
    via the real ``pippal.onboarding`` so the schema matches the
    launched app's loader and onboarding is NOT force-shown.
    """
    if seed == "first_run":
        return
    if seed == "activated":
        from pippal.onboarding import (
            FirstRunActivationState,
            activation_state_path,
            save_activation_state,
        )

        save_activation_state(
            FirstRunActivationState(
                completed_at="2026-01-01T00:00:00Z",
                completed_with="sample",
                last_failure=None,
            ),
            path=activation_state_path(profile),
        )
        return
    raise ValueError(f"unknown profile seed: {seed!r}")


def _install_cached_piper(profile: Path) -> Path:
    """Make the launched real app find a REAL piper engine.

    The launched app resolves ``PIPER_EXE`` as
    ``INSTALL_ROOT/piper/piper.exe`` where ``INSTALL_ROOT`` is the
    source checkout root (it is a source layout). It has no env
    override, so to give a journey a real engine without modifying
    production code we copy the locally-cached real piper runtime into
    THIS checkout's ``piper/`` directory once. The bytes are the
    genuine Rhasspy piper.exe + its DLLs / espeak data — a real
    out-of-process synth, not a stub.
    """
    src = Path(r"C:\Users\tigyi\piper-repro\piper")
    dst = CHECKOUT / "piper"
    if not (dst / "piper.exe").exists():
        if not (src / "piper.exe").exists():
            raise RuntimeError(
                f"cached piper runtime not found at {src}; J2/J3 "
                "read-aloud journeys need a real engine"
            )
        shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst / "piper.exe"


def _install_cached_voice(profile: Path) -> str:
    """Copy the locally-cached real ``en_US-ryan-high`` voice into the
    fresh profile's voices dir so a read-aloud journey synthesises with
    a REAL voice without paying a ~120 MB download every run (J1 still
    does ONE genuine real download of the smallest catalogue voice to
    prove the install path)."""
    from pippal.paths import VOICES_DIR

    src_dir = Path(r"C:\Users\tigyi\piper-repro\voices")
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    name = "en_US-ryan-high.onnx"
    for fn in (name, f"{name}.json"):
        s = src_dir / fn
        if not s.exists():
            raise RuntimeError(f"cached voice file missing: {s}")
        shutil.copy2(s, VOICES_DIR / fn)
    return name


@dataclass
class RealApp:
    """Handle to the running real PipPal desktop app + its driven page."""

    profile: Path
    cdp_port: int
    bridge_base: str
    proc: subprocess.Popen
    browser: Any
    page: Any
    cdp_version: dict
    log_path: Path
    _pw_cm: Any = field(repr=False)

    def app_log(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    def _all_pages(self) -> list:
        pages = []
        for ctx in self.browser.contexts:
            for pg in ctx.pages:
                try:
                    url = pg.url
                except Exception:
                    continue
                if not url or url == "about:blank":
                    continue
                pages.append(pg)
        return pages

    def _reconnect(self) -> None:
        """Drop and re-establish the Playwright CDP connection.

        Each pywebview window is its OWN CDP ``page`` target on the
        SAME WebView2 browser endpoint. Playwright's
        ``connect_over_cdp`` snapshots the target set at connect time
        and does not surface windows the real app opened *after* that
        — but a FRESH ``connect_over_cdp`` to the same endpoint
        enumerates *all* current real windows. Reconnecting is
        therefore how we follow the user opening a second real window
        (proven directly: a re-connect lists both the onboarding and
        the freshly-opened Voices window). We are still driving the
        genuine pywebview windows of the launched app — only the
        client-side CDP attachment is refreshed.
        """
        old = self.browser
        try:
            self.browser = self._pw_cm.chromium.connect_over_cdp(
                f"http://127.0.0.1:{self.cdp_port}"
            )
        finally:
            try:
                if old is not None:
                    old.close()
            except Exception:
                pass

    def reattach_page(self, view_hint: str | None = None, timeout: float = 20.0):
        """Re-resolve the live page after the app opened a NEW real
        window (e.g. the user clicked "Open Voice Manager" and the real
        app created a second pywebview window). Returns the page whose
        URL matches ``view=<view_hint>`` (or the newest live page).

        Reconnects the CDP client each poll so a window the real app
        opened after the initial connect is discovered (see
        ``_reconnect``).
        """
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            pages = self._all_pages()
            if view_hint:
                # Prefer the NEWEST window for this view (CDP lists the
                # most-recently-created target last) so a close+reopen
                # attaches to the fresh window, not a stale earlier one.
                matches = [
                    pg for pg in pages if f"view={view_hint}" in (pg.url or "")
                ]
                if matches:
                    self.page = matches[-1]
                    return self.page
            elif pages:
                self.page = pages[-1]
                return self.page
            if pages:
                last = pages[-1]
            # Refresh the CDP attachment to pick up new real windows.
            try:
                self._reconnect()
            except Exception:
                pass
            time.sleep(0.4)
        if view_hint is None and last is not None:
            self.page = last
            return last
        raise AssertionError(
            f"no live app page found (view_hint={view_hint!r})"
        )


def _wait_cdp(port: int, proc: subprocess.Popen, timeout: float = 75.0) -> dict:
    """Deadline-poll the WebView2 CDP ``/json/version`` until the real
    window's DevTools endpoint is up (or the app process died)."""
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(
                f"real app exited early (code {proc.returncode}) before "
                f"the CDP endpoint came up on :{port}"
            )
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=1.5
            ) as r:
                return json.loads(r.read())
        except Exception as exc:  # not up yet
            last_err = exc
            time.sleep(0.4)
    raise AssertionError(
        f"WebView2 CDP endpoint never came up on :{port} within "
        f"{timeout}s (last error: {last_err})"
    )


def _resolve_app_page(
    browser: Any,
    timeout: float = 25.0,
    *,
    reconnect_fn: Any | None = None,
    reconnect_every: float = 3.0,
):
    """Find the real pywebview app page among the CDP contexts.

    pywebview/WebView2 windows that are created AFTER the initial
    ``connect_over_cdp`` call are NOT automatically discovered via CDP
    events in WebView2 (unlike stock Chromium). A periodic fresh
    ``connect_over_cdp`` is the only reliable way to pick them up.

    ``reconnect_fn`` is an optional no-arg callable that returns a fresh
    browser object (and closes the old one). When provided, this function
    reconnects every ``reconnect_every`` seconds so newly-created windows
    appear even if they were opened after the first connect-over-CDP
    snapshot.
    """
    deadline = time.time() + timeout
    next_reconnect = time.time() + reconnect_every
    last = None
    while time.time() < deadline:
        for ctx in browser.contexts:
            for pg in ctx.pages:
                try:
                    url = pg.url
                except Exception:
                    continue
                if "index.html" in (url or ""):
                    return pg
                if url and url != "about:blank":
                    last = pg
        # Reconnect to discover WebView2 windows created after the
        # initial connect (WebView2 does not push Target.targetCreated
        # events to an existing Playwright CDP session the same way
        # stock Chromium does — a fresh connect enumerates all targets).
        if reconnect_fn is not None and time.time() >= next_reconnect:
            try:
                browser = reconnect_fn()
            except Exception:
                pass
            next_reconnect = time.time() + reconnect_every
        time.sleep(0.3)
    if last is not None:
        return last
    raise AssertionError("no app page exposed over CDP")


@pytest.fixture
def real_app(request: pytest.FixtureRequest) -> Iterator[RealApp]:
    """Launch ONE fresh real PipPal desktop app for THIS journey.

    Parametrise via ``@pytest.mark.parametrize`` or an indirect marker
    using ``request.param`` keys:

    * ``seed``: ``'first_run'`` (default — empty profile, real
      onboarding shows) or ``'activated'`` (activation pre-seeded).
    * ``with_piper``: ``True`` to copy the cached real piper into the
      checkout so the engine can really synthesise.
    * ``with_voice``: ``True`` to copy the cached real
      ``en_US-ryan-high`` voice into the fresh profile.
    """
    param: dict[str, Any] = getattr(request, "param", {}) or {}
    seed = param.get("seed", "first_run")
    with_piper = bool(param.get("with_piper", False))
    with_voice = bool(param.get("with_voice", False))

    profile = Path(tempfile.mkdtemp(prefix="pippal-journey-"))
    os.environ["PIPPAL_DATA_DIR"] = str(profile)
    # The pippal.paths in THIS pytest process derived DATA_ROOT at
    # import from whatever env existed then; re-point the few constants
    # the seed/voice helpers touch so they write into THIS profile. The
    # launched subprocess reads PIPPAL_DATA_DIR fresh, so it is already
    # correct there.
    import importlib

    import pippal.paths as _paths

    _paths.DATA_ROOT = profile
    _paths.VOICES_DIR = profile / "voices"
    _paths.CONFIG_PATH = profile / "config.json"
    _paths.HISTORY_PATH = profile / "history.json"
    _paths.TEMP_DIR = profile / "temp"
    for _m in ("pippal.voices", "pippal.onboarding"):
        try:
            mod = importlib.import_module(_m)
            if hasattr(mod, "VOICES_DIR"):
                mod.VOICES_DIR = profile / "voices"
            if hasattr(mod, "DATA_ROOT"):
                mod.DATA_ROOT = profile
        except Exception:
            pass
    for d in (profile, profile / "voices", profile / "temp"):
        d.mkdir(parents=True, exist_ok=True)

    _seed_profile(profile, seed)
    if with_piper:
        _install_cached_piper(profile)
    if with_voice:
        _install_cached_voice(profile)

    cdp_port = _free_port()
    cmd_port = _free_port()
    token = "journey-" + os.urandom(8).hex()

    env = dict(os.environ)
    env["PIPPAL_DATA_DIR"] = str(profile)
    env["PIPPAL_JOURNEY_CDP_PORT"] = str(cdp_port)
    # Hermetic IPC (already-landed opt-in core hooks; production never
    # sets these so command_server.py / open_file.py are unchanged).
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
        # Derive the bridge base from the live app URL (the real app
        # picked its own OS-assigned bridge port).
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
        # journey): a Playwright trace (works over connect_over_cdp —
        # the closest thing to a recording the CDP-attach mode allows)
        # PLUS a real screen/window video (ffmpeg gdigrab if present,
        # else a periodic page.screenshot grabber assembled into a .mp4
        # / dense contact-sheet). See _recording.py for the honest
        # connect_over_cdp limitation that motivates this design.
        recorder = None
        ev = os.environ.get("PIPPAL_JOURNEY_EVIDENCE_DIR")
        if ev:
            try:
                from _recording import JourneyRecorder

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

        # Stop the recording against the CURRENT page (the journey may
        # have re-attached to a newer real window) before dropping the
        # rest of the evidence.
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

        # ---- Per-journey evidence: a real screenshot of the live
        # desktop window + the launched app's own log, dropped under
        # the runner's evidence dir (proves a real window was driven).
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
        # app.browser may have been swapped by reattach_page's
        # reconnect; close whichever is current.
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
        # Terminate the real app process tree.
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
