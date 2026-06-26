"""Unit tests for PipPalBridge.remove_voice — lock-before-delete fix.

Verifies:
  1. Happy path: files deleted, ok:True, files actually gone.
  2. Locked-file path: unlink always raises, ok:False with error message, no
     false success claim.
  3. reset_backend is called BEFORE unlink (ordering invariant).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from pippal.web_ui.bridge import PipPalBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stub_engine() -> MagicMock:
    engine = MagicMock()
    engine.is_speaking = False
    engine._is_paused = False
    engine._backend_name = "stub"
    engine._backend_cls = None
    engine._chunks = []
    engine._chunk_paths = []
    engine._queue = []
    type(engine).is_paused = property(lambda self: self._is_paused)
    engine.lock = threading.Lock()
    return engine


def _make_bridge(engine: Any, config: dict | None = None) -> PipPalBridge:
    return PipPalBridge(engine=engine, config=config or {})


_FAKE_VOICE = {
    "id": "en_US-test-high",
    "lang": "en_US",
    "name": "test",
    "quality": "high",
    "label": "Test",
}


# ---------------------------------------------------------------------------
# Happy-path: files present and deleted successfully
# ---------------------------------------------------------------------------

class TestRemoveVoiceHappyPath:
    """remove_voice deletes both files and returns ok:True."""

    def test_files_deleted_and_ok_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both .onnx and .onnx.json are deleted; result is ok:True."""
        # Create fake voice files in tmp_path
        onnx = tmp_path / "en_US-test-high.onnx"
        onnx.write_bytes(b"fake_model")
        sidecar = tmp_path / "en_US-test-high.onnx.json"
        sidecar.write_text("{}", encoding="utf-8")

        # Point module-level VOICES_DIR to tmp_path
        monkeypatch.setattr("pippal.web_ui.bridge.VOICES_DIR", tmp_path)
        # Stub plugins.voices() so _voice_by_id resolves our fake voice
        monkeypatch.setattr("pippal.plugins.voices", lambda: [_FAKE_VOICE])

        engine = _make_stub_engine()
        bridge = _make_bridge(engine)

        result = bridge.remove_voice("en_US-test-high")

        assert result == {"ok": True}, f"Expected ok:True, got {result}"
        assert not onnx.exists(), ".onnx file must be deleted"
        assert not sidecar.exists(), ".onnx.json file must be deleted"

    def test_missing_files_are_ok(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the voice files are already absent, result is still ok:True."""
        monkeypatch.setattr("pippal.web_ui.bridge.VOICES_DIR", tmp_path)
        monkeypatch.setattr("pippal.plugins.voices", lambda: [_FAKE_VOICE])

        engine = _make_stub_engine()
        bridge = _make_bridge(engine)

        result = bridge.remove_voice("en_US-test-high")

        assert result == {"ok": True}, (
            "Absent files (nothing to delete) should resolve to ok:True"
        )


# ---------------------------------------------------------------------------
# Locked-file path: unlink always raises PermissionError
# ---------------------------------------------------------------------------

class TestRemoveVoiceLockedFile:
    """When unlink raises (file locked), remove_voice returns ok:False."""

    def test_ok_false_when_unlink_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Monkeypatched unlink always raises; result must be ok:False with
        an error message that names the still-present file."""
        onnx = tmp_path / "en_US-test-high.onnx"
        onnx.write_bytes(b"fake_model")
        sidecar = tmp_path / "en_US-test-high.onnx.json"
        sidecar.write_text("{}", encoding="utf-8")

        monkeypatch.setattr("pippal.web_ui.bridge.VOICES_DIR", tmp_path)
        monkeypatch.setattr("pippal.plugins.voices", lambda: [_FAKE_VOICE])

        # Make Path.unlink always raise PermissionError (simulates Windows lock)
        original_unlink = Path.unlink

        def _locked_unlink(self: Path, missing_ok: bool = False) -> None:  # noqa: FBT001
            raise PermissionError(f"Access is denied: {self}")

        monkeypatch.setattr(Path, "unlink", _locked_unlink)

        # Speed up retries in the test by patching time.sleep
        with patch("time.sleep"):
            engine = _make_stub_engine()
            bridge = _make_bridge(engine)
            result = bridge.remove_voice("en_US-test-high")

        assert result.get("ok") is False, (
            "Must return ok:False when files are still locked after retries"
        )
        assert "error" in result, "Must include an 'error' key"
        assert "en_US-test-high" in result["error"], (
            "Error message must name the locked file"
        )

    def test_no_false_success_on_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Must NOT return ok:True when the file is still on disk."""
        onnx = tmp_path / "en_US-test-high.onnx"
        onnx.write_bytes(b"fake_model")
        sidecar = tmp_path / "en_US-test-high.onnx.json"
        sidecar.write_text("{}", encoding="utf-8")

        monkeypatch.setattr("pippal.web_ui.bridge.VOICES_DIR", tmp_path)
        monkeypatch.setattr("pippal.plugins.voices", lambda: [_FAKE_VOICE])

        def _locked_unlink(self: Path, missing_ok: bool = False) -> None:  # noqa: FBT001
            raise PermissionError(f"Access is denied: {self}")

        monkeypatch.setattr(Path, "unlink", _locked_unlink)

        with patch("time.sleep"):
            engine = _make_stub_engine()
            bridge = _make_bridge(engine)
            result = bridge.remove_voice("en_US-test-high")

        assert result.get("ok") is not True, (
            "Must not claim ok:True when file still exists on disk"
        )


# ---------------------------------------------------------------------------
# Ordering: reset_backend called BEFORE any unlink
# ---------------------------------------------------------------------------

class TestRemoveVoiceOrdering:
    """reset_backend must be called before the first unlink (release then delete)."""

    def test_reset_backend_called_before_unlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify ordering via call log: reset_backend must appear first."""
        onnx = tmp_path / "en_US-test-high.onnx"
        onnx.write_bytes(b"fake_model")
        sidecar = tmp_path / "en_US-test-high.onnx.json"
        sidecar.write_text("{}", encoding="utf-8")

        monkeypatch.setattr("pippal.web_ui.bridge.VOICES_DIR", tmp_path)
        monkeypatch.setattr("pippal.plugins.voices", lambda: [_FAKE_VOICE])

        call_order: list[str] = []

        engine = _make_stub_engine()

        def _spy_reset() -> None:
            call_order.append("reset_backend")

        engine.reset_backend.side_effect = _spy_reset

        original_unlink = Path.unlink

        def _spy_unlink(self: Path, missing_ok: bool = False) -> None:  # noqa: FBT001
            call_order.append(f"unlink:{self.name}")
            original_unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", _spy_unlink)

        bridge = _make_bridge(engine)
        result = bridge.remove_voice("en_US-test-high")

        assert result.get("ok") is True, f"Expected ok:True, got {result}"
        assert "reset_backend" in call_order, "reset_backend must be called"
        unlink_indices = [i for i, e in enumerate(call_order) if e.startswith("unlink:")]
        reset_idx = call_order.index("reset_backend")
        assert all(reset_idx < ui for ui in unlink_indices), (
            f"reset_backend (pos {reset_idx}) must precede all unlinks "
            f"(positions {unlink_indices}). Call order: {call_order}"
        )

    def test_reset_backend_called_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """reset_backend is called exactly once per remove_voice invocation."""
        onnx = tmp_path / "en_US-test-high.onnx"
        onnx.write_bytes(b"fake_model")
        sidecar = tmp_path / "en_US-test-high.onnx.json"
        sidecar.write_text("{}", encoding="utf-8")

        monkeypatch.setattr("pippal.web_ui.bridge.VOICES_DIR", tmp_path)
        monkeypatch.setattr("pippal.plugins.voices", lambda: [_FAKE_VOICE])

        engine = _make_stub_engine()
        bridge = _make_bridge(engine)
        bridge.remove_voice("en_US-test-high")

        engine.reset_backend.assert_called_once_with()
