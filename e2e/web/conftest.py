"""Pytest fixtures for the PipPal web-UI Playwright suite.

==========================================================================
PER-TEST APP RESET — why this file is structured the way it is
==========================================================================

This project previously suffered FALSE-POSITIVE passes: the suite shared
ONE session-scoped temp profile + ONE long-lived server/engine/config
across every test, so persisted ``config.json`` / installed-voice / engine
state bled between tests. A test could pass only because a *previous*
test left the right state behind, and test order changed the result.

This conftest structurally prevents that. **Every test runs against a
freshly reset application:**

* ``fresh_profile`` — a brand-new, empty ``PIPPAL_DATA_DIR`` temp dir is
  created *per test* and the path constants every backend module bound at
  import (``pippal.paths`` + the ``from ..paths import VOICES_DIR`` style
  copies in ``config`` / ``voices`` / ``history`` / ``onboarding`` /
  ``web_ui.bridge`` / ``ui.voice_manager`` / ``engines.piper``) are
  re-pointed into it. The previous test's temp dir is torn down. Nothing
  on disk survives a test boundary.

* The profile is **pre-seeded**: ``first_run_activation.json`` is written
  as *complete* so the onboarding "ready" surface is deterministic
  (``is_complete`` true) regardless of what an earlier onboarding test
  did. No ``config.json`` is written, so the backend starts from the
  pure layered defaults — a known baseline.

* ``backend`` — a **fresh** ``TTSEngine`` + ``WebOverlay`` +
  ``PipPalBridge`` + ``start_web_ui_server`` (a NEW OS-assigned port) is
  built *per test* from that clean profile, and torn down (``server
  .shutdown()``, ``engine.stop()``) at test end. No engine/overlay/config
  object is ever reused between tests.

* ``assert_fresh_baseline`` (autouse) asserts the known-fresh baseline at
  the START of every test: temp profile is the active data root, NO
  ``config.json`` on disk, NO installed voices, the live config equals the
  layered defaults for the keys the suite mutates, the engine is idle and
  unspoken, history empty, overlay idle. If config bled in, the test
  ERRORS here instead of silently passing on stale state.

Tests are therefore independent and order-independent: run the whole
file, a single test, or ``-p no:randomly`` in any order — each starts
from the same guaranteed-clean state.

The suite still drives the REAL static UI (``webui/``) served by the
REAL bridge server (:mod:`pippal.web_ui.server`) wired to the REAL
:class:`pippal.engine.TTSEngine` and config — Playwright talks to the
served UI exactly the way the desktop webview does (``api.js`` falls
back to ``POST /bridge`` when the pywebview bridge object is absent), so
these are true end-to-end tests against the migrated frontend, not a
mock. Only the data directory is redirected to a per-test temp profile.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import secrets
import shutil
import sys
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


# ==========================================================================
# HUMAN-READABLE STEP LOGGING — make a passing run say what it actually did
# ==========================================================================
#
# Previously a green CI run showed only "Passed ... no log output
# captured" per test — you could not tell what the test exercised. Every
# e2e/web test now narrates its meaningful actions/assertions through a
# tiny ``step`` logger on the stdlib ``logging`` module (so pytest
# captures it and ``--log-cli-level=INFO`` streams it live in CI, per
# passing test, via ``-rA``).
#
# Usage in a test (the ``step`` fixture is function-scoped):
#
#     step("open Settings")                 -> "  → open Settings"
#     step.check("config.auto_hide_ms == 2400")
#                                            -> "  ✓ config.auto_hide_ms == 2400"
#     with step.group("read-aloud 'hello'"): ...   (logs enter/leave)
#
# This is pure observability: it changes NO backend / UI behaviour and
# does not touch the default ``tests/`` suite (this conftest is only
# loaded for ``e2e/web``; the verbose/log CLI flags are passed by the
# workflow command, never by the root ``pytest.ini``).

_STEP_LOG = logging.getLogger("e2e.web.step")


class _StepLogger:
    """A concise, human-readable step recorder bound to one test.

    ``step("...")`` logs an action line (``→``); ``step.check("...")``
    logs an assertion/observation line (``✓``); ``step.group("...")``
    is a context manager that brackets a multi-step action.
    """

    def __init__(self, log: logging.Logger, nodeid: str) -> None:
        self._log = log
        self._nodeid = nodeid
        self._depth = 0

    def _emit(self, mark: str, msg: str) -> None:
        indent = "  " * (self._depth + 1)
        self._log.info("%s%s %s", indent, mark, msg)

    def __call__(self, msg: str) -> None:
        """Log a meaningful ACTION the test performs (``→``)."""
        self._emit("→", msg)

    def check(self, msg: str) -> None:
        """Log an ASSERTION / observed real effect (``✓``)."""
        self._emit("✓", msg)

    def info(self, msg: str) -> None:
        """Log a neutral note (no arrow)."""
        self._emit(" ", msg)

    @contextlib.contextmanager
    def group(self, msg: str) -> Iterator[None]:
        self._emit("→", msg)
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1


@pytest.fixture
def step(request: pytest.FixtureRequest) -> _StepLogger:
    """Per-test human-readable step logger (see the block above).

    Logged via stdlib ``logging`` so pytest captures it; the workflow
    runs the suite with ``--log-cli-level=INFO -rA -v`` so EVERY passing
    test prints its step lines in the CI log.
    """
    logger = _StepLogger(_STEP_LOG, request.node.nodeid)
    logger.info(f"start {request.node.name}")
    return logger


def pytest_configure(config: pytest.Config) -> None:
    """Scope the step-log formatting to the e2e/web run ONLY.

    This conftest is loaded *only* when pytest collects ``e2e/web``
    (the default ``python -m pytest`` runs ``tests/`` and never imports
    this file), so configuring the live-log format here cannot affect
    the default suite. We only set a terse formatter and a sane default
    level if the CLI did not already pin one — the workflow passes
    ``--log-cli-level=INFO -rA -v`` so every PASSING test's step lines
    show in the CI log (``-rA`` prints captured output for passes too).
    """
    # A compact live-log format: just the message (the step lines are
    # already self-describing — "  → open Settings"). Only applied for
    # this (e2e/web) session.
    config.option.log_cli_format = "%(message)s"
    config.option.log_cli_date_format = "%H:%M:%S"
    # Provide a default if the invoker did not pass --log-cli-level so a
    # bare ``pytest e2e/web`` locally is already informative; the
    # workflow still passes it explicitly for clarity.
    if not config.getoption("log_cli_level"):
        config.option.log_cli_level = "INFO"


# Modules that did `from ..paths import <CONST>` at import time and so
# hold their OWN binding of the path constant. Re-pointing only
# ``pippal.paths`` would miss these copies, so a per-test reset must
# rebind every one of them. (module dotted name, {attr: paths-attr}).
_PATH_REBINDS: tuple[tuple[str, dict[str, str]], ...] = (
    ("pippal.paths", {
        "DATA_ROOT": "DATA_ROOT", "VOICES_DIR": "VOICES_DIR",
        "CONFIG_PATH": "CONFIG_PATH", "HISTORY_PATH": "HISTORY_PATH",
        "TEMP_DIR": "TEMP_DIR",
    }),
    ("pippal.config", {"CONFIG_PATH": "CONFIG_PATH"}),
    ("pippal.voices", {"VOICES_DIR": "VOICES_DIR"}),
    ("pippal.history", {"HISTORY_PATH": "HISTORY_PATH"}),
    ("pippal.onboarding", {
        "DATA_ROOT": "DATA_ROOT", "VOICES_DIR": "VOICES_DIR",
    }),
    ("pippal.playback", {"TEMP_DIR": "TEMP_DIR"}),
    ("pippal.web_ui.bridge", {"VOICES_DIR": "VOICES_DIR"}),
    ("pippal.ui.voice_manager", {"VOICES_DIR": "VOICES_DIR"}),
    ("pippal.engines.piper", {"VOICES_DIR": "VOICES_DIR"}),
)


# Functions that captured a path constant as a DEFAULT ARGUMENT value.
# Python binds default-argument values at ``def`` time, so re-pointing
# the module constant is NOT enough — these functions would still write
# the original (real) profile. Each entry rewrites the function's
# ``__defaults__`` / ``__kwdefaults__`` slot for the fresh profile.
# (module, qualname, {param_name: paths-attr}).
_DEFAULT_ARG_REBINDS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("pippal.config", "load_config", {"path": "CONFIG_PATH"}),
    ("pippal.config", "save_config", {"path": "CONFIG_PATH"}),
    ("pippal.history", "load_history", {"path": "HISTORY_PATH"}),
    ("pippal.history", "save_history", {"path": "HISTORY_PATH"}),
    ("pippal.onboarding", "activation_state_path", {"data_root": "DATA_ROOT"}),
    ("pippal.onboarding", "build_activation_readiness",
     {"voices_dir": "VOICES_DIR"}),
    ("pippal.onboarding", "is_default_engine_ready",
     {"voices_dir": "VOICES_DIR"}),
    ("pippal.ui.voice_manager", "install_piper_voice",
     {"voices_dir": "VOICES_DIR"}),
)


def _rebind_default_arg(func, param_names: dict[str, Path]) -> None:
    """Rewrite ``func``'s default-arg slots so the named params point at
    the fresh profile path. Handles both positional (``__defaults__``)
    and keyword-only (``__kwdefaults__``) defaults."""
    code = func.__code__
    # Positional defaults map to the LAST N positional-or-keyword params.
    pos_names = list(code.co_varnames[: code.co_argcount])
    defaults = list(func.__defaults__ or ())
    if defaults:
        first_def = code.co_argcount - len(defaults)
        for off, name in enumerate(pos_names[first_def:]):
            if name in param_names:
                defaults[off] = param_names[name]
        func.__defaults__ = tuple(defaults)
    kwd = dict(func.__kwdefaults__ or {})
    changed = False
    for name, value in param_names.items():
        if name in kwd:
            kwd[name] = value
            changed = True
    if changed:
        func.__kwdefaults__ = kwd


def _repoint_paths(profile: Path) -> None:
    """Re-point every bound path constant at ``profile``.

    ``pippal.paths`` derives its constants from ``PIPPAL_DATA_DIR`` once,
    at import. Setting the env var alone is not enough after the package
    is imported, so we (1) recompute the constants and assign them back
    into ``pippal.paths`` *and* every module that copied them by value,
    and (2) rewrite the default-argument slots of the functions that
    captured a path constant as a default at ``def`` time.
    """
    os.environ["PIPPAL_DATA_DIR"] = str(profile)
    data_root = profile
    derived = {
        "DATA_ROOT": data_root,
        "VOICES_DIR": data_root / "voices",
        "CONFIG_PATH": data_root / "config.json",
        "HISTORY_PATH": data_root / "history.json",
        "TEMP_DIR": data_root / "temp",
    }
    for mod_name, attr_map in _PATH_REBINDS:
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for attr, paths_attr in attr_map.items():
            setattr(mod, attr, derived[paths_attr])
    for mod_name, qualname, param_map in _DEFAULT_ARG_REBINDS:
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        func = getattr(mod, qualname, None)
        if func is None:
            continue
        _rebind_default_arg(
            func, {p: derived[a] for p, a in param_map.items()}
        )
    for d in (derived["DATA_ROOT"], derived["TEMP_DIR"], derived["VOICES_DIR"]):
        d.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session", autouse=True)
def require_live_windows():
    """Override the parent e2e/conftest.py gate.

    That gate exists for the Tk *live desktop* suite, which launches the
    real ``reader_app.py`` and needs ``PIPPAL_E2E_LIVE=1`` plus a real
    Windows session. The web suite is self-contained — it serves the
    static UI and an in-process backend — so it has its own, lighter
    requirement: a browser-capable host (Playwright provides one).
    """
    return None


@pytest.fixture
def cmd_server_identity() -> Iterator[dict[str, str]]:
    """A hermetic, per-test identity for the shell-integration IPC.

    The shell-integration command server (``pippal.command_server``,
    the one the right-click "Read with PipPal" entry talks to via
    ``python -m pippal.open_file``) normally binds the FIXED well-known
    port ``CMD_SERVER_PORT`` (51677) with no instance identity. Under a
    repeated / parallel / reordered E2E run that is a real isolation
    hazard: a stale or ``TIME_WAIT`` listener from a *previous* test can
    answer ``open_file``'s POST with returncode 0 while THIS test's
    fresh per-test engine never reacts — exactly the historical ~15 %
    flake of ``test_shell_integration_registry_and_command``.

    This fixture uses the (production-unchanged, strictly opt-in) core
    hooks already landed in ``command_server.py`` / ``open_file.py``
    (``PIPPAL_CMD_SERVER_PORT`` / ``PIPPAL_CMD_SERVER_TOKEN``):

    * port ``0`` => the OS hands out a free ephemeral port (no fixed
      port to collide on); ``start_command_server`` writes the
      actually-bound port back into ``PIPPAL_CMD_SERVER_PORT`` so the
      harness — and the ``open_file`` subprocess, which inherits this
      env — target exactly THIS instance;
    * a 128-bit random per-test token => the server REQUIRES the
      matching ``X-PipPal-Token`` header and 404s anything else, and
      the ``open_file`` subprocess sends it.

    A stale listener from another test is therefore on a different
    port AND lacks this token, so it physically cannot satisfy this
    test's request. The two env vars are fully restored at test end,
    so nothing leaks to the next test or to production (which never
    sets them — behaviour stays byte-for-byte identical there).
    """
    prev_port = os.environ.get("PIPPAL_CMD_SERVER_PORT")
    prev_token = os.environ.get("PIPPAL_CMD_SERVER_TOKEN")
    token = secrets.token_hex(16)
    os.environ["PIPPAL_CMD_SERVER_PORT"] = "0"  # OS-assigned ephemeral
    os.environ["PIPPAL_CMD_SERVER_TOKEN"] = token
    try:
        yield {"token": token}
    finally:
        if prev_port is None:
            os.environ.pop("PIPPAL_CMD_SERVER_PORT", None)
        else:
            os.environ["PIPPAL_CMD_SERVER_PORT"] = prev_port
        if prev_token is None:
            os.environ.pop("PIPPAL_CMD_SERVER_TOKEN", None)
        else:
            os.environ["PIPPAL_CMD_SERVER_TOKEN"] = prev_token


@pytest.fixture
def fresh_profile() -> Path:
    """A brand-new, isolated PIPPAL_DATA_DIR for THIS test only.

    Created empty, path constants re-pointed into it, and pre-seeded so
    the onboarding "ready" surface is deterministic (activation marked
    complete). Torn down at test end — nothing survives the boundary.
    """
    tmp = Path(tempfile.mkdtemp(prefix="pippal-web-e2e-"))
    _repoint_paths(tmp)

    # Pre-seed activation as COMPLETE so onboarding 'ready' is
    # deterministic (Finish/Close, not the play-gated first run) and an
    # earlier onboarding test can't influence a later one. Written with
    # the real module so the schema always matches the loader.
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
        path=activation_state_path(tmp),
    )
    # Deliberately NO config.json: the backend must start from the pure
    # layered defaults so the baseline assertion has a known reference.
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


class _NullRoot:
    """Same semantics as pippal.web_ui.app_web._NullRoot: an immediate
    (ms<=0) hop runs inline; a delayed call schedules a real timer so
    timed callbacks (auto-hide) don't fire instantly."""

    def __init__(self) -> None:
        self._timers: dict[int, threading.Timer] = {}
        self._next = 1

    def after(self, ms, fn=None, *a):
        if not fn:
            return None
        if not ms or ms <= 0:
            fn(*a)
            return None
        tid = self._next
        self._next += 1

        def _run():
            self._timers.pop(tid, None)
            fn(*a)

        t = threading.Timer(ms / 1000.0, _run)
        t.daemon = True
        self._timers[tid] = t
        t.start()
        return str(tid)

    def after_cancel(self, tid):
        if tid is None:
            return
        try:
            t = self._timers.pop(int(tid), None)
        except (TypeError, ValueError):
            return
        if t is not None:
            t.cancel()


