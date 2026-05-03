"""PipPal entry shim.

Kept for the autostart .vbs and any existing desktop shortcut. The
actual logic lives in the `pippal` package — see src/pippal/app.py
and src/pippal/__main__.py.

The package follows the PEP-660 src layout, so an editable install
(`pip install -e .`) is the cleanest dev workflow. As a convenience
this shim also adds the local `src/` directory to `sys.path` so a
`git clone && pythonw reader_app.py` workflow keeps working without
the install step.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from pippal.app import main  # noqa: E402

if __name__ == "__main__":
    main()
