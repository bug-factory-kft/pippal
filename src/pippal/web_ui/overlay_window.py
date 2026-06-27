"""Overlay reader-window auto-open/-hide for the PipPal web UI.

The Tk->web migration kept the overlay *state* half (the core
:class:`pippal.web_ui.overlay_state.WebOverlay` the engine drives, and
``app.js`` ``renderOverlay`` / 120 ms ``tick`` polling that snapshot)
but dropped the *window* half: nothing ever called
``windows.open("overlay")`` when a read started, so the karaoke panel
window never appeared. The Tk app showed the overlay Toplevel as a side
effect of the engine flipping the Tk ``Overlay`` visible; the headless
``WebOverlay`` has no window, so the window must be opened explicitly.

:class:`OverlayWindowController` is the missing window half. It taps the
SAME engine->overlay state path the JS polls (it *is* the ``WebOverlay``
the engine drives, subclassed) and fires a host ``show``/``hide``
callback whenever the resolved overlay visibility crosses
idle<->visible. ``app_web.main`` wires those callbacks to
``windows.open("overlay")`` / ``windows.hide("overlay")`` exactly like
the other ``on_open_*`` surfaces, so:

* the overlay WINDOW opens on the read's ``idle -> thinking``/``reading``
  transition (the same transition that makes the JS show the panel), and
* it hides on the return to ``idle`` (engine ``stop`` /
  ``set_state("done")`` -> the ``WebOverlay`` auto-hide timer -> ``idle``,
  or an explicit ``hide``).

The transitions arrive on engine / playback / auto-hide-timer threads --
the same off-GUI-thread context the existing tray / bridge
``windows.open`` callbacks already run in -- and the callbacks are
deduplicated so a window is opened once per reading session, not once
per chunk. All overlay STATE behaviour (the snapshot the JS polls) is
inherited verbatim from the core ``WebOverlay`` -- this only adds the
window-lifecycle side effect, nothing in the karaoke math or auto-hide
timing changes.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from pippal.web_ui.overlay_state import WebOverlay


class OverlayWindowController(WebOverlay):
    """A ``WebOverlay`` that ALSO opens / hides the overlay window.

    Subclasses the core overlay-state mirror so the engine drives it
    exactly as before (same ``set_state`` / ``start_chunk`` /
    ``show_message`` / ``hide`` protocol, same snapshot). After every
    state mutation it re-derives whether the panel should be VISIBLE
    (anything other than ``idle``) and, on a transition, invokes the
    host ``on_show`` / ``on_hide`` callbacks -- which the app wires to
    open / hide the real pywebview overlay window.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._win_lock = threading.Lock()
        self._win_visible = False
        self._on_show: Callable[[], None] | None = None
        self._on_hide: Callable[[], None] | None = None

    def set_window_callbacks(
        self,
        on_show: Callable[[], None],
        on_hide: Callable[[], None],
    ) -> None:
        """Wire the host window open/hide callbacks (called once by
        ``app_web.main`` after the window manager exists)."""
        self._on_show = on_show
        self._on_hide = on_hide

    def overlay_window_visible(self) -> bool:
        """Return True iff the overlay window is currently engine-visible.

        Used by WebWindowManager.raise_window (EDIT 1) to decide whether to
        re-hide the pre-warmed overlay after a non-overlay foreground raise.
        Thread-safe: reads _win_visible under _win_lock."""
        with self._win_lock:
            return self._win_visible

    # ----- visibility reconciliation ----------------------------------

    def _should_be_visible(self) -> bool:
        # #265 -- DECOUPLE the overlay WINDOW from the selection-capture
        # phase.  The engine drives ``set_state("thinking")`` *before* it
        # captures the selection (``engine._speak_selection_impl`` /
        # ``ai_runner.run_ai_action`` both set "thinking" and only THEN
        # call ``capture_for_action`` -> a synthetic Ctrl+C against the
        # foreground app).  If the on-top overlay window opens on that
        # pre-capture "thinking" transition it STEALS foreground focus, so
        # the Ctrl+C lands on the overlay window (which has no selection)
        # and the clipboard probe comes back empty -> "No text selected"
        # even though the user really had text selected.  This is the
        # #265 regression that surfaced after toggling the panel modes
        # (which desync the dedup flag and leave the window foreground).
        #
        # Fix: the window must NOT be considered visible while the engine
        # is merely "thinking" (the pre-capture phase).  It becomes
        # visible only once a read has produced REAL post-capture content
        # or feedback -- i.e. the "reading" state (set in ``playback`` right
        # before ``start_chunk``, after capture + synthesis) or a
        # done-with-message banner (``show_message``, e.g. the read error,
        # which is itself emitted after the capture attempt).  Selection
        # capture therefore never competes with the overlay window for the
        # foreground, regardless of panel-mode toggling.
        #
        # BUG2 -- multi-document NEXT must NOT make the window vanish.  The
        # multi-doc next path is ``read_document_now`` / ``queue_read_now``
        # -> ``engine.replay_text`` -> ``set_state("thinking")`` for the
        # next document's pre-roll, immediately followed by ``reading``.
        # That transient "thinking" leg arrives while the overlay window is
        # ALREADY VISIBLE (a reading session continuing into the next
        # document).  Treating it as not-visible would fire ``on_hide`` ->
        # ``windows.hide("overlay")`` mid-read and (when ``win.hide()``
        # raised) DESTROY the overlay -- killing the GUI loop / vanishing the
        # app.  So a "thinking" state is considered visible IFF the window
        # is ALREADY visible: a CONTINUATION keeps the window, while a COLD
        # selection read (window not yet visible) still stays hidden during
        # its pre-capture "thinking" -- preserving the #265 focus-steal
        # guard.  This is the documented "distinguish already-visible
        # continuation from cold selection read" split (Constraint 4).
        # ISSUE 2 -- instant overlay. The engine emits a distinct POST-capture
        # ``loading`` state (after ``capture_for_action`` succeeds, before
        # ``synthesize_and_play``). At that point the #265 focus-steal window
        # is CLOSED (the selection is already captured), so it is safe to show
        # the overlay immediately -- the window pops with the in-body loader
        # while the (slow Kokoro) synth runs, instead of waiting for
        # ``reading`` post-synth. This must NOT make the PRE-capture
        # ``thinking`` visible (that stays guarded below) -- #265 is preserved
        # because ``thinking`` and ``loading`` are DISTINCT states.
        with self._lock:
            if self.state == "reading":
                return True
            if self.state == "loading":
                return True
            if self.state == "done" and bool(self.message):
                return True
            if self.state == "thinking" and self._win_visible:
                # Continuation: already-visible reading session pre-rolling
                # the next document -- keep the window alive.
                return True
            return False

    def _reconcile_window(self) -> None:
        """Open or hide the window iff the desired visibility changed.

        Deduplicated under ``_win_lock`` so a multi-chunk read (many
        ``start_chunk`` / ``set_state("reading")`` calls) opens the
        window once, and the host callbacks are invoked OUTSIDE the
        overlay ``_lock`` (so ``windows.open`` can't deadlock against a
        snapshot poll)."""
        desired = self._should_be_visible()
        cb: Callable[[], None] | None = None
        with self._win_lock:
            if desired == self._win_visible:
                return
            self._win_visible = desired
            cb = self._on_show if desired else self._on_hide
        if cb is not None:
            try:
                cb()
            except Exception:
                # The window side effect must never break the engine /
                # auto-hide path (mirrors the defensive try/except the
                # rest of the window manager uses).
                pass

    # ----- engine-facing protocol overrides (state + window) ----------

    def set_state(self, state: str) -> None:
        super().set_state(state)
        self._reconcile_window()

    def start_chunk(self, *args: Any, **kwargs: Any) -> None:
        super().start_chunk(*args, **kwargs)
        self._reconcile_window()

    def show_message(self, msg: str) -> None:
        super().show_message(msg)
        self._reconcile_window()

    def hide(self) -> None:
        super().hide()
        self._reconcile_window()

    def _on_hide_timeout(self, generation: int) -> None:
        # The auto-hide timer thread flips state->idle directly; reconcile
        # the window after it so the window genuinely hides on auto-hide.
        super()._on_hide_timeout(generation)
        self._reconcile_window()
