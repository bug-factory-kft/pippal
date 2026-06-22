"""Rapid-Forward multi-page wedge regression tests (SPEC-rapid-forward-wedge).

Two INDEPENDENT defects wedge the reader on a rapid Forward x3 burst; the
real-app Tier-2 journey ``test_pj_rapid_forward_back_advances`` asserts the
compound oracle ``overlay_state == "reading" AND chunk_idx >= 3`` and needs
BOTH fixed. These are REAL-OBJECT tests (genuine ``TTSEngine`` +
``WebOverlay``, a controllable clock / monkeypatched playback primitives) —
NOT MagicMock placebos — so they reproduce the actual wedge the #105 unit
tests missed.

- Defect A: ``engine.seek(delta)`` bases its target on the engine's
  ``_chunk_idx`` (only advanced inside the blocked playback loop), so a
  same-tick Forward x3 burst coalesces to target 1 instead of accumulating
  0->1->2->3. The fix bases the target on the PENDING ``_skip_to`` when set.

- Defect B/C: in ``play_one``, when ``_ensure_chunk_ready`` bails because the
  chunk was SUPERSEDED (a navigation set ``_skip_to``), the loop does
  ``idx += 1`` and ignores ``_skip_to`` — so the settled final target reached
  via the supersede path is never driven to ``_play_chunk`` ->
  ``set_state("reading")`` (and ``is_synthesizing`` never clears). The fix
  jumps the loop index to the settled ``_skip_to`` target on supersession.
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


# ---------------------------------------------------------------------------
# Defect A — seek() must accumulate across a same-tick Forward x3 burst.
# ---------------------------------------------------------------------------


def test_seek_accumulates_across_same_tick_forward_burst(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1: three ``seek(+1)`` while the loop is blocked on chunk 0 must
    accumulate the target to chunk 3 (clamped to last chunk), NOT coalesce
    to 1.

    Simulates the real wedge: the playback loop is blocked in
    ``_wait_for_chunk_end`` on chunk 0, so it never advances
    ``engine._chunk_idx`` (pinned at 0) and ``_skip_to`` is the only pending
    target. A rapid Forward x3 burst must therefore read the PENDING
    ``_skip_to`` and accumulate 0 -> 1 -> 2 -> 3.

    RED on base: ``seek`` reads ``_chunk_idx`` (==0) every time, so each
    press sets ``_skip_to = clamp(0 + 1) = 1`` and the burst coalesces to 1;
    the overlay snapshot ``chunk_idx`` stalls at 1.
    """
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    # 8-chunk doc, mirroring the journey's multi-page text.
    with engine.lock:
        engine._chunks = [f"chunk {i}" for i in range(8)]
        engine._chunk_paths = [Path(f"c{i}.wav") for i in range(8)]
        # The loop is blocked on chunk 0 -> _chunk_idx pinned at 0.
        engine._chunk_idx = 0
        engine._skip_to = None

    # Silence the WAV purge side effect; we only care about nav state.
    monkeypatch.setattr(engine, "_overlay", lambda: overlay)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *a, **k: None)
    import pippal.engine as engine_mod

    monkeypatch.setattr(engine_mod.winsound, "PlaySound", lambda *a, **k: None)

    # Same-tick Forward x3 burst: the loop never runs between presses, so
    # _chunk_idx stays 0 the whole time.
    engine.seek(+1)
    engine.seek(+1)
    engine.seek(+1)

    with engine.lock:
        skip_to = engine._skip_to
    assert skip_to == 3, (
        f"Forward x3 from chunk 0 must accumulate _skip_to to 3, got {skip_to!r} "
        "(base bug: coalesces to 1 because seek reads _chunk_idx, not the "
        "pending _skip_to)"
    )
    # The overlay snapshot chunk_idx (set by start_chunk(target)) must also
    # reach 3 — this is the half of the journey oracle that was stalling at 1.
    assert overlay.snapshot()["chunk_idx"] == 3, (
        f"overlay snapshot chunk_idx must reach 3, got {overlay.snapshot()['chunk_idx']!r}"
    )


