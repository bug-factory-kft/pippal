from __future__ import annotations

from types import SimpleNamespace

import pytest

from pippal._register import _piper_voice_persist


class _Var:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


def _settings_stub(voice_display: str) -> SimpleNamespace:
    return SimpleNamespace(vars={"voice_display": _Var(voice_display)})


def test_piper_persist_drops_placeholder_when_no_voice_is_installed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pippal.voices.VOICES_DIR", tmp_path)
    candidate = {"voice": "stale.onnx"}

    _piper_voice_persist(_settings_stub("(no voice installed)"), "piper", candidate)

    assert "voice" not in candidate


def test_piper_persist_falls_back_to_installed_voice_for_invalid_selection(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pippal.voices.VOICES_DIR", tmp_path)
    (tmp_path / "valid.onnx").write_bytes(b"model")
    (tmp_path / "valid.onnx.json").write_text("{}", encoding="utf-8")
    candidate = {"voice": "stale.onnx"}

    _piper_voice_persist(_settings_stub("(no voice installed)"), "piper", candidate)

    assert candidate["voice"] == "valid.onnx"
