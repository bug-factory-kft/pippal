from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from pippal.engines import (
    PiperBackend,
    TTSBackend,
    make_backend,
)


class TestPiperBackend:
    def test_name(self):
        assert PiperBackend({}).name == "piper"

    def test_is_available_when_exe_missing(self, tmp_path: Path):
        # Point PIPER_EXE at something that doesn't exist
        with patch("pippal.engines.piper.PIPER_EXE", tmp_path / "absent.exe"):
            assert PiperBackend({}).is_available() is False

    def test_synthesize_missing_model_returns_false(self, tmp_path: Path):
        cfg: dict[str, Any] = {"voice": "ghost.onnx"}
        b = PiperBackend(cfg)
        with patch("pippal.engines.piper.VOICES_DIR", tmp_path), \
             patch("pippal.engines.piper.PIPER_EXE", tmp_path / "fake.exe"):
            ok = b.synthesize("hello", tmp_path / "out.wav")
        assert ok is False


class TestMakeBackend:
    def test_default_is_piper(self):
        backend = make_backend({})
        assert isinstance(backend, PiperBackend)

    def test_explicit_piper(self):
        backend = make_backend({"engine": "piper"})
        assert isinstance(backend, PiperBackend)

    def test_unknown_engine_treated_as_piper(self):
        # Anything the plugin host hasn't registered (whether the user
        # typed it deliberately or it's a stale config from an
        # uninstalled extension) must fall back rather than raise.
        backend = make_backend({"engine": "totally-fake"})
        assert isinstance(backend, PiperBackend)


class TestTTSBackendIsAbstract:
    def test_cannot_instantiate_directly(self):
        # Abstract method must be implemented by subclasses
        try:
            TTSBackend({})       # type: ignore[abstract]
        except TypeError:
            return
        raise AssertionError("expected TypeError instantiating ABC")
