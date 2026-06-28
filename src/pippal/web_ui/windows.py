"""pywebview window lifecycle for the PipPal web UI.

Provides one frameless dark pywebview
window per surface loading ``<base_url>/index.html?view=<surface>`` —
and adds the reader overlay surface.  The reader overlay is a normal
opaque frameless window, built the same way as the Settings window
(solid dark background, draggable via the pywebview-drag-region
mechanism, fully clickable).

NOTE (R1 / Constraint 2): this module is loaded BY FILE PATH with a
synthetic module name by the regression test harness
(``importlib.util.spec_from_file_location``), so it has NO package
context.  A top-level intra-package import (relative OR absolute) would
raise ``ImportError`` at load time.  The window-surface table, the
Win32/DWM native-window ops, the pure geometry helpers, and the window
lifecycle (make_window/open/hide/close/...) therefore live in sibling
modules (``window_lifecycle.py`` / ``window_native.py`` /
``window_geometry.py``) and are imported LAZILY at call time via the
``_lifecycle()`` / ``_native()`` / ``_geometry()`` shims (absolute
import with a file-path fallback).  Do NOT add any ``from . import ...``
or ``from pippal... import ...`` at module top level here.

``WebWindowManager``'s public API (every method name + signature) is
unchanged: the methods whose bodies moved remain as thin delegators on
the class, so callers (``app_web``) and the bridge server allow-list see
no difference.
"""

from __future__ import annotations

import sys
import threading
from typing import Any