@pytest.fixture
def backend(fresh_profile: Path):
    """A FRESH real engine + bridge + server for THIS test only.

    Built from the clean ``fresh_profile`` (imports happen after the
    path constants are re-pointed so every path resolves into the temp
    profile), and fully torn down at test end. No engine / overlay /
    config / server object is ever shared between tests.
    """
    from pippal.config import load_config
    from pippal.engine import TTSEngine
    from pippal.history import load_history, save_history
    from pippal.paths import ensure_dirs
    from pippal.web_ui.bridge import PipPalBridge
    from pippal.web_ui.overlay_state import WebOverlay
    from pippal.web_ui.server import start_web_ui_server

    ensure_dirs()
    config = load_config()
    overlay = WebOverlay(config)
    engine = TTSEngine(_NullRoot(), config, lambda: overlay)
    engine.attach_history(load_history(), save_history)

    hotkey_calls: list[int] = []

    def _on_hotkey_change():
        hotkey_calls.append(1)
        return []

    # Record the host callbacks so window-opening buttons have a real,
    # asserted effect (in app_web.py these are wired to WebWindowManager
    # .open(...) — here we record the request the same way pywebview's
    # window manager would receive it). This is the genuine bridge
    # contract, not a mock of the UI.
    window_opens: list[str] = []
    close_calls: list[int] = []

    bridge = PipPalBridge(
        engine, config, overlay,
        on_open_settings=lambda: window_opens.append("settings"),
        on_open_voice_manager=lambda: window_opens.append("voices"),
        on_open_notices=lambda: window_opens.append("notices"),
        on_close_window=lambda: close_calls.append(1),
        on_hotkey_change=_on_hotkey_change,
        on_engine_change=engine.reset_backend,
    )
    server, port = start_web_ui_server(bridge)
    ctx = {
        "engine": engine,
        "config": config,
        "overlay": overlay,
        "bridge": bridge,
        "base_url": f"http://127.0.0.1:{port}",
        "profile": fresh_profile,
        "hotkey_calls": hotkey_calls,
        "window_opens": window_opens,
        "close_calls": close_calls,
    }
    try:
        yield ctx
    finally:
        try:
            engine.stop()
        except Exception:
            pass
        server.shutdown()


