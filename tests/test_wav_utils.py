from __future__ import annotations

import wave
from pathlib import Path

import pytest

from pippal.wav_utils import concat_wavs, safe_unlink, wav_duration


def _write_silence(path: Path, seconds: float, rate: int = 22050) -> None:
    """Write a silent PCM_16 mono WAV of the given duration."""
    n_frames = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n_frames)


class TestWavDuration:
    def test_known_duration(self, tmp_path: Path):
        p = tmp_path / "test.wav"
        _write_silence(p, 1.5, rate=22050)
        assert wav_duration(p) == pytest.approx(1.5, abs=1e-3)

    def test_missing_file_returns_zero(self, tmp_path: Path):
        assert wav_duration(tmp_path / "nope.wav") == 0.0

    def test_non_wav_returns_zero(self, tmp_path: Path):
        bad = tmp_path / "not_a_wav.wav"
        bad.write_bytes(b"this is not a wav file")
        assert wav_duration(bad) == 0.0


class TestConcatWavs:
    def test_concatenates_durations(self, tmp_path: Path):
        a = tmp_path / "a.wav"
        b = tmp_path / "b.wav"
        out = tmp_path / "out.wav"
        _write_silence(a, 1.0)
        _write_silence(b, 0.5)
        concat_wavs([a, b], out)
        assert wav_duration(out) == pytest.approx(1.5, abs=1e-3)

    def test_single_input(self, tmp_path: Path):
        a = tmp_path / "a.wav"
        out = tmp_path / "out.wav"
        _write_silence(a, 0.7)
        concat_wavs([a], out)
        assert wav_duration(out) == pytest.approx(0.7, abs=1e-3)

    def test_preserves_sample_params(self, tmp_path: Path):
        a = tmp_path / "a.wav"
        b = tmp_path / "b.wav"
        out = tmp_path / "out.wav"
        _write_silence(a, 0.3, rate=24000)
        _write_silence(b, 0.4, rate=24000)
        concat_wavs([a, b], out)
        with wave.open(str(out), "rb") as w:
            assert w.getframerate() == 24000
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2


class TestSafeUnlink:
    def test_removes_file(self, tmp_path: Path):
        p = tmp_path / "x"
        p.write_text("hi")
        assert p.exists()
        safe_unlink(p)
        assert not p.exists()

    def test_missing_is_quiet(self, tmp_path: Path):
        # Should not raise
        safe_unlink(tmp_path / "nope")