def test_seek_clamps_accumulated_burst_to_last_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A burst that would overshoot the last chunk clamps to the last index,
    and the pending ``_skip_to`` keeps accumulating from the clamped value
    (never runs off the end)."""
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    with engine.lock:
        engine._chunks = [f"chunk {i}" for i in range(3)]  # last idx == 2
        engine._chunk_paths = [Path(f"c{i}.wav") for i in range(3)]
        engine._chunk_idx = 0
        engine._skip_to = None

    monkeypatch.setattr(engine, "_overlay", lambda: overlay)
    import pippal.engine as engine_mod

    monkeypatch.setattr(engine_mod.winsound, "PlaySound", lambda *a, **k: None)

    # Five forwards on a 3-chunk doc -> clamp at 2.
    for _ in range(5):
        engine.seek(+1)

    with engine.lock:
        assert engine._skip_to == 2, engine._skip_to
    assert overlay.snapshot()["chunk_idx"] == 2


def test_seek_back_after_forward_accumulates_from_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mixed burst (Forward, Forward, Back) accumulates from the pending
    ``_skip_to``: 0 -> 1 -> 2 -> 1, not coalescing on ``_chunk_idx``."""
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    with engine.lock:
        engine._chunks = [f"chunk {i}" for i in range(8)]
        engine._chunk_paths = [Path(f"c{i}.wav") for i in range(8)]
        engine._chunk_idx = 0
        engine._skip_to = None

    monkeypatch.setattr(engine, "_overlay", lambda: overlay)
    import pippal.engine as engine_mod

    monkeypatch.setattr(engine_mod.winsound, "PlaySound", lambda *a, **k: None)

    engine.seek(+1)
    engine.seek(+1)
    engine.seek(-1)

    with engine.lock:
        assert engine._skip_to == 1, engine._skip_to


# ---------------------------------------------------------------------------
# Defect B/C — a settled supersede target must be driven to "reading".
# ---------------------------------------------------------------------------