@pytest.fixture
def readiness(backend, fresh_profile: Path):
    """Force a real onboarding readiness state for THIS test.

    ``build_activation_readiness`` is the REAL function — it inspects a
    real ``piper.exe`` path and the real installed-voices dir. This
    checkout has no ``piper.exe`` so the natural state is
    ``missing_piper``. To exercise ``missing_voice`` / ``ready`` we drop
    a real (stub) ``piper.exe`` under the per-test profile and re-point
    the onboarding ``PIPER_EXE`` (module constant + the
    ``build_activation_readiness`` / ``is_default_engine_ready``
    ``piper_exe`` default-arg) at it, and (for ``ready``) write a real
    voice file into the profile's voices dir. The readiness logic then
    runs for real against real on-disk state — no mock. Everything lives
    under the temp profile and is torn down with it.
    """
    import pippal.onboarding as onboarding

    orig_pe_const = onboarding.PIPER_EXE

    def _restore_defaults():
        _rebind_default_arg(
            onboarding.build_activation_readiness,
            {"piper_exe": orig_pe_const},
        )
        _rebind_default_arg(
            onboarding.is_default_engine_ready,
            {"piper_exe": orig_pe_const},
        )
        onboarding.PIPER_EXE = orig_pe_const

    def missing_piper():
        # Natural state in this checkout — nothing to do; just assert it.
        from pippal.onboarding import build_activation_readiness
        rd = build_activation_readiness(backend["config"])
        assert rd.status == "missing_piper", rd.status
        return rd

    def _install_fake_piper() -> Path:
        fake = fresh_profile / "piper" / "piper.exe"
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_bytes(b"MZ")  # any existing file passes Path.exists()
        onboarding.PIPER_EXE = fake
        _rebind_default_arg(
            onboarding.build_activation_readiness, {"piper_exe": fake}
        )
        _rebind_default_arg(
            onboarding.is_default_engine_ready, {"piper_exe": fake}
        )
        return fake

    def missing_voice():
        _install_fake_piper()  # piper present, but no voice on disk
        from pippal.onboarding import build_activation_readiness
        rd = build_activation_readiness(backend["config"])
        assert rd.status == "missing_voice", rd.status
        return rd

    def ready():
        _install_fake_piper()
        from pippal.paths import VOICES_DIR
        VOICES_DIR.mkdir(parents=True, exist_ok=True)
        (VOICES_DIR / "en_US-ryan-high.onnx").write_bytes(b"stub-model")
        (VOICES_DIR / "en_US-ryan-high.onnx.json").write_text("{}", "utf-8")
        from pippal.onboarding import build_activation_readiness
        rd = build_activation_readiness(backend["config"])
        assert rd.status == "ready", rd.status
        return rd

    ctl = {
        "missing_piper": missing_piper,
        "missing_voice": missing_voice,
        "ready": ready,
    }
    try:
        yield ctl
    finally:
        _restore_defaults()


