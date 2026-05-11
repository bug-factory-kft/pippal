from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pippal import playback
from pippal.engine import TTSEngine


@pytest.fixture()
def engine() -> TTSEngine:
    return TTSEngine(MagicMock(), {"engine": "piper"}, overlay_ref=lambda: None)


def test_playback_does_not_reuse_stale_token_index_chunks(
    engine: TTSEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = tmp_path / "out_1_1.wav"
    stale.write_bytes(b"stale wav from old process")
    calls: list[tuple[str, Path]] = []

    def synthesize(text: str, out_path: Path, backend: Any = None) -> bool:
        calls.append((text, out_path))
        out_path.write_bytes(f"fresh:{text}".encode())
        return True

    monkeypatch.setattr(playback, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(playback, "split_sentences", lambda _text: ["first", "second"])
    monkeypatch.setattr(playback, "wav_duration", lambda _path: 0.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *args, **kwargs: None)
    monkeypatch.setattr(engine, "_synthesize", synthesize)

    engine.token = 1
    playback.play_one(engine, "ignored", my_token=1, backend=object())

    synthesized = {text for text, _path in calls}
    assert synthesized == {"first", "second"}
    assert stale.exists()
    assert stale.read_bytes() == b"stale wav from old process"
    assert all(path.name != "out_1_1.wav" for _text, path in calls)
