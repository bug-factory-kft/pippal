"""Regression tests for Behavior B: closing hide-to-tray surfaces hides
the window instead of destroying it, keeping the app alive.

These tests are headless/unit — no real WebView2 or Win32 required.
"""

from __future__ import annotations

import sys
import types
import unittest.mock as mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_webview():
    """Return a minimal fake webview module."""
    mod = types.ModuleType("webview")
    mod.screens = []

    def _create_window(**kwargs):
        w = mock.MagicMock()
        w.on_top = kwargs.get("on_top", False)
        # events.closed / events.shown / events.closing are addable handlers
        w.events = mock.MagicMock()
        w.events.closed = mock.MagicMock()
        w.events.shown = mock.MagicMock()
        w.events.loaded = mock.MagicMock()
        w.events.closing = mock.MagicMock()
        return w

    mod.create_window = _create_window
    return mod


def _make_manager(monkeypatch):
    """Return a fresh WebWindowManager with webview stubbed out."""
    fake_wv = _stub_webview()
    monkeypatch.setitem(sys.modules, "webview", fake_wv)
    # Clear cached module so windows.py picks up the stub
    for key in list(sys.modules):
        if "pippal.web_ui.windows" in key:
            del sys.modules[key]
    from pippal.web_ui.windows import WebWindowManager
    mgr = WebWindowManager()
    mgr._base_url = "http://127.0.0.1:9999"
    mgr._bridge = mock.MagicMock()
    mgr._started = True  # pretend the GUI loop is running
    return mgr


# ---------------------------------------------------------------------------
# 1. WebWindowManager.close() — settings hides, not destroys
# ---------------------------------------------------------------------------


