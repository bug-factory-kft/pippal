"""Centralised filesystem paths and runtime constants."""

from __future__ import annotations

from pathlib import Path

# Project root.
#
# `__file__` is `…/src/pippal/paths.py`, so three .parent hops:
#   .parent       → src/pippal/
#   .parent.parent → src/
#   .parent.parent.parent → project root (where reader_app.py lives)
#
# This works for the dev workflow (the user runs `pythonw reader_app.py`
# from the repo root). A future pip-installed packaging mode would
# need a different layout — likely `%APPDATA%/PipPal/` for runtime
# state and an app-install directory for the bundled engine binary.
ROOT: Path = Path(__file__).resolve().parent.parent.parent

# TTS engines
PIPER_DIR: Path = ROOT / "piper"
PIPER_EXE: Path = PIPER_DIR / "piper.exe"

VOICES_DIR: Path = ROOT / "voices"

# Local IPC for the right-click context menu and external integrations.
CMD_SERVER_PORT: int = 51677

# Persistent state.
CONFIG_PATH: Path = ROOT / "config.json"
HISTORY_PATH: Path = ROOT / "history.json"
TEMP_DIR: Path = ROOT / "temp"

# Assets.
ASSET_ICON_PATH: Path = ROOT / "assets" / "pippal_icon.png"


def ensure_dirs() -> None:
    """Create runtime-required directories if they don't exist yet.
    Engine extensions (e.g. pippal_pro for Kokoro) are responsible
    for creating their own directories at registration time."""
    for d in (TEMP_DIR, VOICES_DIR):
        d.mkdir(parents=True, exist_ok=True)
