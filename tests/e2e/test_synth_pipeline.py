"""End-to-end tests for the synthesis pipeline.

Headless on Windows. We drive the real ``PiperBackend.synthesize``
against the real piper.exe, then verify the WAV output is a real
audio file (right magic header, plausible duration, non-silent).

A separate test optionally decodes the WAV with faster-whisper to
confirm the audio actually contains the words PipPal was asked to
say. That's the expensive end of the spectrum — guarded by the
``e2e_asr`` mark so a fast CI run can skip it.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from pippal.engines.piper import PiperBackend


def _wav_duration_seconds(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
    return frames / rate if rate else 0.0


def _wav_rms(p: Path) -> float:
    """Crude amplitude check — non-silent audio has measurable RMS."""
    import audioop
    with wave.open(str(p), "rb") as w:
        sample_width = w.getsampwidth()
        frames = w.readframes(w.getnframes())
    return audioop.rms(frames, sample_width) if frames else 0.0


@pytest.mark.e2e
class TestSynthesisPipeline:
    """The bare-bones happy path: PipPal asks Piper to say a phrase,
    Piper writes a WAV, the WAV looks right."""

    def test_short_phrase_produces_valid_wav(
        self, piper_config: dict, tmp_path: Path,
    ) -> None:
        backend = PiperBackend(piper_config)
        out = tmp_path / "hello.wav"
        ok = backend.synthesize("Hello world from PipPal.", out)
        assert ok, "PiperBackend.synthesize returned False"
        assert out.exists(), "WAV file was not written"
        assert out.stat().st_size > 1024, (
            f"WAV file suspiciously small: {out.stat().st_size} bytes"
        )

    def test_wav_has_plausible_duration(
        self, piper_config: dict, tmp_path: Path,
    ) -> None:
        backend = PiperBackend(piper_config)
        out = tmp_path / "duration.wav"
        backend.synthesize("This sentence has eight syllables in it.", out)
        d = _wav_duration_seconds(out)
        # Rough envelope: 8 syllables * 0.15-0.4 s/syllable = 1.2-3.2 s.
        # Allow a little slop on either side for prosody / model quirks.
        assert 0.8 < d < 5.0, f"unexpected synth duration: {d:.2f} s"

    def test_wav_is_not_silent(
        self, piper_config: dict, tmp_path: Path,
    ) -> None:
        backend = PiperBackend(piper_config)
        out = tmp_path / "amp.wav"
        backend.synthesize("Hello.", out)
        rms = _wav_rms(out)
        # A piper synth at default settings sits well above 100 RMS.
        # We keep the threshold conservative — the point is "is there
        # audio at all", not "is it loud enough".
        assert rms > 50, f"WAV looks silent (RMS {rms})"

    def test_length_scale_changes_duration(
        self, piper_config: dict, tmp_path: Path,
    ) -> None:
        """``length_scale`` is the user-facing speed knob inverse —
        2.0 means *slower*, 0.6 *faster*. The synth duration should
        track it."""
        text = "The quick brown fox jumps over the lazy dog."

        slow = tmp_path / "slow.wav"
        PiperBackend({**piper_config, "length_scale": 1.5}).synthesize(text, slow)

        fast = tmp_path / "fast.wav"
        PiperBackend({**piper_config, "length_scale": 0.7}).synthesize(text, fast)

        d_slow = _wav_duration_seconds(slow)
        d_fast = _wav_duration_seconds(fast)
        assert d_slow > d_fast, (
            f"length_scale=1.5 should be slower than 0.7, got "
            f"slow={d_slow:.2f}s fast={d_fast:.2f}s"
        )


@pytest.mark.e2e
@pytest.mark.e2e_asr
class TestSynthesisASRRoundTrip:
    """Heavier check: synthesise → transcribe with whisper → verify
    the words come back. Catches regressions in the *content* of the
    audio, not just its file shape.

    Marked separately so a fast headless CI tier can skip it."""

    def test_synth_decodes_to_known_phrase(
        self, piper_config: dict, tmp_path: Path,
    ) -> None:
        whisper = pytest.importorskip("faster_whisper")

        text = "Hello world from PipPal."
        out = tmp_path / "asr.wav"
        PiperBackend(piper_config).synthesize(text, out)

        model = whisper.WhisperModel(
            "tiny.en", device="cpu", compute_type="int8",
        )
        segments, _info = model.transcribe(str(out), language="en")
        decoded = " ".join(seg.text for seg in segments).lower().strip()
        # We don't insist on word-perfect; whisper-tiny mishears, and
        # piper's prosody can swallow short words. Insist on the two
        # content nouns.
        assert "hello" in decoded, (
            f"ASR didn't recover 'hello' from synth output. "
            f"Got: {decoded!r}"
        )
        assert "pippal" in decoded or "pi pal" in decoded or "pippa" in decoded, (
            f"ASR didn't recover 'pippal' from synth output. "
            f"Got: {decoded!r}"
        )
