"""Regression test: a real read must drive the overlay to 'reading' with
non-empty chunk_text even when winsound.PlaySound raises.

Before the fix (playback.py), ``_play_chunk`` called ``winsound.PlaySound``
FIRST and only then called ``ov.set_state("reading")`` + ``ov.start_chunk``.
When PlaySound raised (audio device unavailable, exclusive-mode lock, format
mismatch — all real conditions on Windows headless or restricted machines),
the exception handler returned ``idx + 1`` immediately, skipping both overlay
calls.  The overlay went ``loading(is_synthesizing) -> done -> idle``, the
karaoke window was always empty/black, and ``chunk_text`` was empty throughout.

Fix: move ``set_state("reading")`` + ``start_chunk`` to BEFORE the PlaySound
call so the overlay is always armed with karaoke content as soon as synthesis
completes, regardless of audio-output success.

Run with:
    python -m pytest tests/test_reading_drives_overlay_state.py -v
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pippal import playback as _playback
from pippal.engine import TTSEngine
from pippal.web_ui.overlay_state import WebOverlay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wav(path: Path, duration_s: float = 0.1) -> None:
    """Write a minimal valid PCM WAV at ``path``."""
    sample_rate = 22_050
    n_frames = max(1, int(sample_rate * duration_s))
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(b"\x00\x00" * n_frames)


def _make_overlay() -> WebOverlay:
    return WebOverlay({"show_overlay": True, "auto_hide_ms": 50})


def _make_engine(overlay: WebOverlay) -> TTSEngine:
    return TTSEngine(
        MagicMock(), {"engine": "piper"}, overlay_ref=lambda: overlay
    )


# ---------------------------------------------------------------------------
# Core regression
# ---------------------------------------------------------------------------


class TestReadingDrivesOverlayState:
    """Overlay must reach 'reading' with non-empty chunk_text on every real
    read, even when winsound.PlaySound raises (the failure that made the free
    app karaoke window appear empty/black)."""

    def test_overlay_reaches_reading_when_winsound_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When PlaySound raises, overlay must still reach 'reading' with
        non-empty chunk_text.

        FAILS against the unfixed code because ``_play_chunk`` skips
        ``set_state('reading')`` / ``start_chunk`` when the exception fires.
        PASSES after the fix because those calls are moved before PlaySound.
        """
        overlay = _make_overlay()
        engine = _make_engine(overlay)

        # Spy: record (overlay_state, chunk_text) snapshot after each
        # start_chunk call — this is where chunk_text becomes non-empty while
        # the overlay is in "reading" state (after the fix).
        start_chunk_snapshots: list[dict[str, Any]] = []
        _orig_start_chunk = WebOverlay.start_chunk

        def _spy_start_chunk(
            self: WebOverlay,
            text: str,
            duration: float,
            idx: int = 0,
            total: int = 1,
            offset_s: float = 0.0,
            resume_elapsed_s: float | None = None,
        ) -> None:
            _orig_start_chunk(
                self, text, duration, idx, total, offset_s, resume_elapsed_s
            )
            start_chunk_snapshots.append(self.snapshot())

        monkeypatch.setattr(WebOverlay, "start_chunk", _spy_start_chunk)

        # Spy: record all set_state transitions.
        state_log: list[str] = []
        _orig_set_state = WebOverlay.set_state

        def _spy_set_state(self: WebOverlay, state: str) -> None:
            _orig_set_state(self, state)
            state_log.append(state)

        monkeypatch.setattr(WebOverlay, "set_state", _spy_set_state)

        # Synthesis stub: write a real 100 ms WAV so wav_duration() > 0.
        def _fake_synthesize(
            text: str, out_path: Path, backend: Any = None
        ) -> bool:
            _make_wav(out_path, duration_s=0.1)
            return True

        monkeypatch.setattr(engine, "_synthesize", _fake_synthesize)
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)

        # Simulate the failure: winsound raises (no audio device etc.).
        def _winsound_raises(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("No audio device available")

        monkeypatch.setattr(_playback.winsound, "PlaySound", _winsound_raises)

        # Run the read synchronously (no thread — deterministic).
        engine._read_text_impl("hello from the karaoke overlay")

        # --- Assertions ---

        # 1. The overlay must have reached "reading" state.
        assert "reading" in state_log, (
            "overlay never reached 'reading' state — set_state('reading') is "
            "still after winsound.PlaySound instead of before it.\n"
            f"Recorded state_log: {state_log}"
        )

        # 2. start_chunk must have been called with non-empty chunk_text while
        #    the overlay was in "reading" state.
        reading_with_text = [
            snap
            for snap in start_chunk_snapshots
            if snap.get("overlay_state") == "reading"
            and snap.get("chunk_text")
        ]
        assert reading_with_text, (
            "start_chunk was never called (or called with empty text) while "
            "overlay was in 'reading' state — chunk_text stays '' so the "
            "karaoke UI renders nothing.\n"
            f"start_chunk snapshots: {start_chunk_snapshots}\n"
            f"state_log: {state_log}"
        )

        # 3. The overlay must eventually reach "done".
        assert "done" in state_log, (
            f"overlay never reached 'done'. state_log: {state_log}"
        )

        # 4. Correct order: loading < reading < done.
        assert state_log.index("loading") < state_log.index("reading"), (
            f"'loading' did not precede 'reading'. state_log: {state_log}"
        )
        assert state_log.index("reading") < state_log.index("done"), (
            f"'reading' did not precede 'done'. state_log: {state_log}"
        )

    def test_overlay_reaches_reading_when_winsound_succeeds(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Happy path: reading is also reached when winsound succeeds
        (no regression on the normal working flow)."""
        overlay = _make_overlay()
        engine = _make_engine(overlay)

        start_chunk_snapshots: list[dict[str, Any]] = []
        _orig_start_chunk = WebOverlay.start_chunk

        def _spy_start_chunk(
            self: WebOverlay,
            text: str,
            duration: float,
            idx: int = 0,
            total: int = 1,
            offset_s: float = 0.0,
            resume_elapsed_s: float | None = None,
        ) -> None:
            _orig_start_chunk(
                self, text, duration, idx, total, offset_s, resume_elapsed_s
            )
            start_chunk_snapshots.append(self.snapshot())

        monkeypatch.setattr(WebOverlay, "start_chunk", _spy_start_chunk)

        def _fake_synthesize(
            text: str, out_path: Path, backend: Any = None
        ) -> bool:
            _make_wav(out_path, duration_s=0.1)
            return True

        monkeypatch.setattr(engine, "_synthesize", _fake_synthesize)
        monkeypatch.setattr(engine, "_maybe_play_onboarding", lambda: False)

        # winsound is a no-op — audio "plays" silently.
        monkeypatch.setattr(_playback.winsound, "PlaySound", lambda *a, **k: None)

        # Make time jump past the 0.1 s chunk deadline on the first poll tick
        # so _wait_for_chunk_end returns immediately without actually sleeping.
        _call_count = [0]

        def _fast_time() -> float:
            _call_count[0] += 1
            # First call sets the deadline; all subsequent calls return a large
            # value so the first poll instantly satisfies >= deadline.
            return 0.0 if _call_count[0] <= 1 else 999.0

        monkeypatch.setattr(_playback.time, "time", _fast_time)

        engine._read_text_impl("hello from the karaoke overlay")

        reading_with_text = [
            snap
            for snap in start_chunk_snapshots
            if snap.get("overlay_state") == "reading"
            and snap.get("chunk_text")
        ]
        assert reading_with_text, (
            "Happy-path regression: start_chunk was not called with non-empty "
            "chunk_text in 'reading' state.\n"
            f"start_chunk snapshots: {start_chunk_snapshots}"
        )
