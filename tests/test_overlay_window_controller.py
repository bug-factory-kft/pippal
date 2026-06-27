"""Oracle tests for OverlayWindowController + WebWindowManager.hide (#265 / #302).

Tests are written RED-first: they will fail until the implementation lands.

(a) State-gating / #265 focus-steal guard
    - "thinking" with window NOT yet visible -> on_show MUST NOT fire
    - "loading" -> on_show fires (post-capture, safe to open)
    - "reading" -> on_show fires
    - "thinking" while ALREADY visible (multi-doc continuation) -> window stays
      visible (no on_hide), no duplicate on_show

(b) Open / hide lifecycle
    - loading -> reading flow results in exactly one on_show per session
    - hide() / set_state("idle") results in on_hide

(c) #302 never-destroy-on-failed-hide (overlay exception in WebWindowManager.hide)
    - win.hide() raises for "overlay" -> win.destroy() NOT called, window stays
      in registry
    - win.hide() raises for a non-overlay surface -> win.destroy() IS called and
      surface is removed from registry

(d) Loading-messages render in app.js
    - LOADING_MESSAGES array present in webui/js/app.js
    - currentLoadingMessage function present
    - Static literal "preparing..." no longer used as the default fallback
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# (a) + (b) -- OverlayWindowController state-gating
# ---------------------------------------------------------------------------


class TestOverlayWindowControllerStateGating:
    """#265 focus-steal guard: pre-capture 'thinking' must NOT open the window."""

    def _make_controller(self):
        from pippal.web_ui.overlay_window import OverlayWindowController  # type: ignore[import]

        ctrl = OverlayWindowController({"show_overlay": True})
        return ctrl

    def test_thinking_cold_does_not_fire_on_show(self) -> None:
        """Cold 'thinking' (window not yet visible) must NOT fire on_show.

        This is the core #265 guard: the engine emits 'thinking' BEFORE
        clipboard capture. If the window opened here it would steal foreground
        focus and the Ctrl+C lands on the wrong window.
        """
        ctrl = self._make_controller()
        show_calls: list[None] = []
        hide_calls: list[None] = []
        ctrl.set_window_callbacks(
            on_show=lambda: show_calls.append(None),
            on_hide=lambda: hide_calls.append(None),
        )

        ctrl.set_state("thinking")

        assert show_calls == [], (
            "#265 violated: on_show fired during pre-capture 'thinking' -- "
            "this would steal foreground focus and break clipboard capture."
        )
        assert hide_calls == []

    def test_loading_fires_on_show(self) -> None:
        """'loading' is the POST-capture state -- window MUST open immediately."""
        ctrl = self._make_controller()
        show_calls: list[None] = []
        ctrl.set_window_callbacks(
            on_show=lambda: show_calls.append(None),
            on_hide=lambda: [],
        )

        ctrl.set_state("loading")

        assert show_calls == [None], (
            "'loading' is the post-capture phase (ISSUE 2) -- on_show must fire "
            "so the overlay pops with the in-body loader while synth runs."
        )

    def test_reading_fires_on_show(self) -> None:
        """'reading' (post-synth audio playing) must open the window."""
        ctrl = self._make_controller()
        show_calls: list[None] = []
        ctrl.set_window_callbacks(
            on_show=lambda: show_calls.append(None),
            on_hide=lambda: [],
        )

        ctrl.set_state("reading")

        assert show_calls == [None]

    def test_thinking_continuation_keeps_window_visible(self) -> None:
        """Multi-doc NEXT: 'thinking' while already visible must NOT fire on_hide.

        BUG2 guard: the multi-doc next path briefly hits 'thinking' between
        documents while the window is already up. Treating it as not-visible
        would fire on_hide -> windows.hide("overlay") which, if hide() raises,
        would historically destroy the window and kill the GUI loop.
        """
        ctrl = self._make_controller()
        hide_calls: list[None] = []
        show_count: list[None] = []
        ctrl.set_window_callbacks(
            on_show=lambda: show_count.append(None),
            on_hide=lambda: hide_calls.append(None),
        )

        # Get to a visible state first.
        ctrl.set_state("reading")
        assert show_count == [None]

        # Now the multi-doc 'thinking' pre-roll arrives while already visible.
        ctrl.set_state("thinking")

        assert hide_calls == [], (
            "BUG2: on_hide fired during multi-doc continuation 'thinking' -- "
            "this would destroy the overlay and kill the GUI loop."
        )

    def test_done_with_message_fires_on_show(self) -> None:
        """A 'done' + message banner (e.g. 'No text selected') must open window."""
        ctrl = self._make_controller()
        show_calls: list[None] = []
        ctrl.set_window_callbacks(
            on_show=lambda: show_calls.append(None),
            on_hide=lambda: [],
        )

        ctrl.show_message("No text selected")

        assert show_calls == [None]

    def test_done_without_message_does_not_fire_on_show(self) -> None:
        """A bare 'done' with no message is not a visible state."""
        ctrl = self._make_controller()
        show_calls: list[None] = []
        ctrl.set_window_callbacks(
            on_show=lambda: show_calls.append(None),
            on_hide=lambda: [],
        )

        ctrl.set_state("done")

        assert show_calls == []


