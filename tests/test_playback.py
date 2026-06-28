from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pippal import playback
from pippal.engine import TTSEngine


def _seq_clock(values: list[float]):
    """Return a non-exhausting callable that yields each value in turn,
    then keeps returning the last one indefinitely.

    This replaces ``iter([...])`` + ``lambda: next(...)`` pairs so that extra
    clock calls from CI background threads / diagnostics / platform bookkeeping
    never raise StopIteration — they just see the final stable value again.
    """
    it = iter(values)
    last: dict[str, float] = {"v": values[-1]}

    def _c(*_a: object, **_k: object) -> float:
        try:
            last["v"] = next(it)
        except StopIteration:
            pass
        return last["v"]

    return _c


@pytest.fixture()
def engine() -> TTSEngine:
    return TTSEngine(MagicMock(), {"engine": "piper"}, overlay_ref=lambda: None)


def test_playback_does_not_reuse_stale_token_index_chunks(
    engine: TTSEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = tmp_path / "out_1_1.wav"
    stale.write_bytes(b"stale wav from old process")
    calls: list[tuple[str, Path]] = []

    def synthesize(text: str, out_path: Path, backend: Any = None) -> bool:
        calls.append((text, out_path))
        out_path.write_bytes(f"fresh:{text}".encode())
        return True

    monkeypatch.setattr(playback, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(playback, "split_sentences", lambda _text: ["first", "second"])
    monkeypatch.setattr(playback, "wav_duration", lambda _path: 0.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *args, **kwargs: None)
    monkeypatch.setattr(engine, "_synthesize", synthesize)

    engine.token = 1
    playback.play_one(engine, "ignored", my_token=1, backend=object())

    synthesized = {text for text, _path in calls}
    assert synthesized == {"first", "second"}
    assert stale.exists()
    assert stale.read_bytes() == b"stale wav from old process"
    assert all(path.name != "out_1_1.wav" for _text, path in calls)
    assert all(
        re.fullmatch(r"out_1_[0-9a-f]{32}_\d+\.wav", path.name)
        for _text, path in calls
    )


def test_resume_plays_remaining_tail_wav_not_full_original(
    engine: TTSEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_wav = tmp_path / "source.wav"
    sample_rate = 8_000
    frame_count = sample_rate * 3

    import wave

    with wave.open(str(source_wav), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * frame_count)

    played: list[Path | None] = []
    tail_info: dict[str, int] = {}

    def fake_play_sound(path: str | None, _flags: int = 0) -> None:
        played.append(Path(path) if path is not None else None)
        if path is not None and len(played) == 1:
            with engine.lock:
                engine._is_paused = True
        elif path is not None:
            with wave.open(str(path), "rb") as wav:
                tail_info["frames"] = wav.getnframes()
                tail_info["rate"] = wav.getframerate()
                tail_info["channels"] = wav.getnchannels()
                tail_info["sample_width"] = wav.getsampwidth()

    def fake_sleep(_seconds: float) -> None:
        with engine.lock:
            engine._is_paused = False

    # Non-exhausting clocks: after the controlled sequence is consumed,
    # any extra calls from CI background threads / teardown return the final
    # stable value (1.0 or 10.0) instead of raising StopIteration.
    # Extra trailing 1.0 values in monotonic also absorb a spurious call
    # between playback_started_at and the elapsed_s read without affecting
    # the subtraction (1.0 - 0.0 = 1.0 regardless of how many 1.0s remain).
    monkeypatch.setattr(playback.time, "monotonic", _seq_clock([0.0, 1.0, 1.0]))
    monkeypatch.setattr(playback.time, "time", _seq_clock([0.0, 0.0, 0.0, 10.0]))
    monkeypatch.setattr(playback.time, "sleep", fake_sleep)
    monkeypatch.setattr(playback.winsound, "PlaySound", fake_play_sound)

    result = playback._play_chunk(
        engine,
        playback.PlaybackSession(["one chunk"], [source_wav]),
        idx=0,
        my_token=engine.token,
    )

    assert result == 1
    assert played[0] == source_wav
    tail_wav = played[1]
    assert tail_wav is not None
    assert tail_wav != source_wav
    assert tail_wav.parent == tmp_path
    assert not tail_wav.exists()
    assert tail_info == {
        "frames": sample_rate * 2,
        "rate": sample_rate,
        "channels": 1,
        "sample_width": 2,
    }


def test_seek_during_resumed_tail_playback_purges_before_tail_cleanup(
    engine: TTSEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_wav = tmp_path / "source.wav"
    sample_rate = 8_000
    frame_count = sample_rate * 3

    import wave

    with wave.open(str(source_wav), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * frame_count)

    played: list[Path | None] = []
    unlink_attempts: list[tuple[Path, bool]] = []
    audio_active = False

    def fake_play_sound(path: str | None, _flags: int = 0) -> None:
        nonlocal audio_active
        played.append(Path(path) if path is not None else None)
        if path is None:
            audio_active = False
            return
        audio_active = True
        if len(played) == 1:
            with engine.lock:
                engine._is_paused = True
            return
        with engine.lock:
            engine._skip_to = 0

    def fake_sleep(_seconds: float) -> None:
        with engine.lock:
            engine._is_paused = False

    def fake_safe_unlink(path: Path) -> None:
        unlink_attempts.append((path, audio_active))
        if audio_active:
            return
        path.unlink(missing_ok=True)

    # Non-exhausting clocks.  For the seek test the loop exits via the
    # WaitResult.SEEKED branch (not deadline expiry), so time.time() can safely
    # return 0.0 unconditionally — the extra-call risk of shifting the 10.0
    # slot to a deadline-update position (creating an over-long deadline) is
    # completely eliminated.  monotonic gets an extra 0.0 at the start to absorb
    # one spurious call before playback_started_at is set.
    monkeypatch.setattr(playback.time, "monotonic", _seq_clock([0.0, 0.0, 1.0, 1.0]))
    monkeypatch.setattr(playback.time, "time", lambda: 0.0)
    monkeypatch.setattr(playback.time, "sleep", fake_sleep)
    monkeypatch.setattr(playback.winsound, "PlaySound", fake_play_sound)
    monkeypatch.setattr(playback, "safe_unlink", fake_safe_unlink)

    result = playback._play_chunk(
        engine,
        playback.PlaybackSession(["one chunk"], [source_wav]),
        idx=0,
        my_token=engine.token,
    )

    assert result == 0
    tail_wav = played[1]
    assert tail_wav is not None
    assert not tail_wav.exists()
    assert unlink_attempts == [(tail_wav, False)]


def test_seeked_clamps_returns_and_clears_skip_target(
    engine: TTSEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_paths = [tmp_path / f"chunk_{i}.wav" for i in range(3)]
    for path in chunk_paths:
        path.write_bytes(b"wav")

    with engine.lock:
        engine._skip_to = 99

    monkeypatch.setattr(playback, "wav_duration", lambda _path: 1.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        playback,
        "_wait_for_chunk_end",
        lambda *_args, **_kwargs: playback.WaitResult.SEEKED,
    )

    result = playback._play_chunk(
        engine,
        playback.PlaybackSession(["one", "two", "three"], chunk_paths),
        idx=0,
        my_token=engine.token,
    )

    assert result == 2
    assert engine._skip_to is None


def test_resume_replays_original_chunk_when_tail_wav_creation_fails(
    engine: TTSEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_wav = tmp_path / "source.wav"
    sample_rate = 8_000
    frame_count = sample_rate * 3

    import wave

    with wave.open(str(source_wav), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * frame_count)

    played: list[Path | None] = []

    def fake_play_sound(path: str | None, _flags: int = 0) -> None:
        played.append(Path(path) if path is not None else None)
        if path is not None and len(played) == 1:
            with engine.lock:
                engine._is_paused = True

    def fake_sleep(_seconds: float) -> None:
        with engine.lock:
            engine._is_paused = False

    def fail_tempfile(*_args: Any, **_kwargs: Any) -> object:
        raise OSError("temp creation failed")

    # Non-exhausting clocks: after the controlled sequence is consumed,
    # extra CI calls return the final stable value instead of StopIteration.
    monkeypatch.setattr(playback.time, "monotonic", _seq_clock([0.0, 1.0, 1.0, 1.0]))
    monkeypatch.setattr(playback.time, "time", _seq_clock([0.0, 0.0, 0.0, 10.0]))
    monkeypatch.setattr(playback.time, "sleep", fake_sleep)
    monkeypatch.setattr(playback.winsound, "PlaySound", fake_play_sound)
    monkeypatch.setattr(playback.tempfile, "NamedTemporaryFile", fail_tempfile)

    result = playback._play_chunk(
        engine,
        playback.PlaybackSession(["one chunk"], [source_wav]),
        idx=0,
        my_token=engine.token,
    )

    assert result == 1
    assert played == [source_wav, source_wav]
    assert not source_wav.exists()


def test_resume_failed_tail_and_failed_original_replay_keeps_chunk_retryable(
    engine: TTSEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_wav = tmp_path / "source.wav"
    sample_rate = 8_000
    frame_count = sample_rate * 3

    import wave

    with wave.open(str(source_wav), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * frame_count)

    played: list[Path | None] = []

    def fake_play_sound(path: str | None, _flags: int = 0) -> None:
        played.append(Path(path) if path is not None else None)
        if path is not None and len(played) == 1:
            with engine.lock:
                engine._is_paused = True
            return
        raise OSError("fallback replay failed")

    def fake_sleep(_seconds: float) -> None:
        with engine.lock:
            engine._is_paused = False

    # Non-exhausting clocks: extra CI calls keep returning the last stable value.
    monkeypatch.setattr(playback.time, "monotonic", _seq_clock([0.0, 1.0]))
    monkeypatch.setattr(playback.time, "time", _seq_clock([0.0, 0.0]))
    monkeypatch.setattr(playback.time, "sleep", fake_sleep)
    monkeypatch.setattr(playback.winsound, "PlaySound", fake_play_sound)
    monkeypatch.setattr(playback, "_tail_wav_from_elapsed", lambda *_args: None)

    result = playback._play_chunk(
        engine,
        playback.PlaybackSession(["one chunk"], [source_wav]),
        idx=0,
        my_token=engine.token,
    )

    assert result == 0
    assert played == [source_wav, source_wav]
    assert source_wav.exists()
