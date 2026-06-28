"""Regression tests for the 5 free-Pro parity fixes on branch
feat/free-pro-parity-basics.

Each test targets one specific bug and verifies the fix in isolation
without requiring pywebview, a real network, or the GUI loop.
"""

from __future__ import annotations

import threading
import types
from typing import Any
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Bug 4: _active_webview_window() now tries webview.active_window()
# ---------------------------------------------------------------------------

class TestBug4ActiveWebviewWindow:
    """open_diag_folder returns {'handled': True} when webview is available."""

    def _make_mixin(self):
        from pippal.web_ui.bridge_diag_settings import DiagSettingsBridgeMixin
        class _M(DiagSettingsBridgeMixin):
            config = {}
        return _M()

    def test_returns_none_when_webview_missing(self):
        """Without pywebview installed, _active_webview_window returns None."""
        m = self._make_mixin()
        import sys
        # Hide webview if present
        original = sys.modules.get("webview")
        sys.modules["webview"] = None  # type: ignore
        try:
            result = m._active_webview_window()
            assert result is None
        finally:
            if original is None:
                sys.modules.pop("webview", None)
            else:
                sys.modules["webview"] = original

    def test_returns_active_window(self):
        """With webview available, returns active_window() result."""
        m = self._make_mixin()
        import sys
        fake_win = object()
        fake_webview = types.ModuleType("webview")
        fake_webview.active_window = lambda: fake_win  # type: ignore
        original = sys.modules.get("webview")
        sys.modules["webview"] = fake_webview
        try:
            result = m._active_webview_window()
            assert result is fake_win
        finally:
            if original is None:
                sys.modules.pop("webview", None)
            else:
                sys.modules["webview"] = original

    def test_returns_none_when_active_window_returns_none(self):
        """Returns None when active_window() returns None (no focused window)."""
        m = self._make_mixin()
        import sys
        fake_webview = types.ModuleType("webview")
        fake_webview.active_window = lambda: None  # type: ignore
        original = sys.modules.get("webview")
        sys.modules["webview"] = fake_webview
        try:
            result = m._active_webview_window()
            assert result is None
        finally:
            if original is None:
                sys.modules.pop("webview", None)
            else:
                sys.modules["webview"] = original

    def test_open_diag_folder_handled_when_window_available(self, tmp_path):
        """open_diag_folder returns handled=True when a window is found."""
        m = self._make_mixin()
        import sys
        fake_win = object()
        fake_webview = types.ModuleType("webview")
        fake_webview.active_window = lambda: fake_win  # type: ignore
        original = sys.modules.get("webview")
        sys.modules["webview"] = fake_webview
        try:
            with patch("pippal.web_ui.bridge_diag_settings.sys") as mock_sys, \
                 patch("subprocess.Popen") as mock_popen:
                mock_sys.platform = "win32"
                # Point DIAG_DIR at tmp_path so mkdir doesn't fail
                with patch("pippal.diagnostics.DIAG_DIR", tmp_path):
                    result = m.open_diag_folder()
            assert result.get("handled") is True
        finally:
            if original is None:
                sys.modules.pop("webview", None)
            else:
                sys.modules["webview"] = original


# ---------------------------------------------------------------------------
# Bug 5: persist(close=True) now calls close_window
# ---------------------------------------------------------------------------

