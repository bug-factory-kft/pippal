"""Pytest fixtures and gating for maintained selected-text UI smokes.

These smokes drive Notepad and Edge directly to validate the public
``pippal.clipboard_capture.capture_selection`` path against real
Windows desktop apps. They are intentionally separated from the fast
default ``python -m pytest`` run because they:

- require a Windows desktop session (real focus, real Ctrl+C delivery);
- spawn foreign processes (``notepad.exe``, ``msedge.exe``);
- depend on a default-installed Edge being present on the box.

Gating contract (issue #62):

- ``platform.system() != 'Windows'`` -> skip with an honest reason.
- ``PIPPAL_UI_SMOKES != '1'`` -> skip with an honest reason.
- Missing binaries (Notepad / Edge) -> the relevant test is marked
  ``unavailable`` via pytest.skip with the path that was searched.

The skip path is opt-in only. The release-gate runner
``e2e/run-ui-smokes.ps1`` sets ``PIPPAL_UI_SMOKES=1``, so these
smokes are *not* "green by default" — a skipped run on the gate
machine is recorded as ``blocked``.
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

import pytest

UI_SMOKES_ENV: str = "PIPPAL_UI_SMOKES"
EVIDENCE_DIR_ENV: str = "PIPPAL_UI_SMOKES_EVIDENCE_DIR"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "ui_smoke: maintained selected-text UI smoke against a foreign Windows app",
    )


@pytest.fixture(scope="session", autouse=True)
def _require_windows_and_env() -> None:
    if platform.system() != "Windows":
        pytest.skip("PipPal selected-text UI smokes require Windows")
    if os.environ.get(UI_SMOKES_ENV) != "1":
        pytest.skip(
            f"set {UI_SMOKES_ENV}=1 (or run e2e/run-ui-smokes.ps1) to opt in "
            "to the maintained UI smokes; default pytest stays headless"
        )


@pytest.fixture(scope="session")
def evidence_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    raw = os.environ.get(EVIDENCE_DIR_ENV)
    if raw:
        root = Path(raw).resolve()
    else:
        root = tmp_path_factory.mktemp("pippal-ui-smokes-evidence")
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="session")
def notepad_exe() -> Path:
    candidates = [
        Path(r"C:\Windows\System32\notepad.exe"),
        Path(r"C:\Windows\notepad.exe"),
    ]
    which = shutil.which("notepad.exe")
    if which:
        candidates.insert(0, Path(which))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip(
        f"notepad.exe not found in {[str(c) for c in candidates]}; "
        "Notepad UI smoke is unavailable on this machine"
    )


@pytest.fixture(scope="session")
def edge_exe() -> Path:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    which = shutil.which("msedge.exe")
    if which:
        candidates.insert(0, Path(which))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip(
        f"msedge.exe not found in {[str(c) for c in candidates]}; "
        "Edge browser UI smoke is unavailable on this machine"
    )


@pytest.fixture(scope="session")
def acrobat_exe() -> Path | None:
    """Resolve an Acrobat / Adobe Reader executable, or ``None``.

    Unlike the Notepad/Edge fixtures this returns ``None`` rather than
    skipping when no Acrobat install is found. Issue #63 requires
    Acrobat absence to surface as an ``unavailable`` smoke result with
    structured evidence, not as a pytest skip — the smoke itself
    records the "Acrobat not installed" outcome via pytest.skip with a
    machine-readable reason. Returning ``None`` here lets the smoke
    distinguish "no Acrobat" from "Acrobat present but broken".
    """

    # Imported lazily because conftest must remain importable on
    # non-Windows CI where the harness module pulls Windows-only
    # subprocess assumptions when its helpers are called.
    from . import _harness as harness

    return harness.find_acrobat_exe()
