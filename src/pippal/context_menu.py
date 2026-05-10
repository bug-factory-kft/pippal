"""Windows registry helpers for the 'Read with PipPal' Explorer entry."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .paths import INSTALL_ROOT, PIPER_EXE

CONTEXT_MENU_EXTENSIONS: tuple[str, ...] = (".txt", ".md")
CONTEXT_MENU_LABEL: str = "Read with PipPal"
CONTEXT_MENU_KEY: str = "PipPal"
PIPPAL_OPEN_SCRIPT: str = "pippal_open.py"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _reg_base_path(ext: str) -> str:
    return rf"HKCU\Software\Classes\SystemFileAssociations\{ext}\shell\{CONTEXT_MENU_KEY}"


def _pythonw_path() -> str:
    """Best guess at the windowed Python interpreter."""
    py = sys.executable
    if py.lower().endswith("python.exe"):
        candidate = py[: -len("python.exe")] + "pythonw.exe"
        if Path(candidate).exists():
            return candidate
    return py


def context_menu_status() -> str:
    """Return 'all' / 'partial' / 'none' based on which extensions
    actually have the PipPal entry. Lets Settings warn about half-installed
    state instead of pretending one extension is enough."""
    present = sum(
        1 for ext in CONTEXT_MENU_EXTENSIONS
        if subprocess.run(
            ["reg", "query", _reg_base_path(ext)],
            capture_output=True,
            creationflags=_NO_WINDOW,
        ).returncode == 0
    )
    if present == 0:
        return "none"
    if present == len(CONTEXT_MENU_EXTENSIONS):
        return "all"
    return "partial"


def context_menu_installed() -> bool:
    """Backward-compatible boolean — true only when ALL extensions have
    the entry, so partial drift shows up as 'not installed' and prompts
    the user to re-run Install."""
    return context_menu_status() == "all"


def install_context_menu() -> None:
    """Register 'Read with PipPal' on .txt and .md files for the current
    user. Raises RuntimeError if any registry write fails."""
    pythonw = _pythonw_path()
    client = str(INSTALL_ROOT / PIPPAL_OPEN_SCRIPT)
    cmd = f'"{pythonw}" "{client}" "%1"'

    for ext in CONTEXT_MENU_EXTENSIONS:
        base = _reg_base_path(ext)
        for args in (
            ["reg", "add", base, "/ve", "/d", CONTEXT_MENU_LABEL, "/f"],
            ["reg", "add", base, "/v", "Icon", "/d", str(PIPER_EXE), "/f"],
            ["reg", "add", base + r"\command", "/ve", "/d", cmd, "/f"],
        ):
            rc = subprocess.run(
                args, capture_output=True, creationflags=_NO_WINDOW,
            )
            if rc.returncode != 0:
                err = rc.stderr.decode("utf-8", "replace") or "reg add failed"
                raise RuntimeError(err)


def uninstall_context_menu() -> None:
    for ext in CONTEXT_MENU_EXTENSIONS:
        base = _reg_base_path(ext)
        subprocess.run(
            ["reg", "delete", base, "/f"],
            capture_output=True,
            creationflags=_NO_WINDOW,
        )
