"""Window polish acceptance tests (SPEC items a-h).

Pure-logic / unit: all pass in headless CI (no WebView2, no Win32).

a. should_activate: overlay False, non-overlay True.
b. overlay_position: bottom-centre math + None when headless.
c. drag-region: pywebview-drag-region in index.html + overlay.css; no-drag
   on buttons.
d. about_info: reddit link present.
e. startup_toast: no webview.create_window; icon.notify called; None no-op.
f. _SURFACES["overlay"]: no transparent, has frameless + on_top.
g. import pippal: works with webview absent/stubbed (H3).
"""

from __future__ import annotations

import pathlib
import sys
import types
import unittest.mock as mock

# Root of the repo (two levels up from this file in tests/).
_REPO = pathlib.Path(__file__).parent.parent
_WEBUI = _REPO / "webui"


# ---------------------------------------------------------------------------
# a. should_activate (D4)
# ---------------------------------------------------------------------------


class TestShouldActivate:
    def test_overlay_returns_false(self):
        from pippal.web_ui.windows import should_activate
        assert should_activate("overlay") is False

    def test_settings_returns_true(self):
        from pippal.web_ui.windows import should_activate
        assert should_activate("settings") is True

    def test_voices_returns_true(self):
        from pippal.web_ui.windows import should_activate
        assert should_activate("voices") is True

    def test_onboarding_returns_true(self):
        from pippal.web_ui.windows import should_activate
        assert should_activate("onboarding") is True

    def test_notices_returns_true(self):
        from pippal.web_ui.windows import should_activate
        assert should_activate("notices") is True

    def test_arbitrary_surface_returns_true(self):
        from pippal.web_ui.windows import should_activate
        assert should_activate("anything_else") is True


# ---------------------------------------------------------------------------
# b. overlay_position (D2 / #280)
# ---------------------------------------------------------------------------


class TestOverlayPosition:
    def _fake_webview(self, screens):
        """Return a minimal fake webview module with .screens = screens."""
        mod = types.ModuleType("webview")
        mod.screens = screens
        return mod

    def _fake_screen(self, x=0, y=0, width=1920, height=1080):
        s = mock.MagicMock()
        s.x = x
        s.y = y
        s.width = width
        s.height = height
        return s

    def test_bottom_centre_1920x1080(self, monkeypatch):
        """Standard 1920x1080 screen, overlay 560x200 -> x=680, y=840."""
        fake_wv = self._fake_webview([self._fake_screen(0, 0, 1920, 1080)])
        monkeypatch.setitem(sys.modules, "webview", fake_wv)
        # Re-import to pick up monkeypatched webview
        if "pippal.web_ui.window_geometry" in sys.modules:
            del sys.modules["pippal.web_ui.window_geometry"]
        from pippal.web_ui.window_geometry import overlay_position

        spec = {"width": 560, "height": 200}
        result = overlay_position(spec)
        assert result is not None
        assert result["x"] == (1920 - 560) // 2  # 680
        assert result["y"] == 1080 - 200 - 40     # 840

    def test_offset_screen(self, monkeypatch):
        """Screen at x=1920,y=0 (second monitor)."""
        fake_wv = self._fake_webview([self._fake_screen(1920, 0, 2560, 1440)])
        monkeypatch.setitem(sys.modules, "webview", fake_wv)
        if "pippal.web_ui.window_geometry" in sys.modules:
            del sys.modules["pippal.web_ui.window_geometry"]
        from pippal.web_ui.window_geometry import overlay_position

        spec = {"width": 560, "height": 200}
        result = overlay_position(spec)
        assert result is not None
        assert result["x"] == 1920 + (2560 - 560) // 2
        assert result["y"] == 0 + 1440 - 200 - 40

    def test_returns_none_when_no_screens(self, monkeypatch):
        """When webview.screens is empty, returns None (headless/CI)."""
        fake_wv = self._fake_webview([])
        monkeypatch.setitem(sys.modules, "webview", fake_wv)
        if "pippal.web_ui.window_geometry" in sys.modules:
            del sys.modules["pippal.web_ui.window_geometry"]
        from pippal.web_ui.window_geometry import overlay_position

        spec = {"width": 560, "height": 200}
        result = overlay_position(spec)
        assert result is None

    def test_returns_none_when_spec_has_no_width(self, monkeypatch):
        """When spec is missing required keys, returns None (bad input guard)."""
        fake_wv = self._fake_webview([self._fake_screen(0, 0, 1920, 1080)])
        monkeypatch.setitem(sys.modules, "webview", fake_wv)
        if "pippal.web_ui.window_geometry" in sys.modules:
            del sys.modules["pippal.web_ui.window_geometry"]
        from pippal.web_ui.window_geometry import overlay_position

        # Missing width key → TypeError/ValueError inside → returns None
        result = overlay_position({})
        assert result is None


