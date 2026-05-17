"""PipPal PySide6 frontend entry shim (migration spike).

Parallel to ``reader_app.py`` (the Tk entry). Launches the new Qt
frontend wired to the existing PipPal backend. The Tk entry is
unchanged and remains the default; this file selects the migrated UI.

As with ``reader_app.py``, this adds the local ``src/`` to ``sys.path``
so a ``git clone && python reader_app_qt.py`` workflow works without an
editable install.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from pippal.app_qt import main  # noqa: E402

if __name__ == "__main__":
    main()
