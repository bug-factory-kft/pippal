"""Window lifecycle operations for the PipPal Pro web UI.

Extracted VERBATIM from :mod:`pippal_pro.web_ui.windows` so that
``windows.py`` stays under the line-count guard and remains directly
file-path-loadable by the regression test harness (which loads
``windows.py`` via :func:`importlib.util.spec_from_file_location` with a
synthetic module name and therefore has NO package context).

Each function takes the :class:`WebWindowManager` instance as its first
argument (``mgr``) and reads/writes its state (``mgr._windows``,
``mgr._lock``, ``mgr._bridge``, ...) and calls back into the manager's
own methods exactly as the original methods did via ``self``.  No
behaviour change — only the ``self`` receiver became an explicit ``mgr``
parameter so the bodies live in a sibling module.

``windows.py`` calls these through a lazy ``_lifecycle()`` shim (absolute
import with a file-path fallback) so the file-path loader still works.

Behaviour preserved: #248 (transparency / DWM corner wiring), #265 /
ISSUE 2 (overlay no-activate on cold create + re-show), #280 / #2 / #4
(overlay re-anchor), #302 / BUG2 (overlay never-destroy in ``hide``),
#249 (load_url on re-open), #261 / #284 (hide-not-destroy surfaces).
"""

from __future__ import annotations

from typing import Any

import webview

_SURFACES: dict[str, dict[str, Any]] = {
    "settings": {"title": "PipPal Pro", "width": 600, "height": 760},
    "voices": {"title": "Voices", "width": 820, "height": 640},
    "onboarding": {"title": "PipPal Pro", "width": 540, "height": 560},
    "notices": {"title": "PipPal Pro - Open-source licences", "width": 760, "height": 620},
    "release": {"title": "PipPal Pro - What's new", "width": 780, "height": 620},
    "moods": {"title": "PipPal Pro - Moods", "width": 540, "height": 620},
    # Wave 2 — document import (F1 PDF/TXT + F4 cleanup).
    "import": {"title": "PipPal Pro - Import document", "width": 680, "height": 700},
    # Wave 3 — listen-later queue (F3).
    "queue": {"title": "PipPal Pro - Listen Later", "width": 680, "height": 700},
    # R3 — read history / recent view.
    "recent": {"title": "PipPal Pro - History", "width": 680, "height": 700},
    # Play-sample preview (#248): compact transparent panel sized to its
    # content.  Uses the overlay A2 pattern: transparent=True so the
    # page's panel owns the visible surface; no opaque host background.
    "sample": {
        "title": "PipPal Pro",
        "width": 480,
        "height": 220,
        "frameless": True,
        "easy_drag": True,
        "transparent": True,
    },
    # The reader overlay / mini-player is a NORMAL opaque frameless window
    # — built the same way as the Settings window (solid dark background
    # #13151c, no transparency machinery, fully clickable).
    #
    # Re-architecture (#248 decisive fix): the previous transparent /
    # WS_EX_LAYERED / colour-key approach was fundamentally broken on this
    # pywebview 6.x + WebView2 stack:
    #   1. The layered colour-key made the host CLICK-THROUGH — buttons
    #      did not respond.
    #   2. The window was not draggable.
    #   3. Rounded corners required fragile DWM hacks.
    #   4. No proper header/body/footer structure — short content collapsed.
    #
    # The fix: make the overlay a normal opaque frameless window with the
    # dark Settings background (#13151c).  Dragging is handled by the
    # pywebview-drag-region mechanism (same as Settings/other windows via
    # easy_drag=False + .pywebview-drag-region on the header).  This
    # trivially fixes all four regressions — no transparency, no click-
    # through, no size fragility, stable layout.
    #
    # Window dimensions: comfortable mini-player size.  NOT DPI-fragile
    # (no transparency margin to compensate for).
    #   width:  560 px — wider mini-player: transport buttons + label have
    #           comfortable breathing room, body text fits several words per
    #           line (#280: was 420 px, which felt narrow).
    #   height: 200 px — header(44px) + body(flex:1, min 80px) + footer(40px)
    #                    + padding + border
    "overlay": {
        "title": "PipPal Pro",
        "width": 560,
        "height": 200,
        "on_top": True,
        "frameless": True,
        "easy_drag": False,  # drag handled by .pywebview-drag-region in header
    },
}