def test_superseded_chunk_advances_to_skip_to_not_idx_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2 (the loop-level half): when ``_ensure_chunk_ready`` bails because
    a navigation superseded the current idx mid-synth, the loop must jump to
    the settled ``_skip_to`` target — NOT blindly to ``idx + 1``.

    DISCRIMINATING scenario (settled target is BEHIND the superseded chunk):
    the loop is synthesising chunk 2 (cache MISS); mid-synth a rapid Back
    burst lands and sets ``_skip_to = 0``. ``_synth_superseded(2)`` fires and
    the synth bails. The fix must jump the loop to chunk 0 (the settled
    target). The base ``idx += 1`` would instead walk to chunk 3 — AWAY from
    the target — and never drive chunk 0 to ``reading``. Because the target
    is behind, ``idx += 1`` can provably never reach it.

    RED on base: ``idx += 1`` walks forward to 3, never playing chunk 0;
    overlay never reaches ``reading`` at the settled target 0.
    """
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    chunks = [f"chunk {i}" for i in range(4)]
    chunk_paths = [tmp_path / f"c{i}.wav" for i in range(4)]
    # chunk 0 and 1 already on disk (HIT); chunk 2 is a cache MISS that will
    # be superseded; chunk 3 is the chunk the base idx+=1 bug would walk to.
    chunk_paths[0].write_bytes(b"wav")
    chunk_paths[1].write_bytes(b"wav")

    # Start the loop already positioned at chunk 2 (cache MISS).
    with engine.lock:
        engine._chunks = chunks
        engine._chunk_paths = chunk_paths
        engine._chunk_idx = 0
        engine._skip_to = None

    played: list[int] = []
    real_play_chunk = playback._play_chunk

    def _spy_play_chunk(eng: TTSEngine, session: Any, idx: int, my_token: int):
        played.append(idx)
        result = real_play_chunk(eng, session, idx, my_token)
        # Terminate the loop cleanly once the settled BACK target (0) has been
        # re-played AFTER the supersede, so the final overlay state is the
        # settled target's "reading" (not whatever chunk follows it).
        if idx == 0 and played.count(0) >= 2:
            with eng.lock:
                eng.token += 1
        return result

    monkeypatch.setattr(playback, "_play_chunk", _spy_play_chunk)
    monkeypatch.setattr(playback, "wav_duration", lambda _p: 1.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *a, **k: None)
    monkeypatch.setattr(
        playback,
        "_wait_for_chunk_end",
        lambda *a, **k: playback.WaitResult.COMPLETED,
    )
    monkeypatch.setattr(playback, "split_sentences", lambda _t: chunks)
    monkeypatch.setattr(playback, "_chunk_paths", lambda _t, _n: chunk_paths)
    # Disable background prefetch so the supersede happens deterministically
    # inside the loop's own _ensure_chunk_ready synth (not a racing prefetch
    # thread). The loop's foreground synth is the canonical supersede site.
    monkeypatch.setattr(playback, "_kick_prefetch", lambda *a, **k: None)

    burst_fired = {"done": False}

    def _fake_synth(text: str, out_path: Path, backend: Any = None) -> bool:
        # chunks 0 & 1 are HITs (no synth in the loop). The cache-MISS synth
        # of chunk 2 observes a rapid BACK burst settling on chunk 0: it sets
        # _skip_to=0 and writes its wav. The post-synth _synth_superseded
        # re-check then bails (skip=0 != 2) with _skip_to still pending, so the
        # loop must honour it and jump BACK to chunk 0 — not forward via idx+=1.
        if text == "chunk 2" and not burst_fired["done"]:
            burst_fired["done"] = True
            with engine.lock:
                engine._skip_to = 0
        out_path.write_bytes(f"synth:{text}".encode())
        return True

    monkeypatch.setattr(engine, "_synthesize", _fake_synth)

    my_token = engine.token
    playback.play_one(engine, "ignored text", my_token)

    # The loop must have driven the SETTLED BACK target chunk 0 to _play_chunk
    # AFTER the supersede (a second time, since chunk 0 also plays at the
    # start). The base idx+=1 bug walks forward to 3 and never re-plays 0.
    assert played.count(0) >= 2, (
        f"loop must jump BACK to the settled _skip_to target 0 after the "
        f"supersede; played indices were {played} (base idx+=1 walks forward "
        "to 3 and never re-reaches the settled target behind it)"
    )
    # And it must NOT have wandered forward to chunk 3 via idx+=1.
    assert 3 not in played, (
        f"loop must honour the BACK target, not walk forward to 3; played={played}"
    )

    snap = overlay.snapshot()
    assert snap["overlay_state"] == "reading", (
        f"settled target must reach 'reading', got {snap['overlay_state']!r}"
    )
    assert snap["chunk_idx"] == 0, snap["chunk_idx"]
    assert snap["is_synthesizing"] is False, snap["is_synthesizing"]


def test_settled_forward_burst_reaches_reading_and_clears_synth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2 (end-to-end on the loop): after a Forward burst SETTLES on target
    T (reached via the supersede path), the overlay must end at ``reading``
    with ``is_synthesizing`` cleared — overlay leaves ``thinking``.

    RED on base: the supersede bail does ``idx += 1`` and the settled target
    is never synthesised to completion via the supersede path, so the overlay
    is left in ``thinking`` with ``is_synthesizing`` True (loader stuck on).
    """
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    # 3-chunk doc; the burst settles on the LAST chunk (idx 2) so the loop
    # terminates exactly on the settled target and we can assert the final
    # resting overlay state is 'reading' at that target.
    chunks = [f"chunk {i}" for i in range(3)]
    chunk_paths = [tmp_path / f"c{i}.wav" for i in range(3)]
    chunk_paths[0].write_bytes(b"wav")  # chunk 0 cache HIT; 1..2 are MISSes

    with engine.lock:
        engine._chunks = chunks
        engine._chunk_paths = chunk_paths
        engine._chunk_idx = 0
        engine._skip_to = None

    monkeypatch.setattr(playback, "wav_duration", lambda _p: 1.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *a, **k: None)
    monkeypatch.setattr(
        playback,
        "_wait_for_chunk_end",
        lambda *a, **k: playback.WaitResult.COMPLETED,
    )
    monkeypatch.setattr(playback, "split_sentences", lambda _t: chunks)
    monkeypatch.setattr(playback, "_chunk_paths", lambda _t, _n: chunk_paths)
    monkeypatch.setattr(playback, "_kick_prefetch", lambda *a, **k: None)

    burst_fired = {"done": False}

    def _fake_synth(text: str, out_path: Path, backend: Any = None) -> bool:
        # chunk 0 is synthesised by _prepare_first_chunk — let it succeed.
        # The first cache-MISS synth of an INTERMEDIATE chunk (chunk 1)
        # observes a Forward burst settling on the last chunk (idx 2); the
        # loader is on (begin_synth) for that intermediate chunk and must be
        # cleared once the settled target reaches audio. Mirror engine.seek's
        # overlay effect (target text shown + 'thinking').
        if text == "chunk 1" and not burst_fired["done"]:
            burst_fired["done"] = True
            overlay.start_chunk("chunk 2", 0.0, 2, 3, offset_s=0.0)
            overlay.set_state("thinking")
            with engine.lock:
                engine._skip_to = 2
        out_path.write_bytes(f"synth:{text}".encode())
        return True

    monkeypatch.setattr(engine, "_synthesize", _fake_synth)

    playback.play_one(engine, "ignored text", engine.token)

    snap = overlay.snapshot()
    assert snap["overlay_state"] == "reading", (
        f"settled Forward burst must leave overlay in 'reading', got "
        f"{snap['overlay_state']!r} (base: stuck 'thinking')"
    )
    assert snap["chunk_idx"] == 2, snap["chunk_idx"]
    assert snap["is_synthesizing"] is False, (
        "is_synthesizing must clear once the settled target's audio is ready"
    )


