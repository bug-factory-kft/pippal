"""Pytest fixtures for the PipPal web-UI Playwright suite.

The suite drives the REAL static UI (``webui/``) served by the REAL
bridge server (:mod:`pippal.web_ui.server`) wired to the REAL
:class:`pippal.engine.TTSEngine` and config — only the data directory
is redirected to a temp profile (``PIPPAL_DATA_DIR``) so a run never
touches the developer's real PipPal state.

Playwright talks to the served UI exactly the way the desktop webview
does (the JS ``api.js`` falls back to ``POST /bridge`` when the
pywebview bridge object is absent), so these are true end-to-end tests
against the migrated frontend, not a mock.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


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


@pytest.fixture(scope="session")
def pippal_profile() -> Path:
    """Isolated PIPPAL_DATA_DIR for the whole session."""
    tmp = Path(tempfile.mkdtemp(prefix="pippal-web-e2e-"))
    os.environ["PIPPAL_DATA_DIR"] = str(tmp)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def backend(pippal_profile: Path):
    """Real engine + bridge + server, isolated to the temp profile."""
    # Imported AFTER PIPPAL_DATA_DIR is set so paths resolve into temp.
    from pippal.config import load_config
    from pippal.engine import TTSEngine
    from pippal.history import load_history, save_history
    from pippal.paths import ensure_dirs
    from pippal.web_ui.bridge import PipPalBridge
    from pippal.web_ui.overlay_state import WebOverlay
    from pippal.web_ui.server import start_web_ui_server

    class _NullRoot:
        """Same semantics as pippal.web_ui.app_web._NullRoot: an
        immediate (ms<=0) hop runs inline; a delayed call schedules a
        real timer so timed callbacks don't fire instantly."""

        def after(self, ms, fn=None, *a):
            if not fn:
                return None
            if not ms or ms <= 0:
                fn(*a)
                return None
            t = threading.Timer(ms / 1000.0, lambda: fn(*a))
            t.daemon = True
            t.start()
            return t

        def after_cancel(self, t):
            if t is not None:
                t.cancel()

    ensure_dirs()
    config = load_config()
    overlay = WebOverlay(config)
    engine = TTSEngine(_NullRoot(), config, lambda: overlay)
    engine.attach_history(load_history(), save_history)

    hotkey_calls: list[int] = []

    def _on_hotkey_change():
        hotkey_calls.append(1)
        return []

    bridge = PipPalBridge(
        engine, config, overlay,
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
        "profile": pippal_profile,
        "hotkey_calls": hotkey_calls,
    }
    yield ctx
    server.shutdown()


@pytest.fixture
def app_url(backend) -> str:
    return backend["base_url"]