def make_window(mgr: Any, surface: str, *, hidden: bool = False) -> Any:
    spec = _SURFACES.get(surface, _SURFACES["settings"])
    url = f"{mgr._base_url}/index.html?view={surface}"
    position = mgr._window_position(surface, spec)
    kwargs: dict[str, Any] = {
        "title": spec["title"],
        "url": url,
        "width": spec["width"],
        "height": spec["height"],
        "js_api": mgr._bridge,
        "frameless": spec.get("frameless", True),
        "easy_drag": spec.get("easy_drag", False),
    }
    if hidden:
        # Start the window HIDDEN so the pywebview GUI loop has a window to
        # keep alive WITHOUT popping a visible surface.  Used by run() on a
        # normal (already-activated) launch so the app starts straight to
        # the tray (the startup toast tells the user where it is); the tray
        # "Settings…" item / hotkeys later show() this same hidden window.
        kwargs["hidden"] = True
    if not spec.get("transparent"):
        kwargs["background_color"] = "#13151c"
    if position is not None:
        kwargs.update(position)
    if spec.get("on_top") and not hidden:
        # EDIT 2: only carry the TOPMOST band on NON-hidden windows.  The
        # pre-warmed overlay is created hidden=True at startup; setting on_top
        # on a hidden window means the live HWND is already TOPMOST, and the
        # TOPMOST / foreground z-order shuffle in bring_to_foreground (on the
        # Settings toast-reopen path) surfaces the hidden topmost overlay,
        # causing an empty overlay pop.  Deferring on_top to the visible-show
        # path (open() → _show_no_activate → SetWindowPos(HWND_TOPMOST)) means
        # the pre-warmed overlay starts with normal z-order and is only pinned
        # topmost when a genuine read shows it.  EDIT 1 is the primary fix;
        # this is defense-in-depth (belt-and-braces hardening, #265/#284 safe).
        kwargs["on_top"] = True
    if spec.get("transparent"):
        kwargs["transparent"] = True
    # Note: pywebview ≥6.x does not expose a `parent` kwarg on
    # create_window; child-window z-order is managed by the OS on
    # Windows for windows in the same process without explicit
    # parent wiring.  The kwarg was removed to prevent a
    # TypeError → HTTP 500 when open_moods_window (and other
    # secondary-window openers) are called via the bridge server.
    win = webview.create_window(**kwargs)

    # Lifecycle trace (metadata-only): which surface was opened.  Non-blocking;
    # no-op when diagnostics are off.  ``surface`` is a fixed identifier
    # ("settings"/"overlay"/...), never user content.
    try:
        from pippal.diag_trace import lifecycle_event

        lifecycle_event("window_opened", surface=str(surface))
    except Exception:
        pass

    if spec.get("transparent"):
        # #248 — the WebView2 ``DefaultBackgroundColor = Transparent``
        # pywebview applies for ``transparent=True`` does NOT make the
        # WinForms host Form transparent on this stack, so the host
        # paints an opaque #f0f0f0 rectangle behind the panel.  Apply a
        # Win32 layered colour-key to the host HWND once the native
        # window exists so the empty host area genuinely shows the
        # desktop through (only the rounded panel paints).  Wired on
        # both ``shown`` and ``loaded`` (whichever fires; idempotent)
        # because ``native``/``Handle`` is only valid after creation.
        def _apply_transparency() -> None:
            mgr._apply_layered_colorkey(win)

        # ``shown`` fires when the host HWND is realised; ``loaded``
        # fires after the page loads.  Wire both (idempotent) so the
        # key is applied as soon as the native handle is valid and is
        # re-asserted after any backend repaint on load.
        try:
            win.events.shown += _apply_transparency
        except Exception:
            pass
        try:
            win.events.loaded += _apply_transparency
        except Exception:
            pass
    else:
        # #248 — apply Win11 DWM rounded corners to all non-transparent
        # frameless windows (overlay, settings, voices, etc.).
        #
        # Windows 11 auto-rounds FRAMED windows via DWM, but FRAMELESS
        # windows (pywebview uses FormBorderStyle.None) do NOT get rounded
        # corners automatically — they need an explicit
        # DwmSetWindowAttribute(DWMWA_WINDOW_CORNER_PREFERENCE,
        # DWMWCP_ROUND) call.  This is why the overlay had square corners
        # while Settings appeared rounded after the re-arch: both are
        # frameless, and neither had the call, but the overlay (on_top)
        # may have a subtly different DWM treatment on some Win11 builds.
        # Applying the explicit call uniformly to all frameless opaque
        # windows makes all corners match on every Win11 version.
        def _apply_round_corners() -> None:
            mgr._apply_dwm_round_corners(win)

        try:
            win.events.shown += _apply_round_corners
        except Exception:
            pass

    if surface == "settings":

        def _closing() -> bool:
            if mgr._explicit_close:
                return True
            # Flush position to disk on close so the last user-chosen
            # position survives across launches.
            mgr._persist_window_position(surface, win, flush=True)
            try:
                win.hide()
            except Exception:
                pass
            return False

        win.events.closing += _closing

        # pywebview ≥5.0 exposes moved/resized events on Window.events.
        # Update in-memory position only — disk flush happens in _closing
        # so drag/resize doesn't trigger hundreds of disk writes.
        def _moved() -> None:
            try:
                mgr._persist_window_position(surface, win, flush=False)
            except Exception:
                pass

        def _resized() -> None:
            try:
                mgr._persist_window_position(surface, win, flush=False)
            except Exception:
                pass

        try:
            win.events.moved += _moved
        except Exception:
            pass
        try:
            win.events.resized += _resized
        except Exception:
            pass

    if surface == "overlay" and not hidden:
        # ISSUE 2 — on the COLD create (a real action trigger) the overlay
        # must appear WITHOUT stealing the foreground (create_window shows it
        # activated). Re-assert no-activate once the native HWND is realised
        # so even a first-ever read keeps the user's app in the foreground
        # (#265 belt-and-braces). Best-effort; never break window creation.
        #
        # IMPORTANT: this handler is intentionally skipped when hidden=True
        # (the pre-warm path in run()). In real WebView2 the ``shown`` event
        # fires even for a window created with hidden=True, so attaching
        # _overlay_no_activate unconditionally would call _show_no_activate
        # on the hidden pre-warmed window at startup and pop an empty overlay
        # before any action is triggered. The re-show path (open() →
        # mgr._show_no_activate(existing) at ~line 305) already ensures the
        # no-activate show for every real read/AI/WAV trigger, so this
        # handler is only needed on a non-hidden cold create.
        def _overlay_no_activate() -> None:
            try:
                mgr._show_no_activate(win)
            except Exception:
                pass

        try:
            win.events.shown += _overlay_no_activate
        except Exception:
            pass

    def _closed(s: str = surface) -> None:
        with mgr._lock:
            mgr._windows.pop(s, None)

    win.events.closed += _closed
    return win


