"""Overlay reader-window auto-open/-hide for the PipPal web UI.

``OverlayWindowController`` is the window-lifecycle half dropped in the
Tk-to-web migration. It subclasses ``WebOverlay`` and fires ``on_show``/
``on_hide`` callbacks on idle<->visible transitions. ``app_web.main``
wires those to ``windows.open``/``windows.hide``. Overlay state (JS
polling snapshot) is inherited unchanged from ``WebOverlay``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from pippal.web_ui.overlay_state import WebOverlay


class OverlayWindowController(WebOverlay):
    """``WebOverlay`` subclass that also opens/hides the overlay window.

    Same engine protocol (set_state/start_chunk/show_message/hide). On each
    state mutation, fires ``on_show``/``on_hide`` on visibility transitions;
    deduplicated so the window opens once per reading session.
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
        """Wire show/hide callbacks; called once from app_web.main."""
        self._on_show = on_show
        self._on_hide = on_hide

    def overlay_window_visible(self) -> bool:
        """True iff the overlay window is currently engine-visible.

        Thread-safe. Used by ``WebWindowManager.raise_window`` to decide
        whether to re-hide the pre-warmed overlay on foreground raise.
        """
        with self._win_lock:
            return self._win_visible

    # ----- visibility reconciliation ----------------------------------

    def _should_be_visible(self) -> bool:
        # #265 focus-steal guard: "thinking" precedes selection capture
        # (synthetic Ctrl+C). Opening the window during "thinking" steals
        # foreground, so the Ctrl+C lands on the overlay and the clipboard
        # comes back empty. Window becomes visible only on "reading",
        # "loading" (post-capture, distinct from "thinking" — #265 safe),
        # or "done"+message.
        #
        # Exception (#302 / BUG2): if already visible, a "thinking" state is
        # a mid-read pre-roll (next document), not a cold selection — keep
        # the window open to avoid a spurious hide mid-session.
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
        """Fire show/hide callback iff desired visibility changed.

        Deduplicated under ``_win_lock``; callbacks invoked outside overlay
        ``_lock`` to avoid deadlock against snapshot polls.
        """
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
