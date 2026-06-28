"""Thin entry-point for the frozen PipPal installer build.

PyInstaller Analysis lists this file as the single script entry point.
It simply delegates to the real application entry point so the package
structure remains the authoritative source of truth.
"""

from pippal.web_ui.app_web import main

if __name__ == "__main__":
    main()