# Keys the suite mutates; the baseline guard checks the live config
# matches the layered default for each so a leaked override is caught.
_BASELINE_KEYS = (
    "engine", "voice", "length_scale", "noise_scale", "auto_hide_ms",
    "overlay_y_offset", "karaoke_offset_ms", "show_overlay",
    "show_text_in_overlay", "hotkey_speak", "hotkey_stop",
    "hotkey_pause", "hotkey_queue",
)


@pytest.fixture(autouse=True)
def assert_fresh_baseline(backend):
    """Assert the KNOWN-FRESH baseline at the start of every test.

    If persisted config/voice/engine state bled in from another test,
    the test ERRORS here instead of silently passing on stale state —
    the structural defence against the false-positive class this suite
    previously suffered.
    """
    from pippal.config import _layered_defaults
    from pippal.paths import CONFIG_PATH, DATA_ROOT
    from pippal.voices import installed_voices

    profile: Path = backend["profile"]

    # 1. The active data root really is THIS test's temp profile.
    assert Path(DATA_ROOT) == profile, (
        f"data root not isolated to the per-test profile: "
        f"{DATA_ROOT!r} != {profile!r}"
    )
    # 2. No config.json on disk — backend starts from layered defaults.
    assert not Path(CONFIG_PATH).exists(), (
        f"stale config.json bled into a fresh profile: {CONFIG_PATH}"
    )
    # 3. No voices installed in the fresh profile.
    assert installed_voices() == [], (
        f"stale installed voices bled in: {installed_voices()}"
    )
    # 4. Live config equals the layered defaults for every mutated key.
    defaults = _layered_defaults()
    cfg = backend["config"]
    for key in _BASELINE_KEYS:
        assert cfg.get(key) == defaults.get(key), (
            f"live config[{key!r}]={cfg.get(key)!r} != default "
            f"{defaults.get(key)!r} — config bled between tests"
        )
    # 5. Engine idle / unspoken, history empty, overlay idle.
    engine = backend["engine"]
    with engine.lock:
        assert not engine.is_speaking, "engine already speaking at test start"
        assert engine.token == 0, "engine token not at fresh baseline"
    assert engine.get_history() == [], "history not empty at test start"
    assert engine.queue_length() == 0, "queue not empty at test start"
    assert backend["overlay"].snapshot()["overlay_state"] == "idle", (
        "overlay not idle at test start"
    )
    # 6. Activation pre-seeded complete (deterministic onboarding).
    from pippal.onboarding import load_activation_state

    assert load_activation_state().is_complete, (
        "activation not pre-seeded complete in the fresh profile"
    )
    yield


@pytest.fixture
def app_url(backend) -> str:
    return backend["base_url"]
