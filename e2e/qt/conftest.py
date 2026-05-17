"""pytest-qt fixtures for the PySide6 UI E2E suite.

These tests drive the REAL Qt widgets with REAL input events
(``qtbot.mouseClick`` / ``qtbot.keyClicks``) and explicit waits
(``qtbot.waitUntil`` / ``waitSignal``) — no fixed sleeps. The backend
(config, engine, voices, history, playback) is the real PipPal
backend; only an isolated ``PIPPAL_DATA_DIR`` and a tiny in-process
fake TTS backend keep the run hermetic and offline.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

# Make the src-layout package importable in a fresh clone.
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(scope="session", autouse=True)
def require_live_windows():
    """Override the parent ``e2e/conftest.py`` session gate.

    The Qt UI E2E suite is self-contained: it constructs the real Qt
    widgets in-process with pytest-qt and an isolated data dir, so it
    does NOT need the live-desktop launcher gate (``PIPPAL_E2E_LIVE``)
    the legacy live-UI harness requires. Shadowing the parent fixture
    here keeps ``pytest e2e/qt`` runnable on its own (and in CI)."""
    yield


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirect all PipPal state into tmp_path BEFORE importing the
    package so paths.py resolves the isolated root."""
    data_dir = tmp_path / "pippal-data"
    data_dir.mkdir()
    monkeypatch.setenv("PIPPAL_DATA_DIR", str(data_dir))

    # paths.py reads PIPPAL_DATA_DIR at import time; if it (or a
    # submodule) was already imported by an earlier test, force the
    # path constants to the new tmp dir.
    import importlib

    import pippal.paths as paths
    importlib.reload(paths)
    for modname in ("pippal.config", "pippal.history", "pippal.voices",
                    "pippal.onboarding"):
        if modname in sys.modules:
            importlib.reload(sys.modules[modname])
    paths.ensure_dirs()
    yield data_dir


def _write_wav(path: Path, seconds: float = 0.3) -> None:
    """Write a real, valid RIFF/WAVE PCM file the engine can play and
    the runtime snapshot can validate as a genuine audio chunk."""
    rate = 22050
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


@pytest.fixture
def fake_tts(monkeypatch):
    """Register an in-process TTS backend that emits a real WAV.

    There is no bundled piper.exe in CI, so we substitute a backend
    that exercises the SAME engine → playback → audio-chunk pipeline
    and writes a genuine RIFF/WAVE file. The test asserts the real
    engine effect (is_speaking, backend class, audio chunk on disk),
    not a mock call count."""
    from pippal import plugins
    from pippal.engines.base import TTSBackend

    class FakeTTS(TTSBackend):
        name = "faketts"

        def is_available(self) -> bool:
            return True

        def is_ready(self) -> bool:
            return True

        def synthesize(self, text: str, out_path: Path) -> bool:
            _write_wav(Path(out_path), max(0.2, min(2.0, len(text) / 60)))
            return True

    plugins.register_engine("faketts", FakeTTS)
    yield FakeTTS