def open(mgr: Any, surface: str) -> None:
    """Show a surface, focusing it if already open. Thread-safe.

    For all surfaces the existing window is shown in-place without any
    URL navigation.  Data is refreshed via ``window.__pippalRefresh``
    (registered in main.js during boot) which re-renders only the DOM
    without re-running wireFooter(), so button listeners survive
    hide->show cycles intact.

    This supersedes the #319 nonce-reload (``load_url(&_t=<ms>)``),
    which was a documented pywebview anti-pattern: ``load_url`` tears
    down the ``js_api`` bridge (GitHub issues #238, #1674, #1290) and
    causes a blank/empty window on reopen.  The bridge SURVIVES
    ``hide()->show()`` without reload (#1218).

    #249 data freshness: preserved -- ``__pippalRefresh`` re-fetches
    ``get_config()`` / ``get_queue()`` / etc. on every reopen.

    The overlay branch is byte-unchanged (already no-reload).
    """
    spec = _SURFACES.get(surface, _SURFACES["settings"])
    _reopened = False

    with mgr._lock:
        existing = mgr._windows.get(surface)
        if existing is not None:
            try:
                if surface != "overlay":
                    # No-reload reopen (Approach c -- supersedes #319 nonce).
                    # The bridge survives hide()->show(); load_url breaks it.
                    # In-place refresh is fired below via evaluate_js.
                    pass
                else:
                    # #280 re-anchor: the reader overlay must ALWAYS
                    # re-open at its default active-screen anchor, NEVER
                    # at the position the user last dragged it to. The
                    # _window_position() default path is only consulted
                    # on FIRST creation (_make_window); on this re-show
                    # path the live window still carries the dragged
                    # coordinates, so we explicitly MOVE it back to the
                    # overlay anchor BEFORE showing. The move runs before
                    # _show_no_activate so it never activates/steals the
                    # foreground (#265): move() only repositions; the
                    # subsequent SW_SHOWNOACTIVATE + SWP_NOACTIVATE keep
                    # the user's app in the foreground during capture.
                    anchor = mgr._overlay_position(spec)
                    if anchor is not None:
                        try:
                            existing.move(anchor["x"], anchor["y"])
                        except Exception:
                            # move() is best-effort; a failure must never
                            # block the overlay re-show.
                            pass
                existing.show()
                existing.restore()
                # Non-overlay: kick the in-place data refresh hook
                # registered during boot.  Mirroring the overlay kick;
                # guarded (&&) so it is a no-op if not yet registered.
                # Swallow exceptions -- evaluate_js is best-effort.
                if surface != "overlay":
                    try:
                        existing.evaluate_js(
                            "window.__pippalRefresh"
                            " && window.__pippalRefresh()"
                        )
                    except Exception:
                        pass
                # ISSUE 2 — for the overlay, immediately RE-ASSERT a
                # topmost no-activate state so the pop does not hold the
                # foreground: the user's app keeps focus/caret while the
                # overlay shows the loader (belt-and-braces for #265).
                # show()/restore() above keep pywebview's own window
                # state consistent; _show_no_activate then drops the
                # foreground steal via Win32 (no-op off Windows / in
                # tests, where it just leaves the shown window visible).
                if surface == "overlay":
                    mgr._show_no_activate(existing)
                    # A2 — trigger-driven JS fast-kick: immediately after
                    # re-showing the overlay window, call the guarded global
                    # that forces _setTickRate(true) + a synchronous tick().
                    # This ensures the JS poll notices the new engine state
                    # (loading/thinking) INSTANTLY instead of waiting up to
                    # 2000 ms for the next slow idle heartbeat.  The guard
                    # (&&) makes it a no-op if the overlay JS hasn't rendered
                    # yet (cold create) or on the core public frontend where
                    # the function is absent — always safe to evaluate.
                    try:
                        existing.evaluate_js(
                            "window.__pippalOverlayKick"
                            " && window.__pippalOverlayKick()"
                        )
                    except Exception:
                        # evaluate_js is best-effort — a failure (e.g. the
                        # WebView2 context not yet ready) must never block the
                        # overlay re-show.  The slow poll is the fallback.
                        pass
                # #248 — re-assert the layered colour-key on every
                # re-show of a transparent surface: the WebView2
                # repaint on show/restore can drop the host's layered
                # transparency, so re-applying here keeps the overlay
                # host transparent across hide → re-show cycles.
                if spec.get("transparent"):
                    mgr._schedule_transparency(existing)
                # Mark the reopen path taken.  Return is deferred to
                # OUTSIDE the lock so we can wait for load completion
                # without risking deadlock on _closed/_closing handlers.
                _reopened = True
            except Exception:
                mgr._windows.pop(surface, None)

    if _reopened:
        return

    if not mgr._started:
        win = mgr._make_window(surface)
        with mgr._lock:
            mgr._windows[surface] = win
        if spec.get("transparent"):
            mgr._schedule_transparency(win)
        return

    win = mgr._make_window(surface)
    with mgr._lock:
        mgr._windows[surface] = win
    if spec.get("transparent"):
        mgr._schedule_transparency(win)


