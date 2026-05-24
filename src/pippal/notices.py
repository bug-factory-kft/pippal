"""Locate the bundled third-party licence notices file.

Pure, UI-agnostic path resolution shared by any front-end that wants to
surface the open-source notices. No Tk — just the filesystem.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .paths import INSTALL_ROOT

_NOTICES_CANDIDATES: tuple[str, ...] = (
    "NOTICES.txt",
    "packaging/build/NOTICES.txt",
    "docs/THIRD_PARTY.md",
)


def _candidate_notice_roots() -> tuple[Path, ...]:
    here = Path(__file__).resolve()
    roots = [
        INSTALL_ROOT,
        here.parents[1],
        here.parents[2],
    ]
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def resolve_notices_path(roots: Iterable[Path] | None = None) -> Path | None:
    for root in roots or _candidate_notice_roots():
        for rel in _NOTICES_CANDIDATES:
            path = root / rel
            if path.exists():
                return path
    return None
