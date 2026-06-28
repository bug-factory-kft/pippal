"""pywebview window lifecycle for the web UI.

Each PipPal surface is a pywebview window loading
``<base_url>/index.html?view=<surface>``. The static UI in ``webui/``
talks back through the injected ``js_api`` bridge (and the same HTTP
``/bridge`` endpoint as a fallback / E2E transport).

Native chrome stays minimal: Settings / Voice Manager / Onboarding /
Notices keep a frameless dark window (the UI draws its own title bar).
The reader overlay is a frameless, on-top, opaque dark mini-player (#248).

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
#
# ``window_native`` and ``window_geometry`` are also imported lazily
# (call-time) for the same reason (H3).

# Per-surface window geometry.
_SURFACES: dict[str, dict[str, Any]] = {
    "settings": {"title": "PipPal", "width": 600, "height": 720},
    "voices": {"title": "Voices", "width": 820, "height": 640},
    "onboarding": {"title": "PipPal", "width": 540, "height": 560},
    "notices": {"title": "PipPal - Open-source licences",
                "width": 760, "height": 620},
    "overlay": {"title": "PipPal", "width": 560, "height": 200,
                "on_top": True, "frameless": True, "easy_drag": False},
}


def should_activate(surface: str) -> bool:
    """True if this surface should grab foreground on open.

    Only the reader overlay shows no-activate (#265): it must never steal
    foreground during selection capture (synthetic Ctrl+C).  Every other
    surface is a user-initiated open and should raise to the foreground.
    """
    return surface != "overlay"


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
        """Store the OverlayWindowController; called once from app_web.main."""
        self._overlay_controller = controller

    def configure(self, base_url: str, bridge: Any) -> None:
        self._base_url = base_url.rstrip("/")
        self._bridge = bridge

    # ------------------------------------------------------------------

    def _make_window(self, surface: str, *, hidden: bool = False) -> Any:
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
        if hidden:
            kwargs["hidden"] = True
        # Bug 1 fix: only set on_top on NON-hidden windows.  A pre-warmed
        # hidden overlay with on_top=True becomes TOPMOST immediately; the
        # z-order shuffle in bring_to_foreground (tray Settings-reopen) then
        # surfaces the hidden overlay, causing an empty overlay pop.  Defer
        # on_top to the visible-show path (open() → show_no_activate →
        # SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE)).
        if spec.get("on_top") and not hidden:
            kwargs["on_top"] = True
        win = webview.create_window(**kwargs)

        def _closed(s: str = surface) -> None:
            with self._lock:
                self._windows.pop(s, None)

        win.events.closed += _closed

        # Apply DWM rounded corners on frameless windows once shown (H4).
        def _on_shown() -> None:
            try:
                from pippal.web_ui import window_native as _wn
                _wn.apply_dwm_round_corners(win)
            except Exception:
                pass

        win.events.shown += _on_shown

        # Bug 1 fix (belt-and-braces): on a COLD create of the overlay
        # (not the pre-warm path), re-assert no-activate once the native
        # HWND is realised so the first-ever read does not steal foreground
        # during selection capture (#265).  Intentionally skipped when
        # hidden=True: pywebview fires ``shown`` even for a hidden window,
        # so attaching this handler on the pre-warm would pop an empty
        # overlay at startup before any action is triggered.
        if surface == "overlay" and not hidden:
            def _overlay_no_activate() -> None:
                try:
                    from pippal.web_ui import window_native as _wn
                    _wn.show_no_activate(win)
                except Exception:
                    pass

            try:
                win.events.shown += _overlay_no_activate
            except Exception:
                pass

        return win

    def open(self, surface: str) -> None:
        """Show a surface, focusing it if already open. Thread-safe; can
        be called from tray / hotkey / command-server threads."""
        with self._lock:
            existing = self._windows.get(surface)
            if existing is not None:
                try:
                    if should_activate(surface):
                        existing.show()
                        existing.restore()
                        try:
                            from pippal.web_ui import window_native as _wn
                            _wn.bring_to_foreground(existing)
                        except Exception:
                            pass
                    else:
                        # overlay: re-anchor then show no-activate (#265)
                        self._anchor_overlay(existing)
                        try:
                            from pippal.web_ui import window_native as _wn
                            if not _wn.show_no_activate(existing):
                                existing.show()
                        except Exception:
                            existing.show()
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
        if surface == "overlay":
            self._anchor_overlay(win)
        with self._lock:
            self._windows[surface] = win

    def _anchor_overlay(self, win: Any) -> None:
        """Move the overlay window to its bottom-centre anchor (#280).

        Best-effort: any exception is silently swallowed (H4).
        """
        try:
            from pippal.web_ui import window_geometry as _wg
            spec = _SURFACES["overlay"]
            pos = _wg.overlay_position(spec)
            if pos is not None:
                win.move(pos["x"], pos["y"])
        except Exception:
            pass

    def hide(self, surface: str) -> None:
        """Hide a surface's window without destroying it. Thread-safe.

        Used by the overlay auto-hide path: the reader window is hidden
        (not destroyed) on idle so the next read can re-show it instantly
        and the live page (and its CDP target) survives. Falls back to
        destroy if the platform window can't hide.

        #302: overlay is exempt from the destroy fall-through — it may be
        the last live window; destroying it kills the GUI loop. Swallow the
        hide error and keep it in the live set. Other surfaces keep the
        original destroy fall-through.
        """
        with self._lock:
            win = self._windows.get(surface)
        if win is None:
            return
        try:
            win.hide()
        except Exception:
            if surface == "overlay":
                # #302: never destroy on hide failure — may be the last live
                # window; destroying it kills the GUI loop.
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

        # Bug 1 fix: pre-warm the overlay HIDDEN before the GUI loop starts
        # so the first read shows it warm (~1-2 s WebView2 init avoided) and
        # the hide→show cycle is properly initialised.  Without pre-warming,
        # the overlay is cold-created when reading starts: pywebview's GUI
        # thread creates+shows it AFTER the engine may have already finished
        # (short text), causing the "flashes open then disappears" symptom.
        # Created hidden=True → NOT on_top (see _make_window comment) so the
        # pre-warmed HWND does not surface during tray/Settings foreground
        # operations.  Best-effort: a failure must never block startup.
        with self._lock:
            overlay_already = "overlay" in self._windows
        if not overlay_already:
            try:
                overlay_win = self._make_window("overlay", hidden=True)
            except Exception:
                overlay_win = None
            if overlay_win is not None:
                with self._lock:
                    self._windows["overlay"] = overlay_win

        self._started = True
        webview.start()


def _resolve_close_target(win: Any) -> Any:
    return win
