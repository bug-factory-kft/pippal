"""Pytest bootstrap.

PipPal follows the PEP-660 src layout (`src/pippal/`, `src/pippal_pro/`).
An editable install (`pip install -e ".[dev]"`) is the canonical way
to make the packages importable, but adding `src/` to `sys.path`
inside conftest.py keeps `python -m pytest` working in a fresh clone
without that one-time install step.

Pytest discovers this conftest at collection time, so the import
path is already correct when the test modules' top-level imports
execute.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)
