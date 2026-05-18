"""Tier-2 journey harness: launch the REAL PipPal desktop app with the
WebView2 CDP endpoint enabled, then hand control to the unmodified
production ``main()``.

This is **not** production code and is **not** imported by the app. It
is the entry point the journey conftest spawns as a fresh subprocess
per journey (``py -3.11 e2e/journey/app_launcher.py``). It does exactly
three additive things, none of which change app behaviour:

1. Reads ``PIPPAL_JOURNEY_CDP_PORT`` (set by the conftest to a free
   port) and assigns it to ``webview.settings['REMOTE_DEBUGGING_PORT']``
   *before* ``webview.start()`` runs. pywebview's WebView2 backend
   appends ``--remote-debugging-port=<port>`` to the WebView2
   ``AdditionalBrowserArguments`` from that setting (see
   ``webview/platforms/edgechromium.py``), so the **real** pywebview
   window exposes a Chrome DevTools Protocol endpoint Playwright can
   ``connect_over_cdp`` to and drive with real clicks/keystrokes.

2. Imports ``main`` from the **journey checkout's own** ``src`` (the
   ``reader_app_web.py`` shim's sys.path rule) so the launched app is
   this branch's code, never a globally installed pippal.

3. Calls the unmodified ``pippal.web_ui.app_web.main()``.

``PIPPAL_DATA_DIR`` (fresh per journey), ``PIPPAL_CMD_SERVER_PORT`` /
``PIPPAL_CMD_SERVER_TOKEN`` (the already-landed opt-in hermetic IPC
hooks) and any piper/voice placement are all arranged by the conftest
in the child's environment before this process starts; this launcher
only flips on the debug endpoint.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Use THIS checkout's src (identical rule to reader_app_web.py) so the
# launched real app is the feat/web-ui-migration code, not a globally
# pip-installed pippal that happens to be importable on this machine.
_HERE = Path(__file__).resolve()
_CHECKOUT = _HERE.parents[2]
_SRC = _CHECKOUT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _enable_cdp() -> int:
    """Turn on the WebView2 remote-debugging endpoint on the REAL window.

    Returns the port so the caller can log it. Raises if the port env
    var is missing (the conftest always sets it; a bare manual run can
    export it too).
    """
    port_raw = os.environ.get("PIPPAL_JOURNEY_CDP_PORT")
    if not port_raw:
        raise SystemExit(
            "PIPPAL_JOURNEY_CDP_PORT not set — this launcher must be "
            "spawned by e2e/journey/conftest.py (or export the port)."
        )
    port = int(port_raw)

    import webview

    # pywebview reads this module-global setting when it builds the
    # WebView2 CreationProperties (before webview.start()). Setting it
    # here, in the launcher, leaves production app_web.py untouched.
    webview.settings["REMOTE_DEBUGGING_PORT"] = port
    # Belt-and-braces: also set the env var WebView2 itself honours, so
    # the CDP endpoint comes up even if a pywebview version differs.
    extra = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    flag = f"--remote-debugging-port={port}"
    if flag not in extra:
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
            f"{extra} {flag}".strip()
        )
    return port


def main() -> None:
    port = _enable_cdp()
    # Visible breadcrumb in the app's stdout/stderr log the conftest
    # captures — proves the launcher armed CDP before the UI started.
    print(f"[journey-launcher] CDP armed on 127.0.0.1:{port}", flush=True)
    print(f"[journey-launcher] PIPPAL_DATA_DIR={os.environ.get('PIPPAL_DATA_DIR')}",
          flush=True)

    from pippal.web_ui.app_web import main as app_main

    app_main()


if __name__ == "__main__":
    main()
