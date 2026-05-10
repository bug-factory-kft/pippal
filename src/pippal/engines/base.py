"""Abstract TTS backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class TTSBackend(ABC):
    """Pluggable speech synthesizer. Produces a WAV file from text.

    Subclasses must override `synthesize`. `is_available` should return
    False when the engine's binary or runtime deps are missing so the
    factory can fall back gracefully.
    """

    name: str = "base"

    def __init__(self, config: dict[str, Any]) -> None:
        # Shallow-copy so the backend's view of config is frozen at
        # construction time. The live config dict is mutable (apply_mood
        # writes in place); without this snapshot, a mood change between
        # synth calls would change the voice mid-paragraph for any
        # cached backend.
        self.config: dict[str, Any] = dict(config)

    @abstractmethod
    def synthesize(self, text: str, out_path: Path) -> bool:
        """Render `text` to a WAV at `out_path`. Return True on success."""

    def is_available(self) -> bool:
        return True

    def is_ready(self) -> bool:
        """Stronger check than ``is_available``: the engine is wired up
        AND has a voice / model loaded ready to actually synth.

        Default is ``is_available()`` because a backend that doesn't
        carry per-voice assets (a hypothetical self-contained engine)
        needs nothing more. Piper overrides to also require an .onnx
        voice on disk. Plugin-registered backends should override when
        their availability check doesn't already gate on the per-voice
        assets they need."""
        return self.is_available()
