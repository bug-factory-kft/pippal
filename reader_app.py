"""PipPal entry shim.

Kept for the autostart .vbs and any existing desktop shortcut. All of
the actual logic lives in the `pippal` package — see pippal/app.py and
pippal/__main__.py."""

from pippal.app import main

if __name__ == "__main__":
    main()
