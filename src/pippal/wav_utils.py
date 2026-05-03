"""Lightweight WAV helpers backed by the stdlib `wave` module."""

from __future__ import annotations

import sys
import wave
from collections.abc import Iterable
from pathlib import Path


def wav_duration(path: str | Path) -> float:
    """Duration in seconds of the WAV at `path`. Returns 0 on failure.
    Falls back to `soundfile` if available so we tolerate non-PCM
    formats that the stdlib `wave` module rejects."""
    try:
        with wave.open(str(path), "rb") as w:
            rate = w.getframerate() or 1
            return w.getnframes() / float(rate)
    except Exception:
        pass
    try:
        import soundfile as sf  # optional dep, present with Kokoro

        return float(sf.info(str(path)).duration)
    except Exception:
        return 0.0


def concat_wavs(input_paths: Iterable[str | Path], output_path: str | Path) -> None:
    """Concatenate several WAVs into one. All inputs must share sample
    rate, channel count and sample width; PipPal only stitches files
    coming from the same engine in one pass so this holds."""
    out: wave.Wave_write | None = None
    try:
        for p in input_paths:
            with wave.open(str(p), "rb") as w:
                params = w.getparams()
                frames = w.readframes(w.getnframes())
            if out is None:
                out = wave.open(str(output_path), "wb")
                out.setparams(params)
            out.writeframes(frames)
    finally:
        if out is not None:
            out.close()


def safe_unlink(path: str | Path) -> None:
    """Best-effort delete; never raises."""
    try:
        Path(path).unlink(missing_ok=True)
    except Exception as e:
        print(f"[wav_utils] could not delete {path}: {e}", file=sys.stderr)
