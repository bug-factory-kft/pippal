"""Regression test for the karaoke overlay show->hide race (#race-fix).

Symptom: on short reads, the engine reaches "idle" and calls hide("overlay")
BEFORE pywebview's ``shown`` event fires for that overlay window, so the show
is immediately cancelled and the overlay window flashes then vanishes.

Root cause (windows.py): ``open("overlay")`` calls ``win.show()`` and returns;
before pywebview fires the ``shown`` event the engine has already gone idle and
``hide("overlay")`` calls ``win.hide()``. The window either never appears or
flashes briefly.

Fix: ``WebWindowManager.open("overlay")`` sets ``_overlay_show_pending=True``
before calling ``win.show()``; ``hide("overlay")`` defers to
``_overlay_hide_deferred`` when pending; the overlay's ``shown`` event handler
(wired by ``_make_window`` via ``_make_overlay_shown_guard``) clears the flag
and applies the deferred hide.

Run with: python -m pytest tests/test_karaoke_overlay_race.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Callable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeEvents:
    """Minimal pywebview event object: supports += and manual .fire()."""

    def __init__(self) -> None:
        self._handlers: list[Callable[[], None]] = []

    def __iadd__(self, fn: Callable[[], None]) -> "FakeEvents":
        self._handlers.append(fn)
        return self

    def fire(self) -> None:
        for h in list(self._handlers):
            h()


class FakeWindow:
    """Minimal pywebview Window fake with trackable show/hide calls."""

    def __init__(self) -> None:
        shown_ev = FakeEvents()
        closed_ev = FakeEvents()
        self.events = SimpleNamespace(shown=shown_ev, closed=closed_ev)
        self.shown_event: FakeEvents = shown_ev
        self.show_calls = 0
        self.hide_calls = 0

    def show(self) -> None:
        self.show_calls += 1

    def hide(self) -> None:
        self.hide_calls += 1

    def move(self, x: int, y: int) -> None:
        pass


def _make_manager_with_overlay() -> tuple:
    """Return (mgr, fake_win) with the race guard attached."""
    from pippal.web_ui.windows import WebWindowManager  # type: ignore[import]

    mgr = WebWindowManager()
    fake_win = FakeWindow()
    # Wire the same shown-event guard that _make_window() attaches.
    handler = mgr._make_overlay_shown_guard(fake_win)
    fake_win.shown_event += handler
    mgr._windows["overlay"] = fake_win
    mgr._started = True
    return mgr, fake_win


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestKaraokeOverlayRace:
    """Race: hide() arrives before pywebview shown event fires."""

    def test_hide_before_shown_is_deferred_not_immediate(self) -> None:
        """hide("overlay") while show is pending must NOT call win.hide() yet.

        This is the core race: ``open("overlay")`` sets
        ``_overlay_show_pending=True`` and calls ``win.show()``. On a short
        read the engine goes idle immediately (before the pywebview ``shown``
        event fires) and calls ``hide("overlay")``. The fix must defer the
        hide so the window is visible at least until ``shown`` fires.
        """
        mgr, fake_win = _make_manager_with_overlay()

        # Simulate open("overlay") having set the pending flag.
        mgr._overlay_show_pending = True
        mgr._overlay_hide_deferred = False

        # Engine goes idle before shown fires -- this is the race.
        mgr.hide("overlay")

        assert fake_win.hide_calls == 0, (
            "hide() called win.hide() immediately while show was pending -- "
            "this is the race that makes the overlay flash and disappear."
        )
        assert mgr._overlay_hide_deferred is True, (
            "hide() should set _overlay_hide_deferred=True when show is pending."
        )

    def test_shown_event_applies_deferred_hide(self) -> None:
        """After shown fires with a deferred hide, win.hide() must be called."""
        mgr, fake_win = _make_manager_with_overlay()

        # Simulate open("overlay"): pending flag set.
        mgr._overlay_show_pending = True
        mgr._overlay_hide_deferred = False

        # Race: hide arrives before shown.
        mgr.hide("overlay")
        assert fake_win.hide_calls == 0, "pre-condition: hide not yet called"

        # Now the shown event fires (window finally visible).
        fake_win.shown_event.fire()

        assert fake_win.hide_calls == 1, (
            "After shown fires, the deferred hide must be applied exactly once."
        )
        assert mgr._overlay_show_pending is False, (
            "shown handler must clear _overlay_show_pending."
        )
        assert mgr._overlay_hide_deferred is False, (
            "shown handler must clear _overlay_hide_deferred after applying it."
        )

    def test_normal_hide_after_shown_is_immediate(self) -> None:
        """Normal long-read path: hide() after shown fires must work immediately."""
        mgr, fake_win = _make_manager_with_overlay()

        # Simulate open() then shown fires (long read -- no race).
        mgr._overlay_show_pending = True
        mgr._overlay_hide_deferred = False
        fake_win.shown_event.fire()  # shown fires before hide() call

        # Now the read finishes and hide is called.
        mgr.hide("overlay")

        assert fake_win.hide_calls == 1, (
            "Normal path: hide() after shown fires must call win.hide() immediately."
        )

    def test_shown_without_pending_is_noop(self) -> None:
        """Pre-warm path: shown fires with no pending show -> no accidental hide."""
        mgr, fake_win = _make_manager_with_overlay()

        # No pending show (e.g. the pre-warm's cold-create shown event).
        mgr._overlay_show_pending = False
        mgr._overlay_hide_deferred = False

        fake_win.shown_event.fire()

        assert fake_win.hide_calls == 0, (
            "shown with no pending state must not hide the window."
        )

    def test_pending_flag_cleared_after_shown(self) -> None:
        """_overlay_show_pending is False after shown fires (no deferred hide)."""
        mgr, fake_win = _make_manager_with_overlay()

        mgr._overlay_show_pending = True
        mgr._overlay_hide_deferred = False
        fake_win.shown_event.fire()

        assert mgr._overlay_show_pending is False, (
            "_overlay_show_pending must be cleared after shown fires."
        )

    def test_double_shown_does_not_double_hide(self) -> None:
        """If shown fires twice (edge case), the deferred hide runs exactly once."""
        mgr, fake_win = _make_manager_with_overlay()

        mgr._overlay_show_pending = True
        mgr._overlay_hide_deferred = False

        # Race: hide before shown.
        mgr.hide("overlay")
        assert fake_win.hide_calls == 0

        # First shown fires -- deferred hide is applied.
        fake_win.shown_event.fire()
        assert fake_win.hide_calls == 1

        # Second spurious shown -- must not hide again.
        fake_win.shown_event.fire()
        assert fake_win.hide_calls == 1, (
            "Second shown must not call win.hide() again."
        )
