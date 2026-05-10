"""Piper TTS — out-of-process via the bundled `piper.exe`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..config import DEFAULT_CONFIG
from ..paths import PIPER_DIR, PIPER_EXE, VOICES_DIR
from ..voices import installed_voices
from .base import TTSBackend

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class PiperBackend(TTSBackend):
    name = "piper"

    def is_available(self) -> bool:
        return PIPER_EXE.exists()

    def is_ready(self) -> bool:
        # piper.exe alone isn't enough — synth needs an .onnx voice
        # in VOICES_DIR. Without one, the action handlers should play
        # the onboarding clip instead of letting synth fail silently.
        return self.is_available() and bool(installed_voices())

    def synthesize(self, text: str, out_path: Path) -> bool:
        model = VOICES_DIR / self.config.get("voice", DEFAULT_CONFIG["voice"])
        if not model.exists():
            print(f"[piper] missing model: {model}", file=sys.stderr)
            return False

        cmd = [
            str(PIPER_EXE),
            "--model", str(model),
            "--output_file", str(out_path),
            "--length_scale", str(self.config.get("length_scale", 1.0)),
            "--noise_scale", str(self.config.get("noise_scale", 0.667)),
            "--noise_w", str(self.config.get("noise_w", 0.8)),
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                cwd=str(PIPER_DIR),
                capture_output=True,
                timeout=180,
                creationflags=_NO_WINDOW,
            )
        except Exception as e:
            print(f"[piper] error: {e}", file=sys.stderr)
            return False
        return (
            proc.returncode == 0
            and out_path.exists()
            and out_path.stat().st_size > 0
        )