def test_genuine_synth_failure_still_skips_forward(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: a GENUINE synth failure (not a supersession — no
    pending ``_skip_to``) must still skip forward via ``idx += 1`` so a single
    bad chunk does not wedge the loop. The supersede fix must NOT swallow real
    failures.
    """
    overlay = WebOverlay({"show_overlay": True})
    engine = _make_engine(overlay)

    chunks = [f"chunk {i}" for i in range(3)]
    chunk_paths = [tmp_path / f"c{i}.wav" for i in range(3)]
    chunk_paths[0].write_bytes(b"wav")
    chunk_paths[2].write_bytes(b"wav")  # chunk 2 is a HIT

    with engine.lock:
        engine._chunks = chunks
        engine._chunk_paths = chunk_paths
        engine._chunk_idx = 0
        engine._skip_to = None

    played: list[int] = []
    real_play_chunk = playback._play_chunk

    def _spy_play_chunk(eng: TTSEngine, session: Any, idx: int, my_token: int):
        played.append(idx)
        return real_play_chunk(eng, session, idx, my_token)

    monkeypatch.setattr(playback, "_play_chunk", _spy_play_chunk)
    monkeypatch.setattr(playback, "wav_duration", lambda _p: 1.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *a, **k: None)
    monkeypatch.setattr(
        playback,
        "_wait_for_chunk_end",
        lambda *a, **k: playback.WaitResult.COMPLETED,
    )
    monkeypatch.setattr(playback, "split_sentences", lambda _t: chunks)
    monkeypatch.setattr(playback, "_chunk_paths", lambda _t, _n: chunk_paths)

    def _failing_synth_for_1(text: str, out_path: Path, backend: Any = None) -> bool:
        # chunk 1 is a cache MISS and its synth FAILS (no _skip_to set).
        if text == "chunk 1":
            return False
        out_path.write_bytes(f"synth:{text}".encode())
        return True

    monkeypatch.setattr(engine, "_synthesize", _failing_synth_for_1)

    playback.play_one(engine, "ignored", engine.token)

    # chunk 1 failed -> loop must skip to chunk 2 (idx+=1), which plays.
    assert 2 in played, f"genuine failure must skip forward; played={played}"
    assert overlay.snapshot()["chunk_idx"] == 2
