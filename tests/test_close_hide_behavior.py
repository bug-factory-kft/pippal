"""Regression tests for Behavior B: closing hide-to-tray surfaces hides
the window instead of destroying it, keeping the app alive.

Updated to match Pro's window_lifecycle.close() behavior (verbatim port):
- settings, onboarding, voices, moods, import, queue, release, recent: HIDE
- notices, overlay, and all other surfaces: DESTROY
  (overlay is always re-created on demand; notices is not frequently opened)

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
    # Clear cached modules so windows.py + its sibling lifecycle module pick
    # up the stub on the next import.  Matching "pippal.web_ui.window" catches
    # windows, window_lifecycle, window_native, window_geometry.
    for key in list(sys.modules):
        if "pippal.web_ui.window" in key:
            del sys.modules[key]
    from pippal.web_ui.windows import WebWindowManager
    mgr = WebWindowManager()
    mgr._base_url = "http://127.0.0.1:9999"
    mgr._bridge = mock.MagicMock()
    mgr._started = True  # pretend the GUI loop is running
    return mgr


# ---------------------------------------------------------------------------
# 1. WebWindowManager.close() — settings/onboarding/voices hide, not destroy
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

    def test_close_notices_calls_destroy_not_hide(self, monkeypatch):
        """Pro behavior: close('notices') destroys the window (not a hide-surface).

        Updated from old free behavior (hide) to match Pro's window_lifecycle.close()
        verbatim port — notices is not in the hide list; it is destroyed and
        recreated on demand.
        """
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["notices"] = fake_win

        mgr.close("notices")

        fake_win.destroy.assert_called_once()
        fake_win.hide.assert_not_called()

    def test_close_overlay_calls_destroy_not_hide(self, monkeypatch):
        """Pro behavior: close('overlay') destroys the window (not a hide-surface).

        Updated from old free behavior (hide) to match Pro's window_lifecycle.close()
        verbatim port — overlay is not in the hide list for close().  The app
        always keeps a hidden settings window alive (via run()), so destroying
        the overlay does not kill the GUI loop.  The overlay is recreated (or
        the pre-warmed hidden one is re-shown) on the next open() call.
        """
        mgr = _make_manager(monkeypatch)
        fake_win = mock.MagicMock()
        mgr._windows["overlay"] = fake_win

        mgr.close("overlay")

        fake_win.destroy.assert_called_once()
        fake_win.hide.assert_not_called()

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
# 4. events.closing wired for settings in _make_window (Pro: settings only)
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
        # Clear all sibling modules so the fresh webview stub is picked up.
        for key in list(sys.modules):
            if "pippal.web_ui.window" in key:
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
        # Clear all sibling modules so the fresh webview stub is picked up.
        for key in list(sys.modules):
            if "pippal.web_ui.window" in key:
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
        # Clear all sibling modules so the fresh webview stub is picked up.
        for key in list(sys.modules):
            if "pippal.web_ui.window" in key:
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
        # refreshPiperVoices + voice-change listeners live in settings.js
        # after the ES6-module port (step 5). app.js was deleted.
        return (repo / "webui" / "js" / "settings.js").read_text(encoding="utf-8")

    def test_refresh_piper_voices_function_present(self):
        js = self._read_appjs()
        assert "refreshPiperVoices" in js, (
            "settings.js must define refreshPiperVoices() for voice-list live refresh"
        )

    def test_installed_voices_changed_event_listener_present(self):
        js = self._read_appjs()
        assert "addEventListener" in js and "INSTALLED_VOICES_CHANGED_EVENT" in js, (
            "settings.js must register window.addEventListener(INSTALLED_VOICES_CHANGED_EVENT, ...)"
        )

    def test_storage_listener_present(self):
        js = self._read_appjs()
        assert "INSTALLED_VOICES_CHANGED_KEY" in js, (
            "settings.js must check INSTALLED_VOICES_CHANGED_KEY in storage listener"
        )
