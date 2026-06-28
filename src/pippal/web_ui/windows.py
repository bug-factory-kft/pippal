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
from collections.abc import Callable
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
        # Race guard (#race-fix): overlay show→hide race.
        # True between win.show() and the pywebview ``shown`` event.
        self._overlay_show_pending: bool = False
        # True if hide("overlay") was deferred because show was pending.
        self._overlay_hide_deferred: bool = False

    def set_overlay_controller(self, controller: Any) -> None:
        """Store the OverlayWindowController; called once from app_web.main."""
        self._overlay_controller = controller

    def configure(self, base_url: str, bridge: Any) -> None:
        self._base_url = base_url.rstrip("/")
        self._bridge = bridge

    # ------------------------------------------------------------------

    def _make_overlay_shown_guard(self, win: Any) -> Callable[[], None]:
        """Return a ``shown``-event handler that applies any deferred hide.

        ``_make_window`` wires this on the overlay window so it fires on
        every ``shown`` event (both the pre-warm's cold-create fire AND
        each real re-show).  When ``open("overlay")`` sets
        ``_overlay_show_pending=True`` before calling ``win.show()``, a
        racing ``hide("overlay")`` sets ``_overlay_hide_deferred=True``
        instead of calling ``win.hide()`` immediately.  This handler then
        clears both flags and calls ``win.hide()`` once the window is
        actually visible.  On non-pending fires (e.g. the pre-warm shown)
        it is a no-op (#race-fix).

        Also exposed as a public method so unit tests can attach the guard
        to a fake window without going through ``_make_window``.
        """
        def _guard() -> None:
            with self._lock:
                self._overlay_show_pending = False
                do_hide = self._overlay_hide_deferred
                if do_hide:
                    self._overlay_hide_deferred = False
            if do_hide:
                try:
                    win.hide()
                except Exception:
                    # #302: swallow — never destroy on failed hide.
                    pass

        return _guard

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

        # Race guard (#race-fix): wire the deferred-hide handler on ALL
        # overlay creates (hidden and non-hidden). Pre-warm fires shown with
        # _overlay_show_pending=False so it is a no-op there; real re-shows
        # (open() sets _overlay_show_pending=True first) apply any deferred
        # hide once the window is actually visible.
        if surface == "overlay":
            try:
                win.events.shown += self._make_overlay_shown_guard(win)
            except Exception:
                pass

        # Overlay loaded-kick: when the overlay page finishes loading (which
        # can happen AFTER the window was already shown during a read, because
        # WebView2 deprioritises hidden pre-warmed windows), immediately call
        # __pippalOverlayKick so the tick picks up any in-progress read state.
        # If the page loads while idle, the kick is a harmless no-op.
        if surface == "overlay":
            def _overlay_loaded_kick() -> None:
                try:
                    win.evaluate_js(
                        "window.__pippalOverlayKick"
                        " && window.__pippalOverlayKick()"
                    )
                except Exception:
                    pass

            try:
                win.events.loaded += _overlay_loaded_kick
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
                        # overlay: mark show pending BEFORE calling show() so
                        # a racing hide() is deferred until shown fires (#race-fix).
                        self._overlay_show_pending = True
                        self._overlay_hide_deferred = False
                        # overlay: re-anchor then show.
                        self._anchor_overlay(existing)
                        # Call pywebview show() FIRST so its 'shown' event fires
                        # and the race guard (_make_overlay_shown_guard) can clear
                        # _overlay_show_pending and apply any deferred hide.
                        # show_no_activate() bypasses pywebview's own show path so
                        # its 'shown' event never fires, leaving _overlay_show_pending
                        # stuck True and deferred hides never applied (empty overlay).
                        # After pywebview show(), re-assert NOACTIVATE via Win32 so
                        # the overlay does not steal foreground during capture (#265).
                        # Mirrors Pro window_lifecycle.py open() (lines 324-366).
                        try:
                            existing.show()
                        except Exception:
                            pass
                        try:
                            from pippal.web_ui import window_native as _wn
                            _wn.show_no_activate(existing)
                        except Exception:
                            pass
                        # A2 overlay kick: force immediate tick after show
                        # (Pro window_lifecycle.py ~lines 358-361 parity).
                        # Best-effort: evaluate_js no-ops if window not ready.
                        try:
                            existing.evaluate_js(
                                "window.__pippalOverlayKick"
                                " && window.__pippalOverlayKick()"
                            )
                        except Exception:
                            pass
                    return
                except Exception:
                    # Reset race guard if open() failed — no shown will fire.
                    if surface == "overlay":
                        self._overlay_show_pending = False
                        self._overlay_hide_deferred = False
                    self._windows.pop(surface, None)

        if not self._started:
            # First window must be created before webview.start(); queue
            # it so run() picks it up.
            win = self._make_window(surface)
            with self._lock:
                if surface == "overlay":
                    self._overlay_show_pending = True
                    self._overlay_hide_deferred = False
                self._windows[surface] = win
            return

        win = self._make_window(surface)
        if surface == "overlay":
            self._anchor_overlay(win)
        with self._lock:
            if surface == "overlay":
                self._overlay_show_pending = True
                self._overlay_hide_deferred = False
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

        Race guard (#race-fix): if the overlay's ``shown`` event has not
        yet fired (``_overlay_show_pending`` is True), defer the hide so
        the window can fully appear before it is hidden. The
        ``_make_overlay_shown_guard`` handler picks up the deferred hide
        once ``shown`` fires.
        """
        with self._lock:
            win = self._windows.get(surface)
            # Race guard: hide arrived before pywebview shown event --
            # defer to the shown handler so the window is visible first.
            if surface == "overlay" and self._overlay_show_pending:
                self._overlay_hide_deferred = True
                return
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