# ---------------------------------------------------------------------------
# c. Drag-region presence (D3)
# ---------------------------------------------------------------------------


class TestDragRegionPresence:
    def test_index_html_has_pywebview_drag_region(self):
        """index.html titlebar must contain pywebview-drag-region class."""
        html = (_WEBUI / "index.html").read_text(encoding="utf-8")
        assert "pywebview-drag-region" in html, (
            "index.html must contain pywebview-drag-region on the titlebar drag span"
        )

    def test_index_html_has_titlebar_drag_span(self):
        """index.html must wrap icon+brand in a .titlebar-drag span."""
        html = (_WEBUI / "index.html").read_text(encoding="utf-8")
        assert "titlebar-drag" in html

    def test_overlay_css_has_pywebview_drag_region(self):
        """overlay.css must define the .overlay-drag-region with drag."""
        css = (_WEBUI / "css" / "overlay.css").read_text(encoding="utf-8")
        assert "pywebview-drag-region" in css

    def test_overlay_css_has_no_drag_on_obtn(self):
        """overlay.css must mark .obtn as no-drag so button clicks work."""
        css = (_WEBUI / "css" / "overlay.css").read_text(encoding="utf-8")
        # The transport buttons must carry no-drag
        assert "no-drag" in css

    def test_overlay_css_has_no_drag_on_close(self):
        """overlay.css must mark .overlay-close as no-drag."""
        css = (_WEBUI / "css" / "overlay.css").read_text(encoding="utf-8")
        assert ".overlay-close" in css
        # The close button section should have no-drag
        close_idx = css.index(".overlay-close")
        snippet = css[close_idx:close_idx + 200]
        assert "no-drag" in snippet

    def test_app_js_overlay_head_has_drag_region(self):
        """app.js renderOverlay must use overlay-drag-region + pywebview-drag-region."""
        js = (_WEBUI / "js" / "app.js").read_text(encoding="utf-8")
        assert "overlay-drag-region" in js
        assert "pywebview-drag-region" in js

    def test_app_js_no_right_button_drag(self):
        """app.js must NOT contain the old right-button JS drag block."""
        js = (_WEBUI / "js" / "app.js").read_text(encoding="utf-8")
        # The old drag block used data-dragging attribute
        assert "data-dragging" not in js

    def test_theme_css_has_titlebar_drag_rule(self):
        """theme.css must define .titlebar-drag with drag region."""
        css = (_WEBUI / "css" / "theme.css").read_text(encoding="utf-8")
        assert ".titlebar-drag" in css
        assert "pywebview-drag-region" in css or "app-region: drag" in css


# ---------------------------------------------------------------------------
# d. about_info has reddit link (D6)
# ---------------------------------------------------------------------------


class TestAboutInfoReddit:
    def _make_bridge(self):
        import unittest.mock as mock

        from pippal.web_ui.bridge import PipPalBridge

        engine = mock.MagicMock()
        config: dict = {}
        return PipPalBridge(engine, config)

    def test_reddit_key_present(self):
        bridge = self._make_bridge()
        info = bridge.about_info()
        keys = [link["key"] for link in info["links"]]
        assert "reddit" in keys, f"Expected 'reddit' in about_info links, got {keys}"

    def test_reddit_url_correct(self):
        bridge = self._make_bridge()
        info = bridge.about_info()
        reddit = next(lnk for lnk in info["links"] if lnk["key"] == "reddit")
        assert reddit["url"] == "https://www.reddit.com/r/PipPalApp/"

    def test_reddit_text(self):
        bridge = self._make_bridge()
        info = bridge.about_info()
        reddit = next(lnk for lnk in info["links"] if lnk["key"] == "reddit")
        assert reddit["text"] == "Community (Reddit)"


