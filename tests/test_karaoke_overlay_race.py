"""Tests for Pro's overlay open/hide lifecycle behavior (post window-lifecycle port).

The old test file tested free's custom race-guard mechanism
(_overlay_show_pending / _overlay_hide_deferred / _make_overlay_shown_guard).
That mechanism was FREE's patch around a race; Pro's code does NOT have it.

After the verbatim port of Pro's window_lifecycle.py, the behavior is:
- hide("overlay") calls win.hide() IMMEDIATELY — no deferred mechanism.
- open("overlay") calls existing.show() + existing.restore() +
  mgr._show_no_activate(existing) + evaluate_js(__pippalOverlayKick).
- The overlay is NEVER destroyed on a failed hide (BUG2/BUG302 guard is
  preserved in window_lifecycle.hide).
- The manager has NO _overlay_show_pending or _overlay_hide_deferred attrs.

These tests replace the old race-guard tests to document and guard Pro's
actual behavior.

Run with: python -m pytest tests/test_karaoke_overlay_race.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager() -> any:
    from pippal.web_ui.windows import WebWindowManager  # type: ignore[import]

    mgr = WebWindowManager()
    mgr._base_url = "http://127.0.0.1:9999"
    mgr._bridge = MagicMock()
    mgr._started = True
    return mgr


# ---------------------------------------------------------------------------
# Pro's overlay lifecycle behavior
# ---------------------------------------------------------------------------


class TestProOverlayLifecycle:
    """Pro's window_lifecycle has no race-guard; hide is always immediate."""

    def test_manager_has_no_race_guard_attrs(self) -> None:
        """Pro's WebWindowManager must NOT have old free-patch race attrs.

        _overlay_show_pending and _overlay_hide_deferred were free's custom
        patch, not in Pro's code.  Verify they are absent so we know the
        port is clean.
        """
        mgr = _make_manager()
        assert not hasattr(mgr, "_overlay_show_pending"), (
            "WebWindowManager has _overlay_show_pending — old free patch not removed"
        )
        assert not hasattr(mgr, "_overlay_hide_deferred"), (
            "WebWindowManager has _overlay_hide_deferred — old free patch not removed"
        )
        assert not hasattr(mgr, "_make_overlay_shown_guard"), (
            "WebWindowManager has _make_overlay_shown_guard — old free patch not removed"
        )

    def test_hide_overlay_calls_win_hide_immediately(self) -> None:
        """hide('overlay') must call win.hide() immediately (no deferred path).

        Pro's hide() is a direct call — no pending-flag check, no deferral.
        """
        mgr = _make_manager()
        fake_win = MagicMock()
        mgr._windows["overlay"] = fake_win

        mgr.hide("overlay")

        fake_win.hide.assert_called_once()

    def test_hide_overlay_never_destroys_on_failed_hide(self) -> None:
        """BUG2 / #302 guard: failed overlay hide must NEVER destroy the window.

        This guard is preserved in Pro's window_lifecycle.hide.  The overlay
        is (often) the last live window; destroying it kills the GUI loop.
        """
        mgr = _make_manager()
        fake_win = MagicMock()
        fake_win.hide.side_effect = RuntimeError("simulated hide failure")
        mgr._windows["overlay"] = fake_win

        mgr.hide("overlay")  # must not raise

        fake_win.destroy.assert_not_called()
        assert "overlay" in mgr._windows, (
            "BUG2: overlay was removed from _windows after a failed hide — "
            "this would kill the pywebview GUI loop."
        )

    def test_hide_overlay_keeps_window_in_registry_on_success(self) -> None:
        """Successful overlay hide must NOT remove it from _windows."""
        mgr = _make_manager()
        fake_win = MagicMock()
        mgr._windows["overlay"] = fake_win

        mgr.hide("overlay")

        assert "overlay" in mgr._windows, (
            "overlay was removed from _windows after hide — it should stay registered."
        )

    def test_hide_non_overlay_failure_destroys_and_pops(self) -> None:
        """For non-overlay surfaces the destroy fall-through is preserved."""
        mgr = _make_manager()
        fake_win = MagicMock()
        fake_win.hide.side_effect = RuntimeError("simulated hide failure")
        mgr._windows["settings"] = fake_win

        mgr.hide("settings")

        fake_win.destroy.assert_called_once()
        assert "settings" not in mgr._windows, (
            "Non-overlay surface should be popped from registry after failed hide."
        )

    def test_open_existing_overlay_calls_show_and_restore(self) -> None:
        """open('overlay') on an existing window calls show() + restore().

        Pro's open() re-shows the existing window in-place: show() to make it
        visible, restore() to un-minimise, then _show_no_activate() via Win32
        so the overlay stays no-activate (no foreground steal).
        """
        mgr = _make_manager()
        fake_win = MagicMock()
        mgr._windows["overlay"] = fake_win

        # _show_no_activate delegates to window_native.show_no_activate which
        # is a Win32 call.  On non-Windows / test env it returns False (no-op).
        # We patch it to avoid real Win32 calls.
        with patch.object(mgr, "_show_no_activate", return_value=False) as mock_sna, \
             patch.object(mgr, "_overlay_position", return_value=None):
            mgr.open("overlay")

        fake_win.show.assert_called_once()
        fake_win.restore.assert_called_once()
        mock_sna.assert_called_once_with(fake_win)

    def test_open_existing_overlay_fires_kick_js(self) -> None:
        """open('overlay') must call __pippalOverlayKick evaluate_js (A2 fast-kick)."""
        mgr = _make_manager()
        fake_win = MagicMock()
        mgr._windows["overlay"] = fake_win

        with patch.object(mgr, "_show_no_activate", return_value=False), \
             patch.object(mgr, "_overlay_position", return_value=None):
            mgr.open("overlay")

        # evaluate_js must have been called at least once with the kick pattern
        called_scripts = [
            str(call.args[0]) if call.args else ""
            for call in fake_win.evaluate_js.call_args_list
        ]
        assert any("__pippalOverlayKick" in s for s in called_scripts), (
            "open('overlay') must call __pippalOverlayKick evaluate_js (A2 fast-kick)"
        )

    def test_open_non_overlay_fires_refresh_js(self) -> None:
        """open('settings') on an existing window must call __pippalRefresh."""
        mgr = _make_manager()
        fake_win = MagicMock()
        mgr._windows["settings"] = fake_win

        mgr.open("settings")

        called_scripts = [
            str(call.args[0]) if call.args else ""
            for call in fake_win.evaluate_js.call_args_list
        ]
        assert any("__pippalRefresh" in s for s in called_scripts), (
            "open('settings') must call __pippalRefresh to refresh the UI in-place"
        )


# Alias for backwards-compatibility with any external CI that references this
# class name. The tests now verify Pro's behavior instead of the old race guard.
TestKaraokeOverlayRace = TestProOverlayLifecycle
