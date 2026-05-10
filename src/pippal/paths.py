"""Centralised filesystem paths and runtime constants.

Two roots:

- ``INSTALL_ROOT`` is where the package is installed/extracted from
  (the source checkout in dev, ``Program Files\\WindowsApps\\…`` under
  MSIX). Read-only under MSIX. Holds the bundled engine binary and
  static assets.
- ``DATA_ROOT`` is where runtime/user state lives — voices the user
  installs, config, history, scratch files. Always under
  ``%LOCALAPPDATA%\\PipPal`` so dev and Store builds behave the same
  and we never try to write into the install dir.

``DATA_ROOT`` can be overridden via the ``PIPPAL_DATA_DIR`` env var
so test fixtures can redirect into ``tmp_path`` without touching the
real profile."""

from __future__ import annotations

import os
import sys
from pathlib import Path


# ---- Install root (read-only-safe) -----------------------------------
def _resolve_install_root() -> Path:
    """Where the bundled engine binary and static assets live.

    PyInstaller ``--onedir`` puts ``datas`` under ``_internal/``;
    ``sys._MEIPASS`` points at that ``_internal/`` dir at runtime, so
    ``INSTALL_ROOT/assets/...`` and ``INSTALL_ROOT/piper/...`` resolve
    correctly inside the MSIX bundle.

    In dev (no frozen build) ``__file__`` is ``…/src/pippal/paths.py``,
    so three ``.parent`` hops give the source checkout root."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent.parent.parent


INSTALL_ROOT: Path = _resolve_install_root()

# Bundled engine binary + static assets — the install layer is allowed
# to be read-only.
PIPER_DIR: Path = INSTALL_ROOT / "piper"
PIPER_EXE: Path = PIPER_DIR / "piper.exe"
ASSET_ICON_PATH: Path = INSTALL_ROOT / "assets" / "pippal_icon.png"


# ---- Data root (always writable) -------------------------------------
def _resolve_data_root() -> Path:
    override = os.environ.get("PIPPAL_DATA_DIR")
    if override:
        return Path(override)
    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser(
        "~/AppData/Local"
    )
    return Path(local_appdata) / "PipPal"


DATA_ROOT: Path = _resolve_data_root()

VOICES_DIR: Path = DATA_ROOT / "voices"
CONFIG_PATH: Path = DATA_ROOT / "config.json"
HISTORY_PATH: Path = DATA_ROOT / "history.json"
TEMP_DIR: Path = DATA_ROOT / "temp"

# Local IPC for the right-click context menu and external integrations.
CMD_SERVER_PORT: int = 51677


def ensure_dirs() -> None:
    """Create runtime-required directories if they don't exist yet.
    Engine extensions (e.g. pippal_pro for Kokoro) are responsible
    for creating their own directories at registration time."""
    for d in (DATA_ROOT, TEMP_DIR, VOICES_DIR):
        d.mkdir(parents=True, exist_ok=True)