class TestBug5PersistClosesWindow:
    """Verify persist() behaviour without running a browser.
    After the ES6-module port (step 5), persist() lives in settings-footer.js."""

    def _read_app_js(self) -> str:
        import pathlib
        # persist() moved to settings-footer.js (step 5 ES6 port). app.js deleted.
        p = pathlib.Path(__file__).parent.parent / "webui" / "js" / "settings-footer.js"
        return p.read_text(encoding="utf-8")

    def test_persist_calls_close_window_when_close_true(self):
        """persist(true) must call API.call('close_window') in the source."""
        src = self._read_app_js()
        # The fix: when close is true, we call "close_window" not just renderSettings
        assert '"close_window"' in src, "close_window call missing from persist()"

    def test_persist_fallback_calls_render_settings(self):
        """Fallback inside the close_window catch must call renderSettings."""
        src = self._read_app_js()
        # The catch block after close_window must still call renderSettings
        assert "renderSettings" in src

    def test_persist_close_window_conditional_on_close(self):
        """close_window should only be called inside persist's if(close) branch."""
        src = self._read_app_js()
        # Find the persist function, then locate the close_window call inside it.
        persist_idx = src.find("function persist(close)")
        assert persist_idx >= 0, "persist() function not found in settings-footer.js"
        # Find the end of persist function — next top-level function declaration
        next_fn = src.find("\nexport function ", persist_idx + 1)
        persist_body = src[persist_idx:next_fn if next_fn > 0 else persist_idx + 2000]
        # The close_window call must exist inside the persist body
        assert '"close_window"' in persist_body, (
            "close_window call not found inside persist() body"
        )
        # And it must be guarded by if(close)
        assert "if (close)" in persist_body, (
            "close_window call inside persist() is not guarded by if (close)"
        )


# ---------------------------------------------------------------------------
# Bug 3: Voice install re-fetches catalogue
# ---------------------------------------------------------------------------

class TestBug3VoiceCatalogueRefresh:
    """Verify doInstall re-fetches get_voice_catalogue.
    After ES6-module port (step 5), voice manager lives in voices.js."""

    def _read_app_js(self) -> str:
        import pathlib
        # Voice manager (doInstall, vmState) moved to voices.js. app.js deleted.
        p = pathlib.Path(__file__).parent.parent / "webui" / "js" / "voices.js"
        return p.read_text(encoding="utf-8")

    def test_install_voice_async_called_first(self):
        """doInstall should attempt install_voice_async before falling back."""
        src = self._read_app_js()
        assert '"install_voice_async"' in src, (
            "install_voice_async call missing — async path not wired in doInstall"
        )

    def test_get_voice_catalogue_called_after_install(self):
        """After a successful install, get_voice_catalogue must be re-fetched."""
        src = self._read_app_js()
        assert '"get_voice_catalogue"' in src, (
            "get_voice_catalogue not called after install — Bug 3 fix incomplete"
        )

    def test_vmstate_all_updated(self):
        """vmState.all must be updated with the fresh catalogue."""
        src = self._read_app_js()
        assert "vmState.all = cat.voices" in src, (
            "vmState.all not updated after catalogue fetch"
        )


# ---------------------------------------------------------------------------
# Bug 1: Overlay window pre-warms hidden at startup
# ---------------------------------------------------------------------------