class TestOverlayWindowControllerLifecycle:
    """Open/hide lifecycle: reading -> on_show; idle/hide -> on_hide."""

    def _make_controller(self):
        from pippal.web_ui.overlay_window import OverlayWindowController  # type: ignore[import]

        ctrl = OverlayWindowController({"show_overlay": True})
        return ctrl

    def test_read_flow_then_hide_fires_on_hide(self) -> None:
        """loading -> reading -> hide() should give exactly one on_show and one on_hide."""
        ctrl = self._make_controller()
        show_calls: list[None] = []
        hide_calls: list[None] = []
        ctrl.set_window_callbacks(
            on_show=lambda: show_calls.append(None),
            on_hide=lambda: hide_calls.append(None),
        )

        ctrl.set_state("loading")   # window opens
        ctrl.set_state("reading")   # deduped -- already visible
        ctrl.hide()                 # engine stop -> idle

        assert show_calls == [None]
        assert hide_calls == [None]

    def test_callbacks_deduped_across_chunks(self) -> None:
        """Multiple start_chunk calls in one session must NOT open the window again."""
        ctrl = self._make_controller()
        show_calls: list[None] = []
        ctrl.set_window_callbacks(
            on_show=lambda: show_calls.append(None),
            on_hide=lambda: [],
        )

        ctrl.set_state("reading")
        ctrl.start_chunk("hello world", 1.0, idx=0, total=2)
        ctrl.start_chunk("second chunk", 1.0, idx=1, total=2)

        assert len(show_calls) == 1, (
            "on_show must fire exactly once per reading session, not per chunk."
        )

    def test_overlay_window_visible_reflects_state(self) -> None:
        """overlay_window_visible() returns the current engine-derived visibility."""
        from pippal.web_ui.overlay_window import OverlayWindowController  # type: ignore[import]

        ctrl = OverlayWindowController({"show_overlay": True})
        ctrl.set_window_callbacks(on_show=lambda: None, on_hide=lambda: None)

        assert ctrl.overlay_window_visible() is False

        ctrl.set_state("reading")
        assert ctrl.overlay_window_visible() is True

        ctrl.hide()
        assert ctrl.overlay_window_visible() is False


# ---------------------------------------------------------------------------
# (c) -- #302 never-destroy-on-failed-hide
# ---------------------------------------------------------------------------


class TestWebWindowManagerHideGuard:
    """#302 / BUG2: overlay.hide() failure must NEVER destroy the overlay."""

    def _make_manager_with_fake_window(self, surface: str, raises: bool):
        """Return (manager, fake_win) with the fake in _windows[surface]."""
        from pippal.web_ui.windows import WebWindowManager  # type: ignore[import]

        mgr = WebWindowManager()
        fake_win = MagicMock()
        if raises:
            fake_win.hide.side_effect = RuntimeError("hide failed (simulated)")
        mgr._windows[surface] = fake_win
        return mgr, fake_win

    def test_overlay_hide_failure_never_destroys_window(self) -> None:
        """When win.hide() raises for 'overlay', destroy() must NOT be called and
        the window must stay in the registry (keeps GUI loop alive -- BUG2 guard)."""
        mgr, fake_win = self._make_manager_with_fake_window("overlay", raises=True)

        mgr.hide("overlay")

        fake_win.destroy.assert_not_called()
        assert "overlay" in mgr._windows, (
            "BUG2: overlay was removed from _windows after a failed hide -- "
            "this would kill the pywebview GUI loop."
        )

    def test_overlay_hide_success_does_not_remove_window(self) -> None:
        """A successful hide() on 'overlay' must NOT remove it from the registry.

        The overlay is always hide-not-destroy; it must survive for re-shows.
        """
        mgr, fake_win = self._make_manager_with_fake_window("overlay", raises=False)

        mgr.hide("overlay")

        fake_win.destroy.assert_not_called()
        assert "overlay" in mgr._windows

    def test_non_overlay_hide_failure_destroys_and_pops(self) -> None:
        """For non-overlay surfaces the original destroy fall-through is preserved.

        If win.hide() raises for e.g. 'settings', the window is destroyed and
        removed from the registry (the original semantics).
        """
        mgr, fake_win = self._make_manager_with_fake_window("settings", raises=True)

        mgr.hide("settings")

        fake_win.destroy.assert_called_once()
        assert "settings" not in mgr._windows, (
            "Non-overlay surface should be popped from registry after failed hide."
        )

    def test_set_overlay_controller_stores_controller(self) -> None:
        """set_overlay_controller must store the controller for later use."""
        from pippal.web_ui.windows import WebWindowManager  # type: ignore[import]

        mgr = WebWindowManager()
        fake_ctrl = MagicMock()
        mgr.set_overlay_controller(fake_ctrl)
        assert mgr._overlay_controller is fake_ctrl


# ---------------------------------------------------------------------------
# (d) -- Loading-messages render in app.js
# ---------------------------------------------------------------------------


class TestAppJsLoadingMessages:
    """app.js must contain the rotating loading messages from Pro's overlay.js."""

    @pytest.fixture
    def app_js(self) -> str:
        repo_root = pathlib.Path(__file__).parent.parent
        js_path = repo_root / "webui" / "js" / "app.js"
        return js_path.read_text(encoding="utf-8")

    def test_loading_messages_array_present(self, app_js: str) -> None:
        assert "LOADING_MESSAGES" in app_js, (
            "LOADING_MESSAGES array not found in webui/js/app.js -- "
            "port it from Pro's overlay.js."
        )

    def test_current_loading_message_function_present(self, app_js: str) -> None:
        assert "currentLoadingMessage" in app_js, (
            "currentLoadingMessage() function not found in webui/js/app.js."
        )

    def test_preparing_literal_removed_as_default(self, app_js: str) -> None:
        # The static "preparing..." fallback must be replaced by currentLoadingMessage().
        assert ('"preparing…"' not in app_js) and ("'preparing…'" not in app_js), (
            "Static 'preparing...' literal still used as loader default in app.js -- "
            "replace with currentLoadingMessage()."
        )

    def test_loading_rotate_ms_present(self, app_js: str) -> None:
        assert "LOADING_ROTATE_MS" in app_js, (
            "LOADING_ROTATE_MS not found in app.js."
        )
