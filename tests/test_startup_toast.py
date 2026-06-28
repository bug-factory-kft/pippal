"""Tests for the startup tray notification (D5 port).

Verifies:
1. ``show_startup_toast`` is callable and schedules a tray balloon.
2. Under PIPPAL_NO_STARTUP_NOTIFICATION=1 the call is skipped entirely.
3. Any exception inside the helper is swallowed (silent-fail, no crash).
4. ``webview.create_window`` is NEVER called (D5 acceptance oracle).
5. ``icon.notify`` IS called when an icon is supplied; None icon no-ops.
"""

from __future__ import annotations

import threading
import unittest.mock as mock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_startup_toast():
    from pippal.web_ui import startup_toast
    return startup_toast


# ---------------------------------------------------------------------------
# 1. show_startup_toast is callable and runs the timer path
# ---------------------------------------------------------------------------


class TestStartupToastHelper:
    """Unit tests for pippal.web_ui.startup_toast."""

    def test_module_exports_show_startup_toast(self):
        mod = _import_startup_toast()
        assert callable(mod.show_startup_toast)

    def test_show_startup_toast_calls_display_exactly_once(self, monkeypatch):
        """The public show_startup_toast() must schedule _display_toast and
        that scheduled call must eventually invoke the display exactly once."""
        mod = _import_startup_toast()

        calls: list[str] = []

        def fake_display(icon=None):
            calls.append("displayed")

        # Make the timer fire synchronously so the test doesn't wait.
        def fake_timer(delay, fn):
            t = mock.MagicMock()
            t.daemon = True
            fn()  # fire immediately
            t.start = lambda: None
            t.cancel = lambda: None
            return t

        monkeypatch.setattr(mod, "_display_toast", fake_display)
        monkeypatch.setattr(threading, "Timer", fake_timer)
        monkeypatch.delenv("PIPPAL_NO_STARTUP_NOTIFICATION", raising=False)

        mod.show_startup_toast()

        assert calls == ["displayed"], f"Expected exactly one display call, got {calls}"

    def test_show_startup_toast_skipped_when_env_set(self, monkeypatch):
        """If PIPPAL_NO_STARTUP_NOTIFICATION is set, no timer is started."""
        mod = _import_startup_toast()

        calls: list[str] = []

        def fake_display(icon=None):
            calls.append("displayed")

        monkeypatch.setattr(mod, "_display_toast", fake_display)
        monkeypatch.setenv("PIPPAL_NO_STARTUP_NOTIFICATION", "1")

        mod.show_startup_toast()

        assert calls == [], "Should not display when env-flag is set"

    def test_display_toast_exception_is_silenced(self, monkeypatch):
        """A crash inside _display_toast must not propagate."""
        mod = _import_startup_toast()

        def boom(icon=None):
            raise RuntimeError("headless / no GUI")

        def fake_timer(delay, fn):
            t = mock.MagicMock()
            t.daemon = True
            fn()
            return t

        monkeypatch.setattr(mod, "_display_toast", boom)
        monkeypatch.setattr(threading, "Timer", fake_timer)
        monkeypatch.delenv("PIPPAL_NO_STARTUP_NOTIFICATION", raising=False)

        # Must not raise
        mod.show_startup_toast()

    def test_show_startup_toast_skipped_in_ci(self, monkeypatch):
        """CI environment (PIPPAL_NO_STARTUP_NOTIFICATION) suppresses toast."""
        mod = _import_startup_toast()
        calls: list[str] = []
        monkeypatch.setattr(mod, "_display_toast", lambda icon=None: calls.append("x"))
        monkeypatch.setenv("PIPPAL_NO_STARTUP_NOTIFICATION", "1")
        mod.show_startup_toast()
        assert calls == []

    # D5 acceptance oracle: no webview.create_window, icon.notify called
    def test_no_webview_create_window_with_icon(self, monkeypatch):
        """_display_toast must never call webview.create_window (D5).
        With a live icon, it calls icon.notify instead."""
        mod = _import_startup_toast()

        # Stub webview so create_window raises if called
        class FakeWebview:
            @staticmethod
            def create_window(*a, **kw):
                raise AssertionError("webview.create_window must NOT be called")

        import sys
        monkeypatch.setitem(sys.modules, "webview", FakeWebview())  # type: ignore[arg-type]

        fake_icon = mock.MagicMock()
        # Should not raise; must call icon.notify
        mod._display_toast(icon=fake_icon)
        fake_icon.notify.assert_called_once_with("Running in the background", "PipPal")

    def test_no_webview_create_window_with_none(self, monkeypatch):
        """_display_toast(icon=None) must be a complete no-op (D5)."""
        mod = _import_startup_toast()

        class FakeWebview:
            @staticmethod
            def create_window(*a, **kw):
                raise AssertionError("webview.create_window must NOT be called")

        import sys
        monkeypatch.setitem(sys.modules, "webview", FakeWebview())  # type: ignore[arg-type]

        # Must not raise, must not call anything
        mod._display_toast(icon=None)  # no-op


# ---------------------------------------------------------------------------
# 2. Integration: show_startup_toast is wired into app_web module
# ---------------------------------------------------------------------------


class TestStartupToastWiredInMain:
    """Verify show_startup_toast is imported into app_web and called in main()."""

    def test_show_startup_toast_imported_in_app_web(self):
        """app_web must import show_startup_toast at module level."""
        from pippal.web_ui import app_web

        assert hasattr(app_web, "show_startup_toast"), (
            "pippal.web_ui.app_web must import show_startup_toast "
            "so it can be called during main()"
        )

    def test_show_startup_toast_is_the_real_function(self):
        """The imported name must be the actual helper, not a stub."""
        from pippal.web_ui import app_web
        from pippal.web_ui.startup_toast import show_startup_toast

        assert app_web.show_startup_toast is show_startup_toast

    def test_main_source_calls_show_startup_toast(self):
        """A source-level guard: main()'s source must call show_startup_toast."""
        import inspect

        from pippal.web_ui import app_web

        src = inspect.getsource(app_web.main)
        # The call now passes the tray icon: show_startup_toast(icon)
        assert "show_startup_toast(icon)" in src, (
            "main() must call show_startup_toast(icon) — found no such call in source"
        )