def hide(mgr: Any, surface: str) -> None:
    """Hide a surface's window without destroying it. Thread-safe.

    Used by the overlay auto-hide path: the reader window is hidden
    (not destroyed) on idle so the next read can re-show it instantly
    and the live page (and its CDP target) survives. Falls back to
    destroy if the platform window can't hide.

    BUG2 — the OVERLAY is the EXCEPTION to that fall-through.  The
    overlay window is frequently the foreground / last live pywebview
    window; destroying it (the historical fall-through when
    ``win.hide()`` raised) takes the GUI loop's last window with it and
    the WHOLE app disappears.  So for the overlay we NEVER destroy on a
    failed hide: we keep the window object in the live set (the GUI loop
    keeps a window) and swallow the hide error.  Other surfaces keep the
    original destroy fall-through (a transient settings/sample window is
    safe to tear down).  This guarantees at least one window always
    keeps the GUI loop alive across a reading→thinking→reading
    document switch."""
    with mgr._lock:
        win = mgr._windows.get(surface)
    if win is None:
        return
    try:
        win.hide()
    except Exception:
        if surface == "overlay":
            # NEVER destroy the overlay: it is (typically) the
            # foreground / last live window and destroying it kills the
            # pywebview GUI loop → the app vanishes (BUG2).  Keep it in
            # the live-window set and swallow the hide failure; the next
            # read re-shows it and the GUI loop stays alive.
            return
        try:
            win.destroy()
        except Exception:
            pass
        with mgr._lock:
            mgr._windows.pop(surface, None)


