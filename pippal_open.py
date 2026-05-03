"""Tiny client invoked by Windows shell when right-clicking a file →
'Read with PipPal'. Sends the file path to the running PipPal instance."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

# Single source of truth for the IPC port. Repo layout puts pippal/ next
# to this script, so we can import it directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pippal.paths import CMD_SERVER_PORT


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    path = sys.argv[1]
    body = json.dumps({"path": path}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{CMD_SERVER_PORT}/read-file",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return 0
    except Exception:
        return 2


if __name__ == "__main__":
    sys.exit(main())