class TestBug1OverlayPrewarm:
    """WebWindowManager.run() pre-warms the overlay window hidden."""

    def _make_manager(self):
        import sys as _sys
        # Clear all pippal.web_ui.window* siblings (windows, window_lifecycle,
        # window_native, window_geometry) so that the next _make_window call
        # re-imports window_lifecycle fresh and picks up whatever webview is
        # current in sys.modules at that moment (which may be patched by the
        # test's `patch("webview.create_window", ...)` context).  Without this,
        # a previous test that loaded window_lifecycle with a fake webview
        # leaves a stale binding that shadows the patch.
        for key in list(_sys.modules):
            if "pippal.web_ui.window" in key:
                del _sys.modules[key]
        from pippal.web_ui.windows import WebWindowManager
        mgr = WebWindowManager()
        mgr._base_url = "http://127.0.0.1:9999"
        mgr._bridge = MagicMock()
        return mgr

    def test_prewarm_creates_overlay_in_windows(self):
        """run() should pre-warm the overlay so _windows['overlay'] is set."""
        mgr = self._make_manager()
        created = {}

        def fake_create_window(**kwargs):
            surface = "overlay" if "overlay" in kwargs.get("url", "") else "settings"
            win = MagicMock()
            win.events = MagicMock()
            win.events.closed = MagicMock()
            win.events.closed.__iadd__ = lambda self, fn: None
            win.events.shown = MagicMock()
            win.events.shown.__iadd__ = lambda self, fn: None
            created[surface] = kwargs
            return win

        import webview as _wv  # noqa: F401
        with patch("webview.create_window", side_effect=fake_create_window), \
             patch("webview.start"):
            # Pre-seed a settings window so run() doesn't try to open one
            mgr._windows["settings"] = MagicMock()
            mgr.run()

        assert "overlay" in created, (
            "Overlay was NOT pre-warmed during run() — Bug 1 fix missing"
        )
        assert created["overlay"].get("hidden") is True, (
            "Overlay was pre-warmed but not with hidden=True"
        )

    def test_prewarm_overlay_has_no_on_top(self):
        """Pre-warmed overlay must NOT be created with on_top=True (#265)."""
        mgr = self._make_manager()
        created_kwargs: dict[str, Any] = {}

        def fake_create_window(**kwargs):
            if "overlay" in kwargs.get("url", ""):
                created_kwargs.update(kwargs)
            win = MagicMock()
            win.events = MagicMock()
            win.events.closed.__iadd__ = lambda self, fn: None
            win.events.shown.__iadd__ = lambda self, fn: None
            return win

        with patch("webview.create_window", side_effect=fake_create_window), \
             patch("webview.start"):
            mgr._windows["settings"] = MagicMock()
            mgr.run()

        assert not created_kwargs.get("on_top"), (
            "Pre-warmed overlay has on_top=True — this causes z-order pop issues"
        )

    def test_make_window_hidden_skips_on_top(self):
        """_make_window with hidden=True must not pass on_top to create_window."""
        mgr = self._make_manager()
        captured: dict[str, Any] = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            win = MagicMock()
            win.events = MagicMock()
            win.events.closed.__iadd__ = lambda self, fn: None
            win.events.shown.__iadd__ = lambda self, fn: None
            return win

        with patch("webview.create_window", side_effect=fake_create):
            mgr._make_window("overlay", hidden=True)

        assert captured.get("hidden") is True
        assert not captured.get("on_top"), "on_top must not be set on hidden overlay"


# ---------------------------------------------------------------------------
# Bug 2: Async voice install API
# ---------------------------------------------------------------------------

class TestBug2AsyncVoiceInstall:
    """install_voice_async + voice_install_status + cancel_voice_install."""

    def _make_bridge(self):
        from pippal.web_ui.bridge import PipPalBridge

        engine = MagicMock()
        config: dict[str, Any] = {}
        return PipPalBridge(engine, config)

    def test_install_voice_async_returns_task_id(self):
        """install_voice_async returns ok=True + a task_id string."""
        bridge = self._make_bridge()

        def fake_download(url, dest, timeout=None):
            # write 1 byte so the size check passes
            import pathlib
            pathlib.Path(str(dest)).write_bytes(b"\x00")

        with patch("pippal.web_ui.bridge.PipPalBridge._voice_by_id",
                   return_value={"id": "en_US-amy-medium", "lang": "en_US",
                                 "name": "Amy", "quality": "medium",
                                 "label": "Amy (en_US)", "url_base": "x",
                                 "size_mb": 0}), \
             patch("pippal.web_ui.bridge.PipPalBridge._stream_voice_with_progress",
                   return_value="en_US-amy-medium.onnx"):
            result = bridge.install_voice_async("en_US-amy-medium")

        assert result.get("ok") is True
        assert "task_id" in result
        assert isinstance(result["task_id"], str) and result["task_id"]

    def test_voice_install_status_returns_task_state(self):
        """voice_install_status returns the task dict for a known task_id."""
        bridge = self._make_bridge()

        with patch("pippal.web_ui.bridge.PipPalBridge._voice_by_id",
                   return_value={"id": "x", "lang": "en", "name": "x",
                                 "quality": "medium", "label": "X", "url_base": "x"}), \
             patch("pippal.web_ui.bridge.PipPalBridge._stream_voice_with_progress",
                   return_value="x.onnx"):
            r = bridge.install_voice_async("x")

        task_id = r["task_id"]
        status = bridge.voice_install_status(task_id)
        assert "running" in status or "done" in status

    def test_voice_install_status_unknown_task(self):
        """voice_install_status returns done=True for unknown task_id."""
        bridge = self._make_bridge()
        result = bridge.voice_install_status("nonexistent")
        assert result.get("done") is True

    def test_cancel_voice_install_unknown(self):
        """cancel_voice_install returns ok=False for unknown task."""
        bridge = self._make_bridge()
        result = bridge.cancel_voice_install("nonexistent")
        assert result.get("ok") is False

    def test_cancel_voice_install_sets_flag(self):
        """cancel_voice_install sets cancelled flag on a running task."""
        bridge = self._make_bridge()
        # Manually seed a running task
        task_id = "test-task-id"
        with bridge._voice_task_lock:
            bridge._voice_tasks[task_id] = {
                "running": True, "pct": 0.0, "status": "…",
                "error": "", "done": False, "cancelled": False, "installed": None,
            }
        result = bridge.cancel_voice_install(task_id)
        assert result.get("ok") is True
        with bridge._voice_task_lock:
            assert bridge._voice_tasks[task_id]["cancelled"] is True

    def test_async_install_completion(self):
        """End-to-end: async install completes and marks done=True."""
        bridge = self._make_bridge()
        done_event = threading.Event()

        def fake_stream(voice, is_cancelled, set_progress):
            set_progress(pct=50.0, status="halfway")
            set_progress(pct=100.0, status="done")
            done_event.set()
            return "test-voice.onnx"

        with patch("pippal.web_ui.bridge.PipPalBridge._voice_by_id",
                   return_value={"id": "test", "label": "Test"}), \
             patch.object(bridge, "_stream_voice_with_progress", side_effect=fake_stream):
            r = bridge.install_voice_async("test")

        task_id = r["task_id"]
        done_event.wait(timeout=5.0)
        # Give the thread a moment to update done flag
        import time
        time.sleep(0.05)
        status = bridge.voice_install_status(task_id)
        assert status.get("done") is True
        assert status.get("installed") == "test-voice.onnx"

    def test_app_js_has_voice_install_status_call(self):
        """voices.js must call voice_install_status to poll progress.
        After ES6-module port (step 5), voice manager lives in voices.js."""
        import pathlib
        src = (pathlib.Path(__file__).parent.parent / "webui" / "js" / "voices.js"
               ).read_text(encoding="utf-8")
        assert '"voice_install_status"' in src, (
            "voice_install_status polling call missing from voices.js"
        )


