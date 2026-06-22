"""Event-driven overlay nav/loading regression tests (SPEC ISSUE 1 + 3).

These encode the user's hard requirement: leaving the loading state must be
driven by a real "audio ready" EVENT/SIGNAL, asserted on EVERY chunk
transition (not only ``idx == 0``), and a navigate-during-synth must not wedge
the playback loop.

Mechanism under test:
- ``_play_chunk`` re-asserts ``set_state("reading")`` for every chunk it begins
  playing (previously only ``idx == 0``), so a forward/back seek to a non-zero
  chunk reliably leaves the ``thinking``/loading state.
- ``WebOverlay`` exposes an authoritative ``is_synthesizing`` snapshot flag that
  flips ``True`` exactly when a real (cache-miss) synth begins and ``False`` the
  instant audio is ready (``start_chunk`` published) — the loader binds to that
  flag, so it can never outlive the synth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pippal import playback
from pippal.engine import TTSEngine
from pippal.web_ui.overlay_state import WebOverlay


def _make_engine(overlay: WebOverlay) -> TTSEngine:
    return TTSEngine(MagicMock(), {"engine": "piper"}, overlay_ref=lambda: overlay)


def test_reading_reasserted_on_nonzero_seek_chunk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chunk played at a NON-ZERO index must leave the overlay in
    ``reading`` (loader hidden), not stuck in ``thinking``.

    RED on build-73 source: ``_play_chunk`` only calls
    ``set_state("reading")`` when ``idx == 0``; here we pre-set the overlay to
    ``thinking`` (as ``engine.seek`` does) and play chunk idx==2, then assert
    the overlay flipped back to ``reading``.
    """
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    chunk_paths = [tmp_path / f"chunk_{i}.wav" for i in range(3)]
    for path in chunk_paths:
        path.write_bytes(b"wav")

    # Simulate the post-seek state engine.seek() leaves: target text shown,
    # state flipped to "thinking" (loading).
    overlay.start_chunk("third chunk", 0.0, 2, 3, offset_s=0.0)
    overlay.set_state("thinking")
    assert overlay.snapshot()["overlay_state"] == "thinking"

    monkeypatch.setattr(playback, "wav_duration", lambda _path: 1.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        playback,
        "_wait_for_chunk_end",
        lambda *_args, **_kwargs: playback.WaitResult.COMPLETED,
    )

    playback._play_chunk(
        engine,
        playback.PlaybackSession(["one", "two", "three"], chunk_paths),
        idx=2,
        my_token=engine.token,
    )

    snap = overlay.snapshot()
    assert snap["overlay_state"] == "reading", (
        f"overlay must re-assert 'reading' on a non-zero seek chunk, got {snap['overlay_state']!r}"
    )
    assert snap["chunk_text"] == "three"
    assert snap["chunk_idx"] == 2


def test_is_synthesizing_flag_flips_off_when_audio_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The authoritative ``is_synthesizing`` snapshot flag must be False once a
    chunk's audio is ready (``start_chunk`` published) so the loader hides
    immediately — no 120 ms poll heuristic / no ``thinking``-state inference.

    RED on build-73 source: ``WebOverlay`` has no ``is_synthesizing`` field.
    """
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    chunk_paths = [tmp_path / f"chunk_{i}.wav" for i in range(2)]
    for path in chunk_paths:
        path.write_bytes(b"wav")

    # A real synth is announced (cache-miss): flag must be True.
    overlay.begin_synth()
    assert overlay.snapshot()["is_synthesizing"] is True

    monkeypatch.setattr(playback, "wav_duration", lambda _path: 1.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        playback,
        "_wait_for_chunk_end",
        lambda *_args, **_kwargs: playback.WaitResult.COMPLETED,
    )

    playback._play_chunk(
        engine,
        playback.PlaybackSession(["one", "two"], chunk_paths),
        idx=1,
        my_token=engine.token,
    )

    snap = overlay.snapshot()
    # Audio is now playing -> synth flag cleared -> loader hides.
    assert snap["is_synthesizing"] is False
    assert snap["overlay_state"] == "reading"


def test_navigate_during_synth_does_not_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache-miss synth must observe a navigation (``_skip_to``) that arrives
    mid-synth and abort, so a rapid second Forward press supersedes the
    in-flight synth instead of wedging behind a blocking synth.

    RED on build-73 source: ``_ensure_chunk_ready`` calls ``_synthesize``
    synchronously and never checks ``_skip_to``; a navigation set during the
    synth is ignored until the blocking synth returns.
    """
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    chunk_paths = [tmp_path / f"chunk_{i}.wav" for i in range(4)]
    # idx 1 has no wav on disk -> cache miss -> must synthesise.
    chunk_paths[0].write_bytes(b"wav")

    synth_observed_skip: dict[str, Any] = {"skip_to_during_synth": None}

    def slow_synth(text: str, out_path: Path, backend: Any = None) -> bool:
        # User presses Forward AGAIN while this synth is "running".
        with engine.lock:
            engine._skip_to = 3
            synth_observed_skip["skip_to_during_synth"] = engine._skip_to
        # A cancellation-aware synth must NOT blindly write & return success
        # when a newer navigation has superseded this target. The cooperative
        # cancel hook lets the loop abandon this stale target.
        if engine._synth_superseded(target_idx=1):
            return False
        out_path.write_bytes(f"synth:{text}".encode())
        return True

    monkeypatch.setattr(engine, "_synthesize", slow_synth)

    ready = playback._ensure_chunk_ready(
        engine,
        playback.PlaybackSession(["a", "b", "c", "d"], chunk_paths),
        idx=1,
    )

    # The synth for the now-stale target 1 was abandoned (superseded by the
    # forward press to 3) instead of blocking the loop to completion.
    assert synth_observed_skip["skip_to_during_synth"] == 3
    assert ready is False, (
        "navigate-during-synth must supersede the stale synth target so the "
        "loop can advance to the new target without wedging"
    )
