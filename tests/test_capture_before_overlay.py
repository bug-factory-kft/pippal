"""Call-order oracle for the capture-before-overlay fix (commit 44f419c).

Root cause of the "No text selected" intermittent bug:
    begin_action_overlay() was called BEFORE capture_for_action() in both
    _speak_selection_impl and _queue_selection_impl.  The overlay window —
    even "no-activate" — stole foreground focus from the user's application,
    so the synthetic Ctrl+C issued by capture_for_action landed on the wrong
    window and returned empty, triggering the "No text selected" path.

Fix: call capture_for_action FIRST (user's app keeps focus), then call
    begin_action_overlay ONLY when captured text is confirmed non-empty.

These tests use ``unittest.mock.call`` ordering to deterministically lock
down the call sequence at the seam between capture and overlay.  They do
NOT exercise Windows focus / clipboard — that requires manual QA — but they
guarantee the implementation contract at the code level.

Coverage:
  1. _speak_selection_impl with text  → capture THEN overlay (both called)
  2. _speak_selection_impl with empty → capture called, overlay NOT called
  3. _queue_selection_impl with text  → capture THEN overlay (both called)
  4. _queue_selection_impl with empty → capture called, overlay NOT called
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pippal.engine import TTSEngine
from pippal.web_ui.overlay_state import WebOverlay


@pytest.fixture()
def overlay() -> WebOverlay:
    return WebOverlay({"show_overlay": True})


@pytest.fixture()
def engine(overlay: WebOverlay) -> TTSEngine:
    eng = TTSEngine(MagicMock(), {"engine": "piper"}, overlay_ref=lambda: overlay)
    return eng


@pytest.fixture(autouse=True)
def _silence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence side-effects that are irrelevant to the ordering oracle."""
    monkeypatch.setattr("pippal.engine.winsound.PlaySound", lambda *_: None)
    monkeypatch.setattr(
        "pippal.engine.playback.synthesize_and_play", lambda *_a, **_k: None,
    )


# ---------------------------------------------------------------------------
# _speak_selection_impl
# ---------------------------------------------------------------------------

class TestSpeakSelectionOrder:
    """Call-order assertions for _speak_selection_impl."""

    def test_capture_called_before_overlay_when_text_present(
        self, engine: TTSEngine, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With non-empty capture, order MUST be: capture → overlay."""
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)

        call_order: list[str] = []

        def fake_capture(_eng: object, _action: str) -> str:
            call_order.append("capture")
            return "selected text"

        def fake_overlay(_eng: object) -> None:
            call_order.append("overlay")

        with (
            patch("pippal.engine.clipboard_capture.capture_for_action", fake_capture),
            patch("pippal.engine.begin_action_overlay", fake_overlay),
        ):
            engine._speak_selection_impl()

        assert "capture" in call_order, "capture_for_action was not called"
        assert "overlay" in call_order, "begin_action_overlay was not called"
        assert call_order.index("capture") < call_order.index("overlay"), (
            f"Expected capture before overlay, got order: {call_order}"
        )

    def test_overlay_not_called_when_capture_empty(
        self, engine: TTSEngine, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When capture returns empty, begin_action_overlay must NOT be called.

        The 'No text selected' message path must not trigger the loading
        overlay — there is nothing to load.
        """
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)
        monkeypatch.setattr(
            "pippal.engine.should_show_activation_panel", lambda: False,
        )

        overlay_mock = MagicMock()

        with (
            patch(
                "pippal.engine.clipboard_capture.capture_for_action",
                return_value="",
            ),
            patch("pippal.engine.begin_action_overlay", overlay_mock),
        ):
            engine._speak_selection_impl()

        overlay_mock.assert_not_called(), (
            "begin_action_overlay was called even though capture returned empty "
            "— this is the focus-stealing bug re-introduced."
        )


# ---------------------------------------------------------------------------
# _queue_selection_impl
# ---------------------------------------------------------------------------

class TestQueueSelectionOrder:
    """Call-order assertions for _queue_selection_impl."""

    def test_capture_called_before_overlay_when_text_present(
        self, engine: TTSEngine, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With non-empty capture (idle engine), order MUST be: capture → overlay."""
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)
        # Engine starts idle (is_speaking=False) — queue path falls through
        # to the Read branch, which calls begin_action_overlay.

        call_order: list[str] = []

        def fake_capture(_eng: object, _action: str) -> str:
            call_order.append("capture")
            return "queued text"

        def fake_overlay(_eng: object) -> None:
            call_order.append("overlay")

        with (
            patch("pippal.engine.clipboard_capture.capture_for_action", fake_capture),
            patch("pippal.engine.begin_action_overlay", fake_overlay),
        ):
            engine._queue_selection_impl()

        assert "capture" in call_order, "capture_for_action was not called"
        assert "overlay" in call_order, "begin_action_overlay was not called"
        assert call_order.index("capture") < call_order.index("overlay"), (
            f"Expected capture before overlay, got order: {call_order}"
        )

    def test_overlay_not_called_when_capture_empty(
        self, engine: TTSEngine, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When capture returns empty, begin_action_overlay must NOT be called."""
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)

        overlay_mock = MagicMock()

        with (
            patch(
                "pippal.engine.clipboard_capture.capture_for_action",
                return_value="",
            ),
            patch("pippal.engine.begin_action_overlay", overlay_mock),
        ):
            engine._queue_selection_impl()

        overlay_mock.assert_not_called(), (
            "begin_action_overlay was called in _queue_selection_impl even "
            "though capture returned empty."
        )