# ---------------------------------------------------------------------------
# Window lifecycle port: Pro's window_lifecycle.py ported verbatim to free
# ---------------------------------------------------------------------------


class TestWindowLifecyclePort:
    """Verify Pro's window layer has been ported to free (window_lifecycle.py).

    These tests FAIL until the port lands.  They serve as the failing-test
    oracle required by the test-first policy before the implementation.
    """

    def test_window_lifecycle_module_exists(self) -> None:
        """window_lifecycle.py must exist and be importable in free."""
        import importlib

        mod = importlib.import_module("pippal.web_ui.window_lifecycle")
        assert mod is not None, (
            "pippal.web_ui.window_lifecycle not importable -- Pro port not complete"
        )

    def test_manager_has_raise_window(self) -> None:
        """WebWindowManager must have raise_window() (Pro-only method)."""
        from pippal.web_ui.windows import WebWindowManager

        mgr = WebWindowManager()
        assert hasattr(mgr, "raise_window"), (
            "WebWindowManager.raise_window not found -- Pro windows.py not ported"
        )

    def test_manager_has_explicit_close_flag(self) -> None:
        """WebWindowManager must have _explicit_close (Pro shutdown-safety flag)."""
        from pippal.web_ui.windows import WebWindowManager

        mgr = WebWindowManager()
        assert hasattr(mgr, "_explicit_close"), (
            "WebWindowManager._explicit_close not found -- Pro windows.py not ported"
        )

    def test_window_lifecycle_has_surfaces_dict(self) -> None:
        """window_lifecycle._SURFACES must be accessible and contain overlay."""
        import importlib

        mod = importlib.import_module("pippal.web_ui.window_lifecycle")
        surfaces = getattr(mod, "_SURFACES", None)
        assert surfaces is not None, "_SURFACES missing from window_lifecycle"
        assert "overlay" in surfaces, (
            "'overlay' key missing from window_lifecycle._SURFACES"
        )
        assert "settings" in surfaces, (
            "'settings' key missing from window_lifecycle._SURFACES"
        )
