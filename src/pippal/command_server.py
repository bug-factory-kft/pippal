"""Tiny HTTP IPC server.

Bound to 127.0.0.1 only. Lets the right-click 'Read with PipPal'
shell entry (and any other helper) ask the running PipPal to read a
file or arbitrary text. Surface is intentionally minimal."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .paths import CMD_SERVER_PORT

# Caps to keep a malicious or accidental client from freezing the engine.
MAX_READ_FILE_BYTES = 200 * 1024     # 200 KB
MAX_READ_TEXT_BYTES = 200 * 1024
ALLOWED_EXTENSIONS = (".txt", ".md", ".log", ".csv", ".json", ".html", ".xml")


def _looks_binary(sample: bytes) -> bool:
    """Heuristic: NUL bytes mean it's almost certainly not text."""
    return b"\x00" in sample[:1024]


def start_command_server(
    engine: Any, port: int = CMD_SERVER_PORT,
) -> ThreadingHTTPServer | None:
    """Spin up the listener on a daemon thread. Returns the server (or
    None if the port couldn't be bound)."""

    class CmdHandler(BaseHTTPRequestHandler):
        def _ok(self) -> None:
            self.send_response(200)
            self.end_headers()

        def do_GET(self) -> None:
            if self.path == "/ping":
                self._ok()
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length > MAX_READ_TEXT_BYTES * 2:    # cheap guard before json parse
                self.send_error(413, "payload too large")
                return
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self.send_error(400, "bad JSON")
                return

            if self.path == "/read-file":
                self._handle_read_file(data)
            elif self.path == "/read":
                self._handle_read(data)
            else:
                self.send_error(404)

        def _handle_read_file(self, data: dict[str, Any]) -> None:
            p = (data.get("path") or "").strip()
            if not p:
                self.send_error(400, "missing path")
                return
            path = Path(p)
            if not path.is_file():
                self.send_error(404, "no such file")
                return
            if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                self.send_error(415, f"extension not allowed: {path.suffix}")
                return
            try:
                size = path.stat().st_size
            except OSError as e:
                self.send_error(500, f"stat: {e}")
                return
            if size > MAX_READ_FILE_BYTES:
                self.send_error(413,
                                f"file too large ({size} bytes; "
                                f"max {MAX_READ_FILE_BYTES})")
                return
            try:
                blob = path.read_bytes()
            except OSError as e:
                self.send_error(500, f"read: {e}")
                return
            if _looks_binary(blob):
                self.send_error(415, "looks binary")
                return
            text = blob.decode("utf-8", errors="replace")
            engine.replay_text(text)
            self._ok()

        def _handle_read(self, data: dict[str, Any]) -> None:
            text = (data.get("text") or "").strip()
            if not text:
                self.send_error(400, "missing text")
                return
            if len(text.encode("utf-8")) > MAX_READ_TEXT_BYTES:
                self.send_error(413, "text too large")
                return
            engine.replay_text(text)
            self._ok()

        def log_message(self, *args: Any, **kw: Any) -> None:
            return

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), CmdHandler)
    except OSError as e:
        print(f"[cmd-server] cannot bind {port}: {e}", file=sys.stderr)
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
