"""Core ordering oracle for the loading-first overlay chokepoint.

The "overlay appears with a delay" bug is an ORDERING bug: every entry
point used to set the (invisible) ``thinking`` state and then run the
blocking ``capture_for_action`` / synth, only reaching a VISIBLE state
afterwards. These tests assert the inverse property — the overlay is in a
visible ``loading`` state (with the in-body loader armed) the MOMENT
``capture_for_action`` is entered, even when capture is artificially slow.

They drive the REAL ``WebOverlay`` so ``state`` and ``is_synthesizing``
are genuine, and use a slow-capture stub that records the overlay snapshot
at the instant it is entered.

This is the core analogue of the Pro catching test
``test_overlay_show_before_textprep.py``; the helper
``pippal.overlay_actions.begin_action_overlay`` is what makes both pass.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pippal.engine import TTSEngine
from pippal.web_ui.overlay_state import WebOverlay


def _make_engine(overlay: WebOverlay) -> TTSEngine:
    return TTSEngine(MagicMock(), {"engine": "piper"}, overlay_ref=lambda: overlay)


def _install_capture_probe(
    monkeypatch: pytest.MonkeyPatch, overlay: WebOverlay, returns: str,
) -> dict[str, Any]:
    """Stub capture_for_action so it records the overlay snapshot AT ENTRY.

    The recorded ``state`` / ``is_synthesizing`` are the load-bearing oracle:
    they describe the overlay at the exact moment the (would-be slow) capture
    begins. If the loading-first chokepoint ran first, they must already be
    the visible ``loading`` state.
    """
    seen: dict[str, Any] = {}

    def slow_capture(_engine: Any, _action: str) -> str:
        snap = overlay.snapshot()
        seen["state"] = snap["overlay_state"]
        seen["is_synthesizing"] = snap["is_synthesizing"]
        return returns

    monkeypatch.setattr(
        "pippal.engine.clipboard_capture.capture_for_action", slow_capture,
    )
    return seen


@pytest.fixture()
def overlay() -> WebOverlay:
    return WebOverlay({"show_overlay": True})


@pytest.fixture(autouse=True)
def _quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pippal.engine.winsound.PlaySound", lambda *_: None)
    # Synth is irrelevant to the ordering oracle — never actually play audio.
    monkeypatch.setattr(
        "pippal.engine.playback.synthesize_and_play",
        lambda *_a, **_k: None,
    )


class TestLoadingBeforeCapture:
    def test_speak_shows_loading_before_capture(
        self, overlay: WebOverlay, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = _make_engine(overlay)
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)
        seen = _install_capture_probe(monkeypatch, overlay, "hello")

        engine._speak_selection_impl()

        assert seen["state"] == "loading", (
            "overlay did not become visible before text-prep — the first "
            "pop-up waits for capture"
        )
        assert seen["is_synthesizing"] is True

    def test_queue_idle_shows_loading_before_capture(
        self, overlay: WebOverlay, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = _make_engine(overlay)
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)
        seen = _install_capture_probe(monkeypatch, overlay, "hello")

        engine._queue_selection_impl()  # idle → behaves like Read

        assert seen["state"] == "loading"
        assert seen["is_synthesizing"] is True


class TestLoadingBeforeSynth:
    """``_read_text_impl`` / ``_replay_text_impl`` have no capture; the
    loader must be up before ``synthesize_and_play`` is reached."""

    def test_read_text_shows_loading_before_synth(
        self, overlay: WebOverlay, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = _make_engine(overlay)
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)
        seen: dict[str, Any] = {}

        def probe(*_a: Any, **_k: Any) -> None:
            snap = overlay.snapshot()
            seen["state"] = snap["overlay_state"]
            seen["is_synthesizing"] = snap["is_synthesizing"]

        monkeypatch.setattr(
            "pippal.engine.playback.synthesize_and_play", probe,
        )

        engine._read_text_impl("hello world")

        assert seen["state"] == "loading"
        assert seen["is_synthesizing"] is True

    def test_replay_text_shows_loading_before_synth(
        self, overlay: WebOverlay, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = _make_engine(overlay)
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)
        seen: dict[str, Any] = {}

        def probe(*_a: Any, **_k: Any) -> None:
            snap = overlay.snapshot()
            seen["state"] = snap["overlay_state"]
            seen["is_synthesizing"] = snap["is_synthesizing"]

        monkeypatch.setattr(
            "pippal.engine.playback.synthesize_and_play", probe,
        )

        engine._replay_text_impl("hello world")

        assert seen["state"] == "loading"
        assert seen["is_synthesizing"] is True


class TestLoaderClearedOnCompletionEdge:
    """Spec H5: the loader hides on a completion edge, never on a timer.
    An early ``begin_synth`` must not linger over a ``done`` banner."""

    def test_no_text_selected_clears_loader(
        self, overlay: WebOverlay, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engine = _make_engine(overlay)
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)
        monkeypatch.setattr("pippal.engine.should_show_activation_panel", lambda: False)
        _install_capture_probe(monkeypatch, overlay, "")  # empty → "No text"

        engine._speak_selection_impl()

        snap = overlay.snapshot()
        assert snap["overlay_state"] == "done"
        assert snap["overlay_message"] == "No text selected"
        assert snap["is_synthesizing"] is False


class TestChokepointHelper:
    def test_begin_action_overlay_is_noop_without_overlay(self) -> None:
        from pippal.overlay_actions import begin_action_overlay

        engine = TTSEngine(MagicMock(), {"engine": "piper"}, overlay_ref=lambda: None)
        # Must not raise when no overlay is attached.
        begin_action_overlay(engine)

    def test_begin_action_overlay_sets_loading_state(
        self, overlay: WebOverlay,
    ) -> None:
        from pippal.overlay_actions import begin_action_overlay

        engine = _make_engine(overlay)
        begin_action_overlay(engine)
        snap = overlay.snapshot()
        assert snap["overlay_state"] == "loading"
        assert snap["is_synthesizing"] is True
