"""pywebview window lifecycle for the web UI.

Each PipPal surface is a pywebview window loading
``<base_url>/index.html?view=<surface>``. The static UI in ``webui/``
talks back through the injected ``js_api`` bridge (and the same HTTP
``/bridge`` endpoint as a fallback / E2E transport).

Native chrome stays minimal: Settings / Voice Manager / Onboarding /
Notices keep a frameless dark window (the UI draws its own title bar).
The reader overlay is a frameless, on-top, transparent panel.

WebView2 (Chromium) is the runtime on Windows; pywebview picks it
automatically.
"""

from __future__ import annotations

import threading
from typing import Any

# ``webview`` (pywebview) is imported lazily inside the methods that
# actually create / run windows so that importing this module — and
# therefore ``import pippal`` — does not require the GUI runtime to be
# installed (e.g. on a headless CI host that only runs the unit suite).

# Per-surface window geometry.
_SURFACES: dict[str, dict[str, Any]] = {
    "settings": {"title": "PipPal", "width": 600, "height": 720},
    "voices": {"title": "Voices", "width": 820, "height": 640},
    "onboarding": {"title": "PipPal", "width": 540, "height": 560},
    "notices": {"title": "PipPal - Open-source licences",
                "width": 760, "height": 620},
    "overlay": {"title": "PipPal", "width": 800, "height": 220,
                "on_top": True, "transparent": True, "frameless": True},
}


class WebWindowManager:
    """Creates / focuses pywebview windows and owns the GUI loop."""

    def __init__(self) -> None:
        self._base_url = ""
        self._bridge: Any = None
        self._windows: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._started = False
        self._overlay_controller: Any = None

    def set_overlay_controller(self, controller: Any) -> None:
        """Store the OverlayWindowController wired by app_web.main.

        Called once after the window manager is configured.  The controller
        is available for future callers (e.g. raise_window) that need to
        check overlay visibility state.
        """
        self._overlay_controller = controller

    def configure(self, base_url: str, bridge: Any) -> None:
        self._base_url = base_url.rstrip("/")
        self._bridge = bridge

    # ------------------------------------------------------------------

    def _make_window(self, surface: str) -> Any:
        import webview

        spec = _SURFACES.get(surface, _SURFACES["settings"])
        url = f"{self._base_url}/index.html?view={surface}"
        kwargs: dict[str, Any] = {
            "title": spec["title"],
            "url": url,
            "width": spec["width"],
            "height": spec["height"],
            "js_api": self._bridge,
            "background_color": "#13151c",
            "frameless": spec.get("frameless", True),
            "easy_drag": False,
        }
        if spec.get("on_top"):
            kwargs["on_top"] = True
        if spec.get("transparent"):
            kwargs["transparent"] = True
        win = webview.create_window(**kwargs)

        def _closed(s: str = surface) -> None:
            with self._lock:
                self._windows.pop(s, None)

        win.events.closed += _closed
        return win

    def open(self, surface: str) -> None:
        """Show a surface, focusing it if already open. Thread-safe; can
        be called from tray / hotkey / command-server threads."""
        with self._lock:
            existing = self._windows.get(surface)
            if existing is not None:
                try:
                    existing.show()
                    existing.restore()
                    return
                except Exception:
                    self._windows.pop(surface, None)

        if not self._started:
            # First window must be created before webview.start(); queue
            # it so run() picks it up.
            win = self._make_window(surface)
            with self._lock:
                self._windows[surface] = win
            return

        win = self._make_window(surface)
        with self._lock:
            self._windows[surface] = win

    def hide(self, surface: str) -> None:
        """Hide a surface's window without destroying it. Thread-safe.

        Used by the overlay auto-hide path: the reader window is hidden
        (not destroyed) on idle so the next read can re-show it instantly
        and the live page (and its CDP target) survives. Falls back to
        destroy if the platform window can't hide.

        BUG2 -- the OVERLAY is the EXCEPTION to that fall-through.  The
        overlay window is frequently the foreground / last live pywebview
        window; destroying it (the historical fall-through when
        ``win.hide()`` raised) takes the GUI loop's last window with it and
        the WHOLE app disappears.  So for the overlay we NEVER destroy on a
        failed hide: we keep the window object in the live set (the GUI loop
        keeps a window) and swallow the hide error.  Other surfaces keep the
        original destroy fall-through (a transient settings/sample window is
        safe to tear down).  This guarantees at least one window always
        keeps the GUI loop alive across a reading->thinking->reading
        document switch.
        """
        with self._lock:
            win = self._windows.get(surface)
        if win is None:
            return
        try:
            win.hide()
        except Exception:
            if surface == "overlay":
                # NEVER destroy the overlay: it is (typically) the
                # foreground / last live window and destroying it kills the
                # pywebview GUI loop -> the app vanishes (BUG2 / #302).
                # Keep it in the live-window set and swallow the hide
                # failure; the next read re-shows it and the GUI loop stays
                # alive.
                return
            try:
                win.destroy()
            except Exception:
                pass
            with self._lock:
                self._windows.pop(surface, None)

    def close_active(self) -> None:
        """Close whichever window currently has focus (the JS 'X' / Cancel
        button calls this through the bridge)."""
        with self._lock:
            wins = list(self._windows.items())
        target = None
        for _surface, w in wins:
            try:
                if getattr(w, "gui", None) is not None and w.on_top is False:
                    target = w
            except Exception:
                pass
        # Fall back to the most recently opened window.
        if target is None and wins:
            target = wins[-1][1]
        if target is not None:
            try:
                target.destroy()
            except Exception:
                pass

    def shutdown(self) -> None:
        with self._lock:
            wins = list(self._windows.values())
        for w in wins:
            try:
                w.destroy()
            except Exception:
                pass
        try:
            import webview

            webview.windows.clear()
        except Exception:
            pass

    def run(self) -> None:
        """Block on the pywebview GUI loop until all windows close."""
        import webview

        if not self._windows:
            # Nothing queued — open Settings so the app has a face.
            self.open("settings")
        self._started = True
        webview.start()


def _resolve_close_target(win: Any) -> Any:
    return win
