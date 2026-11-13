from __future__ import annotations

from pathlib import Path

import pytest

from pippal import voice_install
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

    encoded = voice_install._encode_download_url(raw_url)

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

    monkeypatch.setattr(voice_install.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "voice.onnx"

    voice_install._streaming_download(raw_url, dest)

    assert "tug%C3%A3o" in seen["url"]
    assert "tugão" not in seen["url"]
    assert dest.read_bytes() == b"voice-bytes"


def test_install_piper_voice_downloads_model_and_metadata(tmp_path: Path) -> None:
    voice = _portuguese_voice()
    filename = voice_filename(voice)
    calls: list[str] = []

    def fake_download(url: str, dest: Path) -> None:
        calls.append(url)
        dest.write_bytes(f"downloaded:{dest.name}".encode())

    installed = voice_install.install_piper_voice(
        voice,
        voices_dir=tmp_path,
        streaming_download=fake_download,
    )

    assert installed == filename
    assert calls == [
        voice_url_base(voice) + filename,
        voice_url_base(voice) + f"{filename}.json",
    ]
    assert (tmp_path / filename).read_bytes() == f"downloaded:{filename}.part".encode()
    assert (tmp_path / f"{filename}.json").read_bytes() == (
        f"downloaded:{filename}.json.part".encode()
    )
    assert list(tmp_path.glob("*.part")) == []


def test_install_piper_voice_removes_partial_files_on_failure(tmp_path: Path) -> None:
    voice = _portuguese_voice()
    filename = voice_filename(voice)

    def fake_download(url: str, dest: Path) -> None:
        dest.write_bytes(b"partial")
        if url.endswith(".json"):
            raise RuntimeError("network dropped")

    with pytest.raises(RuntimeError, match="network dropped"):
        voice_install.install_piper_voice(
            voice,
            voices_dir=tmp_path,
            streaming_download=fake_download,
        )

    assert (tmp_path / filename).exists() is False
    assert (tmp_path / f"{filename}.json").exists() is False
    assert list(tmp_path.glob("*.part")) == []


RETRAINED_SIDECAR = '{"phoneme_id_map": {"_": [0], "a": [14], "aɪ": [161]}}'
WORKING_SIDECAR = '{"phoneme_id_map": {"_": [0], "a": [14], "ɪ": [74]}}'


def test_install_piper_voice_refuses_config_the_bundled_piper_cannot_load(
    tmp_path: Path,
) -> None:
    """A download with multi-codepoint phoneme keys (the upstream retrain of
    November 2026) must fail at install time and leave the working voice that
    is already on disk untouched."""
    voice = _portuguese_voice()
    filename = voice_filename(voice)
    (tmp_path / filename).write_bytes(b"working model")
    (tmp_path / f"{filename}.json").write_text(WORKING_SIDECAR, encoding="utf-8")

    def fake_download(url: str, dest: Path) -> None:
        if url.endswith(".json"):
            dest.write_text(RETRAINED_SIDECAR, encoding="utf-8")
        else:
            dest.write_bytes(b"retrained model")

    with pytest.raises(voice_install.IncompatibleVoiceError, match="bundled Piper"):
        voice_install.install_piper_voice(
            voice,
            voices_dir=tmp_path,
            streaming_download=fake_download,
        )

    assert (tmp_path / filename).read_bytes() == b"working model"
    assert (tmp_path / f"{filename}.json").read_text(encoding="utf-8") == WORKING_SIDECAR
    assert list(tmp_path.glob("*.part")) == []


def test_bridge_voice_download_refuses_config_the_bundled_piper_cannot_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Same guard on the Voice Manager download path."""
    import urllib.request

    from pippal.web_ui import bridge as bridge_module

    voice = _portuguese_voice()
    filename = voice_filename(voice)
    (tmp_path / filename).write_bytes(b"working model")
    (tmp_path / f"{filename}.json").write_text(WORKING_SIDECAR, encoding="utf-8")

    def fake_urlopen(url: str, timeout: float):
        body = RETRAINED_SIDECAR.encode() if url.endswith(".json") else b"retrained model"
        response = _Response([body])
        response.headers = {}  # type: ignore[attr-defined]
        return response

    monkeypatch.setattr(bridge_module, "VOICES_DIR", tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    bridge = bridge_module.PipPalBridge.__new__(bridge_module.PipPalBridge)

    with pytest.raises(voice_install.IncompatibleVoiceError):
        bridge._stream_voice_with_progress(voice, lambda: False, lambda **_kw: None)

    assert (tmp_path / filename).read_bytes() == b"working model"
    assert (tmp_path / f"{filename}.json").read_text(encoding="utf-8") == WORKING_SIDECAR
    assert list(tmp_path.glob("*.part")) == []