def _sibling(name: str) -> Any:
    """Lazily import a sibling helper module by short *name* (R1 shim).

    Imports at CALL time, not module-load time, so ``windows.py`` stays
    file-path-loadable (Constraint 2).

    Two execution contexts must both work:

    1. **Normal package run** — ``windows.py`` was imported as
       ``pippal.web_ui.windows`` (``__package__ == "pippal.web_ui"``).
       Use the normal absolute import; the sibling is a real, cached
       package module that binds the real ``webview``.
    2. **Synthetic file-path loader** (the regression harness loads
       ``windows.py`` via ``spec_from_file_location`` with a synthetic
       name, so ``__package__`` is empty / not the real package). In this
       context the absolute import would either fail OR — worse — return a
       STALE cached real-package sibling that bound a different ``webview``
       than the one the test monkeypatched into ``sys.modules`` for THIS
       load. So when we are NOT in the real package we ALWAYS load the
       sibling FRESH from its file path next to ``__file__``; the fresh
       module's top-level ``import webview`` then binds the currently-
       patched ``webview``, exactly as the original single-file
       ``windows.py`` did when it was re-exec'd per test.

    This is a pure import bridge — the moved function bodies run verbatim;
    only their import path is bridged."""
    in_real_package = __package__ == "pippal.web_ui"
    if in_real_package:
        import importlib

        return importlib.import_module(f"pippal.web_ui.window_{name}")

    import importlib.util
    import pathlib

    p = pathlib.Path(__file__).with_name(f"window_{name}.py")
    spec = importlib.util.spec_from_file_location(f"_ppw_{name}", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def __getattr__(name: str) -> Any:
    """PEP 562 module-level lazy attribute resolver.

    Keeps ``windows._SURFACES`` accessible (the surface table now lives in
    the ``window_lifecycle`` sibling) WITHOUT a top-level intra-package
    import (R1 / Constraint 2) and without duplicating the table.  Callers
    and tests that read ``windows._SURFACES`` see the identical dict; the
    fetch is lazy (at attribute-access time) so module load stays
    file-path-safe."""
    if name == "_SURFACES":
        return _sibling("lifecycle")._SURFACES
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _lifecycle() -> Any:
    """Lazily import the sibling ``window_lifecycle`` module (R1 shim)."""
    return _sibling("lifecycle")


def _native() -> Any:
    """Lazily import the sibling ``window_native`` module (R1 shim)."""
    return _sibling("native")


def _geometry() -> Any:
    """Lazily import the sibling ``window_geometry`` module (R1 shim)."""
    return _sibling("geometry")


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
        self._explicit_close = False
        self._overlay_controller: Any = None  # set via set_overlay_controller()

    def set_overlay_controller(self, controller: Any) -> None:
        """Wire the OverlayWindowController so raise_window can consult its
        engine-visible state before deciding whether to re-hide the overlay.

        Called once from app_web.main() right after overlay.set_window_callbacks.
        When not called (tests / early startup), the controller is None and
        raise_window defaults to treating the overlay as not-visible (safe).
        """
        self._overlay_controller = controller

    def configure(self, base_url: str, bridge: Any) -> None:
        self._base_url = base_url.rstrip("/")
        self._bridge = bridge

    def _make_window(self, surface: str, *, hidden: bool = False) -> Any:
        """Create a pywebview window for *surface* (#248/#265/#280 wiring).

        Thin delegator to :func:`window_lifecycle.make_window` (R1 shim);
        the body moved verbatim into the sibling lifecycle module.  When
        *hidden* is True the window is created hidden (BUG 1: tray-only
        normal launch keeps the GUI loop alive without a visible Settings
        window)."""
        return _lifecycle().make_window(self, surface, hidden=hidden)

    def _host_hwnd(self, win: Any) -> int | None:
        """Return the native top-level HWND of a pywebview window, or None.

        Thin delegator to :func:`window_native.host_hwnd` (R1 shim); the
        body moved verbatim into the sibling native module."""
        return _native().host_hwnd(win)

    def _schedule_transparency(self, win: Any) -> None:
        """Apply the layered colour-key to *win* off the GUI thread, with
        a short retry so it lands once the native HWND exists and survives
        the WebView2 repaint that follows show/restore.

        Runs on a daemon thread because the native handle / first paint can
        lag the ``open`` call by a beat; a few spaced re-applies make the
        transparency deterministic without blocking the caller (engine /
        bridge thread).  All failures are swallowed — transparency is
        best-effort and must never break the read path."""
        if sys.platform != "win32":
            return

        def _runner() -> None:
            import time as _t

            # Re-apply over ~1.5 s: the host is created, then WebView2
            # paints (which can reset the layered state), so spacing the
            # applies makes the final state transparent regardless of the
            # paint timing.
            for delay in (0.0, 0.15, 0.35, 0.7, 1.2):
                if delay:
                    _t.sleep(delay)
                try:
                    self._apply_layered_colorkey(win)
                except Exception:
                    pass

        try:
            threading.Thread(target=_runner, daemon=True).start()
        except Exception:
            # Synchronous fallback if a thread can't be spawned.
            try:
                self._apply_layered_colorkey(win)
            except Exception:
                pass

    def _apply_dwm_round_corners(self, win: Any) -> None:
        """Apply Win11 DWM rounded corners to a frameless pywebview window (#248).

        Thin delegator to :func:`window_native.apply_dwm_round_corners`
        (R1 shim); the body moved verbatim into the sibling native module."""
        return _native().apply_dwm_round_corners(win)

    def _apply_layered_colorkey(self, win: Any) -> None:
        """Make a transparent-spec host genuinely transparent (#248).

        Thin delegator to :func:`window_native.apply_layered_colorkey`
        (R1 shim); the body moved verbatim into the sibling native module."""
        return _native().apply_layered_colorkey(win)

    def _show_no_activate(self, win):
        """Show *win* WITHOUT stealing foreground focus (ISSUE 2 / #265).

        Thin delegator to :func:`window_native.show_no_activate` (R1 shim);
        the body moved verbatim into the sibling native module."""
        return _native().show_no_activate(win)

    def _window_position(
        self,
        surface: str,
        spec: dict[str, Any],
    ) -> dict[str, int] | None:
        # #280: The reader overlay ALWAYS opens at the bottom-center of the
        # active screen — never at a saved/restored position.  Restoring a
        # stale position can place the overlay far from the text the user is
        # reading (different corner, wrong monitor).  The overlay is a
        # transient HUD, not a persistent window, so user-dragged positions
        # are intentionally discarded on re-open.
        if surface == "overlay":
            return self._overlay_position(spec)
        saved = self._saved_window_position(surface)
        if saved is not None:
            # B3: clamp — if the saved rect is entirely off all current
            # screens (e.g. the monitor was disconnected since last run)
            # fall back to the default placement so the window is reachable.
            if self._position_on_any_screen(saved, spec):
                return saved
            # Saved position is off-screen — fall through to default.
        if surface != "settings":
            # Non-settings surfaces (onboarding, voices, notices, etc.) open
            # centred on the settings window when it exists.  At FIRST launch
            # there is no settings window yet → _centered_on_parent returns
            # None.  Fall back to _centered_on_screen so the window is not
            # abandoned at the OS-default top-left corner.  Fixes #247:
            # onboarding opens screen-centred on first launch.
            pos = self._centered_on_parent(spec)
            return pos if pos is not None else self._centered_on_screen(spec)
        # settings — first launch: no saved position → centre on screen.
        return self._centered_on_screen(spec)

    def _saved_window_position(self, surface: str) -> dict[str, int] | None:
        bridge = self._bridge
        config = getattr(bridge, "config", None)
        if not isinstance(config, dict):
            return None
        positions = config.get("window_positions")
        if not isinstance(positions, dict):
            return None
        position = positions.get(surface)
        if not isinstance(position, dict):
            return None
        x = self._valid_position_value(position.get("x"))
        y = self._valid_position_value(position.get("y"))
        if x is None or y is None:
            return None
        return {"x": x, "y": y}

    def _valid_position_value(self, value: Any) -> int | None:
        """Thin delegator to :func:`window_geometry.valid_position_value`
        (R1 shim); the body moved verbatim into the sibling geometry module."""
        return _geometry().valid_position_value(value)

    def _persist_window_position(self, surface: str, win: Any, *, flush: bool = True) -> None:
        """Write the current x/y of *win* into config['window_positions'][surface].

        When *flush* is True (default, used by the closing handler) the
        updated config is also written to disk via save_config.  When
        *flush* is False (used by the moved/resized handlers during drag)
        only the in-memory dict is updated — this avoids hundreds of disk
        writes per drag gesture.

        No-ops silently if the bridge/config is not wired (served / test
        mode without a config dict) or if the window object does not expose
        x/y.
        """
        bridge = self._bridge
        config = getattr(bridge, "config", None)
        if not isinstance(config, dict):
            return
        try:
            x = int(win.x)
            y = int(win.y)
        except (AttributeError, TypeError, ValueError):
            return
        positions = config.setdefault("window_positions", {})
        if not isinstance(positions, dict):
            return
        positions[surface] = {"x": x, "y": y}
        if flush:
            # Best-effort flush to disk via the core save_config helper.
            try:
                from pippal.config import save_config  # type: ignore[import-untyped]

                save_config(config)
            except Exception:
                pass

    def _centered_on_parent(self, spec: dict[str, Any]) -> dict[str, int] | None:
        with self._lock:
            parent = self._windows.get("settings")
        if parent is None:
            return None
        try:
            x = int(parent.x) + (int(parent.width) - int(spec["width"])) // 2
            y = int(parent.y) + (int(parent.height) - int(spec["height"])) // 2
        except (AttributeError, TypeError, ValueError):
            return None
        return {"x": x, "y": y}

    def _centered_on_screen(self, spec: dict[str, Any]) -> dict[str, int] | None:
        """Thin delegator to :func:`window_geometry.centered_on_screen`
        (R1 shim); the body moved verbatim into the sibling geometry module."""
        return _geometry().centered_on_screen(spec)

    def _position_on_any_screen(
        self,
        position: dict[str, int],
        spec: dict[str, Any],
    ) -> bool:
        """Thin delegator to :func:`window_geometry.position_on_any_screen`
        (R1 shim); the body moved verbatim into the sibling geometry module."""
        return _geometry().position_on_any_screen(position, spec)

    def _overlay_position(self, spec: dict[str, Any]) -> dict[str, int] | None:
        """Thin delegator to :func:`window_geometry.overlay_position`
        (R1 shim); the body moved verbatim into the sibling geometry module."""
        return _geometry().overlay_position(spec)

    def open(self, surface: str) -> None:
        """Show a surface, focusing it if already open. Thread-safe.

        Thin delegator to :func:`window_lifecycle.open` (R1 shim); the body
        moved verbatim into the sibling lifecycle module (#249 load_url
        re-render, #280/#2/#4 overlay re-anchor, #265 no-activate)."""
        return _lifecycle().open(self, surface)

    def raise_window(self, surface: str = "settings") -> None:
        """Open *surface* and pull it to the foreground (#FIX2).

        Used by the single-instance gate: when a SECOND launch happens (or
        the user clicks the tray notification), the running instance OPENS
        + foregrounds its main window instead of only printing an
        "already running" message.  After the start-to-tray change the app
        may have no visible window, so this is how the user re-opens it.

        Opens via the normal lifecycle path (which show()/restore()s) then
        asserts Win32 foreground so the window is genuinely raised above
        the caller's window.  Thread-safe; no-op-safe off Windows.

        TOAST-REOPEN FIX (EDIT 1): After the foreground raise, if we are
        raising any surface OTHER than the overlay, and the engine is NOT
        currently driving a visible overlay session, actively re-hide the
        pre-warmed overlay window.  On WebView2/pywebview the TOPMOST /
        foreground z-order shuffle in bring_to_foreground surfaces the
        hidden-but-TOPMOST pre-warmed overlay — causing an empty overlay to
        pop when the user clicks the tray toast to reopen Settings.  Re-
        hiding it here is defense-in-depth: best-effort, never breaks reads."""
        self.open(surface)
        with self._lock:
            win = self._windows.get(surface)
        if win is not None:
            try:
                _native().bring_to_foreground(win)
            except Exception:
                # Foregrounding is best-effort: the window is already
                # shown by open(); a foreground failure must never crash.
                pass
        # EDIT 1: re-hide the overlay after any non-overlay raise when the
        # engine is NOT currently driving a visible overlay state.
        # Wrapped in outer try/except so raise_window can NEVER throw.
        try:
            if surface != "overlay":
                controller = self._overlay_controller
                overlay_engine_visible = False
                if controller is not None:
                    try:
                        overlay_engine_visible = bool(controller.overlay_window_visible())
                    except Exception:
                        pass
                if not overlay_engine_visible:
                    try:
                        self.hide("overlay")
                    except Exception:
                        pass
        except Exception:
            pass

    def hide(self, surface: str) -> None:
        """Hide a surface's window without destroying it. Thread-safe.

        Thin delegator to :func:`window_lifecycle.hide` (R1 shim); the body
        moved verbatim into the sibling lifecycle module (#302/BUG2 overlay
        never-destroy on failed hide)."""
        return _lifecycle().hide(self, surface)

    def surface_for_window(self, win: Any) -> str | None:
        """Return the surface name for a pywebview window object, or None.

        Thin delegator to :func:`window_lifecycle.surface_for_window`
        (R1 shim); the body moved verbatim into the sibling lifecycle
        module."""
        return _lifecycle().surface_for_window(self, win)

    def close(self, surface: str) -> None:
        """Close a specific surface window by name. Thread-safe.

        Thin delegator to :func:`window_lifecycle.close` (R1 shim); the body
        moved verbatim into the sibling lifecycle module (#261/#284
        hide-not-destroy surfaces)."""
        return _lifecycle().close(self, surface)

    def close_active(self) -> None:
        """Thin delegator to :func:`window_lifecycle.close_active` (R1 shim);
        the body moved verbatim into the sibling lifecycle module."""
        return _lifecycle().close_active(self)

    def shutdown(self) -> None:
        """Thin delegator to :func:`window_lifecycle.shutdown` (R1 shim);
        the body moved verbatim into the sibling lifecycle module."""
        return _lifecycle().shutdown(self)

    def run(self) -> None:
        """Block on the pywebview GUI loop until all windows close.

        Thin delegator to :func:`window_lifecycle.run` (R1 shim); the body
        moved verbatim into the sibling lifecycle module."""
        return _lifecycle().run(self)
