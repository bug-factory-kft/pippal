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

    def test_is_ready_requires_configured_voice_with_sidecar(self, tmp_path: Path):
        exe = tmp_path / "piper.exe"
        exe.write_bytes(b"fake exe")
        (tmp_path / "installed.onnx").write_bytes(b"model")
        (tmp_path / "installed.onnx.json").write_text("{}", encoding="utf-8")

        with patch("pippal.engines.piper.VOICES_DIR", tmp_path), \
             patch("pippal.engines.piper.PIPER_EXE", exe):
            assert PiperBackend({"voice": "missing.onnx"}).is_ready() is False
            assert PiperBackend({"voice": "installed.onnx"}).is_ready() is True

    def test_is_ready_rejects_voice_without_sidecar(self, tmp_path: Path):
        exe = tmp_path / "piper.exe"
        exe.write_bytes(b"fake exe")
        (tmp_path / "orphan.onnx").write_bytes(b"model")

        with patch("pippal.engines.piper.VOICES_DIR", tmp_path), \
             patch("pippal.engines.piper.PIPER_EXE", exe):
            assert PiperBackend({"voice": "orphan.onnx"}).is_ready() is False

    def test_is_ready_rejects_sidecar_the_bundled_piper_cannot_load(self, tmp_path: Path):
        """A copy of an upstream-retrained voice (multi-codepoint phoneme keys)
        must route to onboarding / re-download, not into a doomed synth."""
        exe = tmp_path / "piper.exe"
        exe.write_bytes(b"fake exe")
        (tmp_path / "retrained.onnx").write_bytes(b"model")
        (tmp_path / "retrained.onnx.json").write_text(
            '{"phoneme_id_map": {"a": [14], "aɪ": [161]}}', encoding="utf-8"
        )

        with patch("pippal.engines.piper.VOICES_DIR", tmp_path), \
             patch("pippal.engines.piper.PIPER_EXE", exe):
            backend = PiperBackend({"voice": "retrained.onnx"})
            assert backend.is_ready() is False
            assert backend.synthesize("hello", tmp_path / "out.wav") is False

    def test_failed_piper_run_logs_its_last_error_line(self, tmp_path: Path, capsys):
        """Piper says why it refused a model on stderr; the app used to drop
        it, leaving "Synthesis failed" as the only trace."""
        exe = tmp_path / "piper.exe"
        exe.write_bytes(b"fake exe")
        (tmp_path / "voice.onnx").write_bytes(b"model")
        (tmp_path / "voice.onnx.json").write_text("{}", encoding="utf-8")

        class _Failed:
            returncode = 3
            stderr = (
                "[piper] [info] Loaded voice\r\n"
                '[piper] [error] "aɪ" is not a single codepoint (ids=161,)\r\n\r\n'
            ).encode()

        with patch("pippal.engines.piper.VOICES_DIR", tmp_path), \
             patch("pippal.engines.piper.PIPER_EXE", exe), \
             patch("pippal.engines.piper.subprocess.run", return_value=_Failed()):
            ok = PiperBackend({"voice": "voice.onnx"}).synthesize("hello", tmp_path / "out.wav")

        assert ok is False
        logged = capsys.readouterr().err
        assert "[piper] exit code 3:" in logged
        assert '"aɪ" is not a single codepoint (ids=161,)' in logged
        assert "hello" not in logged


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