def surface_for_window(mgr: Any, win: Any) -> str | None:
    """Return the surface name for a pywebview window object, or None."""
    with mgr._lock:
        for surface, w in mgr._windows.items():
            if w is win:
                return surface
    return None


def close(mgr: Any, surface: str) -> None:
    """Close a specific surface window by name. Thread-safe.

    For the ``settings`` and ``onboarding`` surfaces this hides the
    window instead of destroying it so the tray app keeps running and
    can re-open the window on demand (X-button / Finish-setup →
    tray → First-run-check).  All other surfaces are destroyed.

    The ``onboarding`` surface hides on close (#261: Finish setup
    hides to tray so ``windows.open("onboarding")`` can re-show it;
    destroying would require a full ``_make_window`` on each re-open).

    This is the preferred target for ``on_close_window`` wiring so the
    X button in any surface closes *that* window, not the last-opened
    window as the old ``close_active()`` heuristic did.
    """
    with mgr._lock:
        win = mgr._windows.get(surface)
    if win is None:
        return
    if surface in (
        "settings",
        "onboarding",
        # #284 — frequently-used surfaces: hide instead of destroy so
        # the next open() reuses the existing WebView2 window instantly
        # (show/restore + evaluate_js(__pippalRefresh)) rather than paying
        # 1-2 s for a full WebView2 init on every hotkey press.
        "moods",
        "voices",
        "import",
        "queue",
        "release",
        "recent",
    ):
        try:
            win.hide()
        except Exception:
            pass
    else:
        try:
            win.destroy()
        except Exception:
            pass


def close_active(mgr: Any) -> None:
    with mgr._lock:
        wins = list(mgr._windows.items())
    target = None
    for _surface, w in wins:
        try:
            if getattr(w, "gui", None) is not None and w.on_top is False:
                target = w
        except Exception:
            pass
    if target is None and wins:
        target = wins[-1][1]
    if target is not None:
        try:
            target.destroy()
        except Exception:
            pass


def shutdown(mgr: Any) -> None:
    with mgr._lock:
        wins = list(mgr._windows.values())
    mgr._explicit_close = True
    for w in wins:
        try:
            w.destroy()
        except Exception:
            pass
    with mgr._lock:
        mgr._windows.clear()
    try:
        webview.windows.clear()
    except Exception:
        pass


def run(mgr: Any) -> None:
    """Block on the pywebview GUI loop until all windows close.

    BUG 1 — on a NORMAL (already-activated) launch the app must start
    straight to the TRAY: no Settings window is popped (the startup tray
    toast tells the user where the app is; the tray menu + global hotkeys
    open windows on demand).  But pywebview needs at least one live window
    to keep its GUI loop alive, so when no surface was opened during
    startup (e.g. first-run onboarding did NOT fire) we create the Settings
    window HIDDEN — the loop stays alive, nothing visible pops, and the
    tray "Settings…" item / a hotkey later show()s this same window.

    First-run / onboarding is unaffected: app_web.main() still calls
    ``open("onboarding")`` before run(), so on first run a window already
    exists in ``mgr._windows`` and this hidden-fallback is skipped.

    PRE-WARM (spec C4/S3): the reader overlay window is created HIDDEN here
    at startup — mirroring the hidden ``settings`` fallback above — so the
    FIRST ``windows.open("overlay")`` (a read / AI / WAV trigger) hits the
    warm show()+``__pippalOverlayKick`` re-show path in :func:`open` instead
    of a COLD ``webview.create_window`` that costs ~1-2 s of WebView2 init
    (#284). Created with ``hidden=True`` it NEVER pops visibly at startup —
    its ``shown``/no-activate handler only fires on the first real show. It
    also preserves BUG2: this pre-warmed window lives in ``mgr._windows``
    and the overlay branch of :func:`hide` is hide-not-destroy, so the
    lifecycle never destroys it. Best-effort: a pre-warm failure must never
    block startup (the cold-create path in :func:`open` is the fallback and
    still runs its own fast-kick on re-show)."""
    if not mgr._windows:
        win = mgr._make_window("settings", hidden=True)
        with mgr._lock:
            mgr._windows["settings"] = win

    # Pre-warm the overlay window HIDDEN so the first read shows it warm.
    with mgr._lock:
        overlay_already = "overlay" in mgr._windows
    if not overlay_already:
        try:
            overlay_win = mgr._make_window("overlay", hidden=True)
        except Exception:
            overlay_win = None
        if overlay_win is not None:
            with mgr._lock:
                mgr._windows["overlay"] = overlay_win

    mgr._started = True
    webview.start()
