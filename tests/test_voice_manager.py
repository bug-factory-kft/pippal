from __future__ import annotations

from pathlib import Path

import pytest

from pippal.ui import voice_manager
from pippal.voices import KNOWN_VOICES, voice_filename, voice_url_base


class _Response:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def read(self, _size: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""


def _portuguese_voice():
    return next(v for v in KNOWN_VOICES if v["id"] == "pt_PT-tugão-medium")


def test_encode_download_url_percent_encodes_non_ascii_path() -> None:
    voice = _portuguese_voice()
    raw_url = voice_url_base(voice) + voice_filename(voice)

    encoded = voice_manager._encode_download_url(raw_url)

    encoded.encode("ascii")
    assert "tug%C3%A3o" in encoded
    assert "tugão" not in encoded


def test_streaming_download_passes_encoded_url_to_urlopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    voice = _portuguese_voice()
    raw_url = voice_url_base(voice) + voice_filename(voice)
    seen: dict[str, str] = {}

    def fake_urlopen(url: str, timeout: float):
        seen["url"] = url
        seen["timeout"] = str(timeout)
        return _Response([b"voice-bytes"])

    monkeypatch.setattr(voice_manager.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "voice.onnx"

    voice_manager.VoiceManagerDialog._streaming_download(raw_url, dest)

    assert "tug%C3%A3o" in seen["url"]
    assert "tugão" not in seen["url"]
    assert dest.read_bytes() == b"voice-bytes"
