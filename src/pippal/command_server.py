"""Tiny HTTP IPC server.

Bound to 127.0.0.1 only. Lets the right-click 'Read with PipPal'
shell entry (and any other helper) ask the running PipPal to read a
file or arbitrary text. Surface is intentionally minimal."""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable, Mapping
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
    engine: Any,
    port: int = CMD_SERVER_PORT,
    commands: Mapping[str, Callable[[], None]] | None = None,
    json_commands: Mapping[str, Callable[[dict[str, Any]], Any]] | None = None,
    queries: Mapping[str, Callable[[], Any]] | None = None,
) -> ThreadingHTTPServer | None:
    """Spin up the listener on a daemon thread. Returns the server (or
    None if the port couldn't be bound)."""

    class CmdHandler(BaseHTTPRequestHandler):
        def _ok(self) -> None:
            self.send_response(200)
            self.end_headers()

        def _json(self, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/ping":
                self._ok()
            elif self.path == "/state":
                self._handle_query("state")
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            if self.path == "/settings":
                self._handle_command("settings")
                return
            if self.path == "/voice-manager":
                self._handle_command("voice-manager")
                return
            if self.path == "/stop":
                self._handle_command("stop")
                return
            if self.path == "/pause":
                self._handle_command("pause")
                return
            if self.path == "/prev":
                self._handle_command("prev")
                return
            if self.path == "/replay":
                self._handle_command("replay")
                return
            if self.path == "/next":
                self._handle_command("next")
                return

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
            elif self.path == "/settings/apply":
                self._handle_json_command("settings.apply", data)
            elif self.path == "/ui/click":
                self._handle_json_command("ui.click", data)
            elif self.path == "/ui/type":
                self._handle_json_command("ui.type", data)
            elif self.path == "/ui/set":
                self._handle_json_command("ui.set", data)
            elif self.path == "/ui/select":
                self._handle_json_command("ui.select", data)
            elif self.path == "/ui/overlay-click":
                self._handle_json_command("ui.overlay_click", data)
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
            engine.read_text_async(text)
            self._ok()

        def _handle_read(self, data: dict[str, Any]) -> None:
            text = (data.get("text") or "").strip()
            if not text:
                self.send_error(400, "missing text")
                return
            if len(text.encode("utf-8")) > MAX_READ_TEXT_BYTES:
                self.send_error(413, "text too large")
                return
            engine.read_text_async(text)
            self._ok()

        def _handle_command(self, name: str) -> None:
            callback = commands.get(name) if commands else None
            if callback is None:
                self.send_error(404)
                return
            try:
                callback()
            except Exception as exc:
                self.send_error(500, f"{name}: {exc}")
                return
            self._ok()

        def _handle_json_command(self, name: str, data: dict[str, Any]) -> None:
            callback = json_commands.get(name) if json_commands else None
            if callback is None:
                self.send_error(404)
                return
            try:
                payload = callback(data)
            except Exception as exc:
                self.send_error(500, f"{name}: {exc}")
                return
            if payload is None:
                self._ok()
            else:
                self._json(payload)

        def _handle_query(self, name: str) -> None:
            callback = queries.get(name) if queries else None
            if callback is None:
                self.send_error(404)
                return
            try:
                payload = callback()
            except Exception as exc:
                self.send_error(500, f"{name}: {exc}")
                return
            self._json(payload)

        def log_message(self, *args: Any, **kw: Any) -> None:
            return

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), CmdHandler)
    except OSError as e:
        print(f"[cmd-server] cannot bind {port}: {e}", file=sys.stderr)
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
