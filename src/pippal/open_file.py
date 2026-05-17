"""Command-line helper for Explorer's "Read with PipPal" action."""

from __future__ import annotations

import json
import sys
import urllib.request

from .command_server import TOKEN_HEADER, _env_port_override, _env_token
from .paths import CMD_SERVER_PORT


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    path = sys.argv[1]
    body = json.dumps({"path": path}).encode("utf-8")
    # Production: the fixed well-known port, no token — byte-identical
    # to before. E2E (opt-in via PIPPAL_CMD_SERVER_PORT /
    # PIPPAL_CMD_SERVER_TOKEN): target THIS test's hermetic instance so
    # a stale/TIME_WAIT listener from another test cannot answer.
    port = _env_port_override()
    if port is None or port == 0:
        port = CMD_SERVER_PORT
    headers = {"Content-Type": "application/json"}
    token = _env_token()
    if token:
        headers[TOKEN_HEADER] = token
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/read-file",
        data=body,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return 0
    except Exception:
        return 2


if __name__ == "__main__":
    # The subprocess inherits the parent's environment, so the E2E
    # harness only has to export the two vars once; nothing here reads
    # them when they are unset (production).
    sys.exit(main())
