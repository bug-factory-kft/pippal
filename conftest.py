"""Pytest bootstrap.

PipPal follows the PEP-660 src layout (`src/pippal/`).
An editable install (`pip install -e ".[dev]"`) is the canonical way
to make the packages importable, but adding `src/` to `sys.path`
inside conftest.py keeps `python -m pytest` working in a fresh clone
without that one-time install step.

Pytest discovers this conftest at collection time, so the import
path is already correct when the test modules' top-level imports
execute.

PipPal is a Windows app. The only reason we run tests on Linux is
the CI runner, which is a headless minimal Ubuntu — Windows-only
stdlib modules like ``winsound`` aren't available there. The block
below stubs them to no-op modules so source code can keep its
top-level ``import winsound`` etc. without conditional logic, and
the tests that exercise those paths patch the stubs anyway.
"""

from __future__ import annotations

import os
import sys
import types
from importlib import metadata as importlib_metadata

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

_real_entry_points = importlib_metadata.entry_points


def _core_only_entry_points(*args: object, **kwargs: object) -> object:
    """Keep unit tests deterministic on machines with extension packages.

    The public runtime still loads installed extensions. Tests exercise only
    this public checkout, so pytest returns no installed PipPal plugin entry
    points during collection.
    """
    entry_points = _real_entry_points(*args, **kwargs)

    class _CoreOnlyEntryPoints:
        def select(self, **params: object) -> object:
            if params.get("group") == "pippal.plugins":
                return []
            return entry_points.select(**params)

        def __getattr__(self, name: str) -> object:
            return getattr(entry_points, name)

        def __iter__(self) -> object:
            return iter(entry_points)

        def __len__(self) -> int:
            return len(entry_points)

        def __getitem__(self, index: object) -> object:
            return entry_points[index]

    return _CoreOnlyEntryPoints()


importlib_metadata.entry_points = _core_only_entry_points


def _stub(name: str, **attrs: object) -> None:
    """Inject a module-shaped no-op into ``sys.modules`` if the real
    one isn't importable on this platform."""
    if name in sys.modules:
        return
    try:
        __import__(name)
    except ImportError:
        mod = types.ModuleType(name)
        for attr, value in attrs.items():
            setattr(mod, attr, value)
        sys.modules[name] = mod


if sys.platform != "win32":
    # ``winsound`` is in the Python stdlib but Windows-only.
    _stub(
        "winsound",
        PlaySound=lambda *a, **k: None,
        SND_PURGE=0,
        SND_FILENAME=0,
        SND_ASYNC=0,
        SND_NODEFAULT=0,
    )
