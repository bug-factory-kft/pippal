"""PipPal web-frontend entry shim (migration spike).

Parallel to ``reader_app.py`` — same single-instance tray app, same
backend, same native global hotkeys, but the windows are a local
HTML/CSS/JS UI hosted in a pywebview (WebView2) frame instead of
Tkinter Toplevels.

``reader_app.py`` (the Tk frontend) is unchanged and still works.

    py -3.11 reader_app_web.py
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from pippal.web_ui.app_web import main  # noqa: E402

if __name__ == "__main__":
    main()
