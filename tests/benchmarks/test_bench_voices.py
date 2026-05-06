"""Benchmarks for ``pippal.voices`` and the Voice Manager filter
inputs. The on-disk glob is the only one that touches the filesystem
— everything else is in-memory list/dict lookup."""

from __future__ import annotations

from pathlib import Path

import pytest

from pippal.voices import (
    KNOWN_VOICES,
    find_piper_voice_for_language,
    installed_voices,
    locale_name,
    voice_filename,
)

pytestmark = pytest.mark.benchmark(group="voices")


def test_voice_filename(benchmark):
    benchmark(voice_filename, KNOWN_VOICES[0])


def test_locale_name(benchmark):
    benchmark(locale_name, "en_US")


def test_find_piper_voice_for_hungarian(benchmark):
    benchmark(find_piper_voice_for_language, "Hungarian")


def test_find_piper_voice_for_english(benchmark):
    benchmark(find_piper_voice_for_language, "English")


def test_find_piper_voice_unknown(benchmark):
    benchmark(find_piper_voice_for_language, "Klingon")


def test_installed_voices_empty_dir(benchmark, tmp_path: Path, monkeypatch):
    """Times the disk glob against an empty directory — measures the
    ``Path.glob('*.onnx')`` floor that all real lookups have to pay."""
    monkeypatch.setattr("pippal.voices.VOICES_DIR", tmp_path)
    benchmark(installed_voices)


def test_installed_voices_with_entries(benchmark, tmp_path: Path, monkeypatch):
    """Times the disk glob with a realistic voices directory layout —
    20 voice files (20 .onnx + 20 .onnx.json sidecar)."""
    for i in range(20):
        (tmp_path / f"voice_{i:02d}.onnx").write_text("")
        (tmp_path / f"voice_{i:02d}.onnx.json").write_text("{}")
    monkeypatch.setattr("pippal.voices.VOICES_DIR", tmp_path)
    benchmark(installed_voices)
