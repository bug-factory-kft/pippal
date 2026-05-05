from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pippal import plugins
from pippal.engines import (
    PiperBackend,
    TTSBackend,
    make_backend,
)

# Kokoro tests live in the pippal-pro repo, where the engine actually
# ships. Public CI runs without pippal_pro on the path; importorskip
# makes the Kokoro-touching tests below collect cleanly when Pro isn't
# installed.
KokoroBackend = pytest.importorskip("pippal_pro.engines.kokoro").KokoroBackend


@pytest.fixture()
def _kokoro_registered():
    """For tests that exercise the make_backend('kokoro') path, register
    Kokoro in the plugin host (the public package doesn't ship it).
    Test cleanup tears the registration back down so other tests aren't
    polluted."""
    plugins.register_engine("kokoro", KokoroBackend)
    yield
    # Re-register only the built-in engines so the global registry is
    # back to its post-_register state.
    plugins._engines.pop("kokoro", None)


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


class TestKokoroBackend:
    def test_name(self):
        assert KokoroBackend({}).name == "kokoro"

    def test_unavailable_when_kokoro_not_installed(self):
        b = KokoroBackend({})
        with patch("pippal_pro.engines.kokoro.kokoro_installed", return_value=False):
            assert b.is_available() is False


class TestMakeBackend:
    def test_default_is_piper(self):
        backend = make_backend({})
        assert isinstance(backend, PiperBackend)

    def test_explicit_piper(self):
        backend = make_backend({"engine": "piper"})
        assert isinstance(backend, PiperBackend)

    def test_kokoro_falls_back_when_unavailable(self, _kokoro_registered):
        with patch.object(KokoroBackend, "is_available", return_value=False):
            backend = make_backend({"engine": "kokoro"})
        assert isinstance(backend, PiperBackend)

    def test_kokoro_used_when_available(self, _kokoro_registered):
        with patch.object(KokoroBackend, "is_available", return_value=True):
            backend = make_backend({"engine": "kokoro"})
        assert isinstance(backend, KokoroBackend)

    def test_unknown_engine_treated_as_piper(self):
        backend = make_backend({"engine": "totally-fake"})
        assert isinstance(backend, PiperBackend)

    def test_unregistered_engine_falls_back_quietly(self):
        # Even if the user has 'kokoro' in their config, the Free build
        # without pippal_pro won't have Kokoro registered. The factory
        # should still return a usable Piper backend rather than raising.
        backend = make_backend({"engine": "kokoro"})
        assert isinstance(backend, PiperBackend)


class TestTTSBackendIsAbstract:
    def test_cannot_instantiate_directly(self):
        # Abstract method must be implemented by subclasses
        try:
            TTSBackend({})       # type: ignore[abstract]
        except TypeError:
            return
        raise AssertionError("expected TypeError instantiating ABC")