class TestCloseHidesSettingsSurface:
    def test_close_settings_calls_hide_not_destroy(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["settings"] = fake_win

        mgr.close("settings")

        fake_win.hide.assert_called_once()
        fake_win.destroy.assert_not_called()

    def test_close_onboarding_calls_hide_not_destroy(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["onboarding"] = fake_win

        mgr.close("onboarding")

        fake_win.hide.assert_called_once()
        fake_win.destroy.assert_not_called()

    def test_close_voices_calls_hide_not_destroy(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["voices"] = fake_win

        mgr.close("voices")

        fake_win.hide.assert_called_once()
        fake_win.destroy.assert_not_called()

    def test_close_notices_calls_hide_not_destroy(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["notices"] = fake_win

        mgr.close("notices")

        fake_win.hide.assert_called_once()
        fake_win.destroy.assert_not_called()

    def test_close_overlay_calls_hide_not_destroy(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["overlay"] = fake_win

        mgr.close("overlay")

        fake_win.hide.assert_called_once()
        fake_win.destroy.assert_not_called()

    def test_close_unknown_surface_destroys(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["some_other"] = fake_win

        mgr.close("some_other")

        fake_win.destroy.assert_called_once()
        fake_win.hide.assert_not_called()

    def test_close_missing_surface_is_noop(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        # No exception; _windows is empty
        mgr.close("settings")  # should not raise


# ---------------------------------------------------------------------------
# 2. WebWindowManager.close() keeps window in _windows after hiding
# ---------------------------------------------------------------------------


class TestCloseWindowRemainsAlive:
    def test_settings_window_stays_in_windows_after_close(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["settings"] = fake_win

        mgr.close("settings")

        # Window must still be registered (hide, not pop)
        assert "settings" in mgr._windows, (
            "close('settings') must keep the window in _windows so it can be re-shown"
        )


# ---------------------------------------------------------------------------
# 3. WebWindowManager.surface_for_window() returns the correct name
# ---------------------------------------------------------------------------


class TestSurfaceForWindow:
    def test_returns_surface_name_for_registered_window(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["settings"] = fake_win

        result = mgr.surface_for_window(fake_win)
        assert result == "settings"

    def test_returns_none_for_unknown_window(self, monkeypatch):
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["settings"] = mock.MagicMock()  # different object

        result = mgr.surface_for_window(fake_win)
        assert result is None


# ---------------------------------------------------------------------------
# 4. events.closing wired for hide-to-tray surfaces in _make_window
# ---------------------------------------------------------------------------


class TestClosingEventWired:
    def test_settings_wires_closing_event(self, monkeypatch):
        """_make_window('settings') must wire events.closing += handler."""
        fake_wv = _stub_webview()
        closing_added = []

        def _create_window(**kwargs):
            w = mock.MagicMock()
            w.on_top = False
            w.events = mock.MagicMock()
            w.events.closed = mock.MagicMock()
            w.events.shown = mock.MagicMock()
            w.events.loaded = mock.MagicMock()
            # Track += calls on closing
            class _Closing:
                def __iadd__(self, fn):
                    closing_added.append(fn)
                    return self
            w.events.closing = _Closing()
            return w

        fake_wv.create_window = _create_window
        monkeypatch.setitem(sys.modules, "webview", fake_wv)
        for key in list(sys.modules):
            if "pippal.web_ui.windows" in key:
                del sys.modules[key]

        from pippal.web_ui.windows import WebWindowManager
        mgr = WebWindowManager()
        mgr._base_url = "http://127.0.0.1:9999"
        mgr._bridge = mock.MagicMock()
        mgr._make_window("settings")

        assert len(closing_added) >= 1, (
            "_make_window('settings') must wire events.closing to intercept X button"
        )

    def test_closing_handler_returns_false_to_cancel_destroy(self, monkeypatch):
        """The closing handler must return False (cancel the native close)."""
        fake_wv = _stub_webview()
        closing_handlers = []

        def _create_window(**kwargs):
            w = mock.MagicMock()
            w.on_top = False
            w.events = mock.MagicMock()
            w.events.closed = mock.MagicMock()
            w.events.shown = mock.MagicMock()
            w.events.loaded = mock.MagicMock()
            class _Closing:
                def __iadd__(self, fn):
                    closing_handlers.append(fn)
                    return self
            w.events.closing = _Closing()
            return w

        fake_wv.create_window = _create_window
        monkeypatch.setitem(sys.modules, "webview", fake_wv)
        for key in list(sys.modules):
            if "pippal.web_ui.windows" in key:
                del sys.modules[key]

        from pippal.web_ui.windows import WebWindowManager
        mgr = WebWindowManager()
        mgr._base_url = "http://127.0.0.1:9999"
        mgr._bridge = mock.MagicMock()
        mgr._make_window("settings")

        assert closing_handlers, "No closing handler registered"
        result = closing_handlers[0]()
        assert result is False, (
            "closing handler must return False to cancel the native window destroy"
        )

    def test_overlay_does_not_wire_closing_event(self, monkeypatch):
        """overlay _make_window must NOT wire events.closing (no native X)."""
        fake_wv = _stub_webview()
        closing_added = []

        def _create_window(**kwargs):
            w = mock.MagicMock()
            w.on_top = False
            w.events = mock.MagicMock()
            w.events.closed = mock.MagicMock()
            w.events.shown = mock.MagicMock()
            w.events.loaded = mock.MagicMock()
            class _Closing:
                def __iadd__(self, fn):
                    closing_added.append(fn)
                    return self
            w.events.closing = _Closing()
            return w

        fake_wv.create_window = _create_window
        monkeypatch.setitem(sys.modules, "webview", fake_wv)
        for key in list(sys.modules):
            if "pippal.web_ui.windows" in key:
                del sys.modules[key]

        from pippal.web_ui.windows import WebWindowManager
        mgr = WebWindowManager()
        mgr._base_url = "http://127.0.0.1:9999"
        mgr._bridge = mock.MagicMock()
        mgr._make_window("overlay")

        assert len(closing_added) == 0, (
            "overlay must not wire events.closing (it has no native X button)"
        )


# ---------------------------------------------------------------------------
# 5. Behavior A: listener code present in app.js
# ---------------------------------------------------------------------------


class TestBehaviorAListenerPresent:
    def _read_appjs(self):
        import pathlib
        repo = pathlib.Path(__file__).parent.parent
        return (repo / "webui" / "js" / "app.js").read_text(encoding="utf-8")

    def test_refresh_piper_voices_function_present(self):
        js = self._read_appjs()
        assert "refreshPiperVoices" in js, (
            "app.js must define refreshPiperVoices() for voice-list live refresh"
        )

    def test_installed_voices_changed_event_listener_present(self):
        js = self._read_appjs()
        assert "addEventListener" in js and "INSTALLED_VOICES_CHANGED_EVENT" in js, (
            "app.js must register window.addEventListener(INSTALLED_VOICES_CHANGED_EVENT, ...)"
        )

    def test_storage_listener_present(self):
        js = self._read_appjs()
        assert "INSTALLED_VOICES_CHANGED_KEY" in js, (
            "app.js must check INSTALLED_VOICES_CHANGED_KEY in storage listener"
        )