# ---------------------------------------------------------------------------
# e. startup_toast spawns no webview (D5) — also in test_startup_toast.py
# ---------------------------------------------------------------------------


class TestStartupToastNoWebview:
    def test_display_toast_with_icon_calls_notify(self):
        """_display_toast(icon) calls icon.notify without touching webview."""
        from pippal.web_ui.startup_toast import _display_toast

        fake_icon = mock.MagicMock()
        _display_toast(icon=fake_icon)
        fake_icon.notify.assert_called_once_with("Running in the background", "PipPal")

    def test_display_toast_none_is_noop(self):
        """_display_toast(None) is a no-op; no exception."""
        from pippal.web_ui.startup_toast import _display_toast

        _display_toast(icon=None)  # must not raise

    def test_no_create_window_in_source(self):
        """startup_toast.py must not reference webview.create_window."""
        import inspect

        from pippal.web_ui import startup_toast

        src = inspect.getsource(startup_toast)
        assert "create_window" not in src, (
            "startup_toast.py must not call webview.create_window"
        )

    def test_no_toast_html_in_source(self):
        """startup_toast.py must not contain _TOAST_HTML (old webview path)."""
        import inspect

        from pippal.web_ui import startup_toast

        src = inspect.getsource(startup_toast)
        assert "_TOAST_HTML" not in src


# ---------------------------------------------------------------------------
# f. _SURFACES["overlay"] spec (D2 static)
# ---------------------------------------------------------------------------


class TestOverlaySpec:
    def test_no_transparent(self):
        from pippal.web_ui.windows import _SURFACES

        overlay = _SURFACES["overlay"]
        assert "transparent" not in overlay, (
            "overlay spec must NOT have transparent=True (opaque mini-player)"
        )

    def test_frameless(self):
        from pippal.web_ui.windows import _SURFACES

        assert _SURFACES["overlay"].get("frameless") is True

    def test_on_top(self):
        from pippal.web_ui.windows import _SURFACES

        assert _SURFACES["overlay"].get("on_top") is True

    def test_dimensions(self):
        """Overlay should be 560x200 matching the Pro mini-player spec."""
        from pippal.web_ui.windows import _SURFACES

        overlay = _SURFACES["overlay"]
        assert overlay["width"] == 560
        assert overlay["height"] == 200


# ---------------------------------------------------------------------------
# g. import pippal works with webview absent (H3)
# ---------------------------------------------------------------------------


class TestHeadlessImport:
    def test_import_pippal_without_webview(self, monkeypatch):
        """``import pippal`` must succeed even when webview is not installed."""
        # Hide webview from the import system
        monkeypatch.setitem(sys.modules, "webview", None)  # type: ignore[arg-type]

        # Re-import to confirm no top-level webview import in windows.py
        for key in list(sys.modules):
            if "pippal.web_ui.windows" in key or "pippal.web_ui.window_native" in key or \
               "pippal.web_ui.window_geometry" in key:
                del sys.modules[key]

        # Should not raise even with webview=None
        import pippal  # noqa: F401
        from pippal.web_ui import windows  # noqa: F401

    def test_windows_module_no_top_level_webview_import(self):
        """windows.py must not import webview at module top level."""
        import ast
        src = (_REPO / "src" / "pippal" / "web_ui" / "windows.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Check that no top-level import statement imports 'webview'
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                module = getattr(node, "module", "") or ""
                assert "webview" not in names and "webview" not in module, (
                    "windows.py must not import webview at module top level (H3)"
                )

    def test_window_native_not_imported_at_top_level(self):
        """windows.py must not import window_native at module top level."""
        import ast
        src = (_REPO / "src" / "pippal" / "web_ui" / "windows.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                names = [a.name for a in getattr(node, "names", [])]
                assert "window_native" not in module and "window_native" not in names, (
                    "windows.py must not import window_native at module top level (H3)"
                )

    def test_window_geometry_not_imported_at_top_level(self):
        """windows.py must not import window_geometry at module top level."""
        import ast
        src = (_REPO / "src" / "pippal" / "web_ui" / "windows.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                names = [a.name for a in getattr(node, "names", [])]
                assert "window_geometry" not in module and "window_geometry" not in names, (
                    "windows.py must not import window_geometry at module top level (H3)"
                )
