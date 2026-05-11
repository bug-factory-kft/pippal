"""Command-line helper for Explorer's "Read with PipPal" action."""

from __future__ import annotations

import json
import sys
import urllib.request

from .paths import CMD_SERVER_PORT


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
        with urllib.request.urlopen(req, timeout=5):
            return 0
    except Exception:
        return 2


if __name__ == "__main__":
    sys.exit(main())
