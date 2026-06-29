"""Tiny HTTP IPC server.

Bound to 127.0.0.1 only. Lets the right-click 'Read with PipPal'
shell entry (and any other helper) ask the running PipPal to read a
file or arbitrary text. Surface is intentionally minimal."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .paths import CMD_PORT_FILE, CMD_SERVER_PORT


class _SingleInstanceHTTPServer(ThreadingHTTPServer):
    """``ThreadingHTTPServer`` whose bind genuinely fails when the port
    is already held by another live PipPal instance.

    The single-instance gate (``app_web.main`` / ``app.main``: a ``None``
    return from :func:`start_command_server` ⇒ ``raise SystemExit(0)``)
    relies on a *second* process being unable to bind the IPC port. The
    stdlib ``HTTPServer`` defeats that on Windows: it sets
    ``allow_reuse_address = True``, so ``socketserver.TCPServer
    .server_bind`` does ``setsockopt(SO_REUSEADDR, 1)`` — and Windows
    ``SO_REUSEADDR`` lets *two* sockets bind the SAME ``127.0.0.1:port``
    concurrently. The gate therefore never fired for two genuine
    instances on Windows (UC-E9).

    Fix (minimal, correct, cross-platform-safe):

    * **Windows:** force ``allow_reuse_address = False`` (so the stdlib
      never sets ``SO_REUSEADDR``) and instead set ``SO_EXCLUSIVEADDRUSE``
      on the listening socket *before* ``bind()``. With exclusive use a
      second ``bind()`` to a port a live instance already owns fails with
      ``OSError`` (``WSAEADDRINUSE``) for **every** caller regardless of
      privilege — so the first instance serves and the second's
      ``start_command_server`` returns ``None`` and it exits 0.

      Crash-restart safe: ``SO_EXCLUSIVEADDRUSE`` only conflicts with
      *currently-open* sockets, not with ``TIME_WAIT``. A bound-but-never
      -connected listener (the IPC server) has no ``TIME_WAIT`` at all,
      and once the owning process exits/crashes its socket is gone, so a
      fresh ``SO_EXCLUSIVEADDRUSE`` bind to the same port succeeds
      immediately. (``SO_REUSEADDR`` and ``SO_EXCLUSIVEADDRUSE`` are
      mutually exclusive on Windows; we set exactly one.)

    * **Non-Windows:** behaviour is byte-for-byte unchanged — the stdlib
      ``ThreadingHTTPServer`` default (``allow_reuse_address`` /
      ``SO_REUSEADDR``) is preserved, since on POSIX two processes
      genuinely cannot both bind the same ``127.0.0.1:port`` and
      ``SO_REUSEADDR`` there only governs ``TIME_WAIT`` rebinds (which we
      still want, for crash-restart). ``SO_EXCLUSIVEADDRUSE`` does not
      exist outside Windows.

    The public contract is identical except that a real conflicting
    second bind now correctly fails (which is the documented intent).
    """

    if sys.platform == "win32":
        # Stop socketserver.TCPServer.server_bind() from setting
        # SO_REUSEADDR (it does so iff allow_reuse_address is truthy).
        allow_reuse_address = False

        def server_bind(self) -> None:
            # SO_EXCLUSIVEADDRUSE must be set BEFORE bind(). It makes the
            # OS refuse any other socket trying to bind this exact
            # address while this listener is alive — the genuine
            # single-instance guarantee on Windows.
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
            )
            super().server_bind()

# --- E2E hermeticity hook (strictly opt-in, production unchanged) -------
#
# The shell-integration IPC normally binds the fixed well-known port
# ``CMD_SERVER_PORT`` (51677) so the right-click "Read with PipPal" entry
# can find the single running instance. That fixed identity is correct
# for production (one user-visible app instance) but is a hazard for a
# parallel/repeated E2E run: a stale or TIME_WAIT listener from a *prior*
# test can answer ``python -m pippal.open_file``'s POST (subprocess
# returncode 0) while the fresh per-test engine never reacts — a
# false-negative flake.
#
# These two env vars let an E2E harness make each test's IPC HERMETIC
# without changing any production code path:
#
# * ``PIPPAL_CMD_SERVER_PORT`` — override the bind/target port. ``0``
#   asks the OS for a free ephemeral port (no fixed-port collision is
#   possible). ``start_command_server`` writes the actually-bound port
#   back so the harness can read it.
# * ``PIPPAL_CMD_SERVER_TOKEN`` — an opaque per-instance identity. When
#   set, the server REQUIRES the matching ``X-PipPal-Token`` header and
#   404s anything else, and ``open_file`` sends it. A stale listener
#   from another test (different token, or none) therefore cannot
#   satisfy this test's request.
#
# When neither var is set, behaviour is byte-for-byte identical to
# before: the fixed port, no token check. Production never sets them.
_ENV_PORT = "PIPPAL_CMD_SERVER_PORT"
_ENV_TOKEN = "PIPPAL_CMD_SERVER_TOKEN"
TOKEN_HEADER = "X-PipPal-Token"


def _env_port_override() -> int | None:
    raw = os.environ.get(_ENV_PORT)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_token() -> str | None:
    tok = os.environ.get(_ENV_TOKEN)
    return tok if tok else None


# --- Port persistence and connect-first helpers -------------------------
#
# The running instance writes its actually-bound port to CMD_PORT_FILE so
# that a second startup can discover it via connect-first probe rather than
# inferring it from a well-known default.  This is the key piece that makes
# the single-instance detection robust when the default port (51677) is
# inside an OS-excluded TCP range (Hyper-V / WSL2 / Docker reservations).


def read_cmd_port_file() -> int | None:
    """Return the port recorded by the running instance, or None."""
    try:
        text = CMD_PORT_FILE.read_text(encoding="utf-8").strip()
        port = int(text)
        if 1 <= port <= 65535:
            return port
        return None
    except Exception:
        return None


def write_cmd_port_file(port: int) -> None:
    """Atomically persist *port* so the next startup can find us."""
    try:
        CMD_PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CMD_PORT_FILE.with_name(".cmd_port.tmp")
        tmp.write_text(str(port), encoding="utf-8")
        tmp.replace(CMD_PORT_FILE)
    except Exception:
        pass  # Best-effort; a missing file just means probe falls back to default.


def resolve_candidate_port() -> int:
    """Return the port to probe for a running instance.

    Priority order:
    1. ``PIPPAL_CMD_SERVER_PORT`` env (E2E harness / explicit override).
    2. Value persisted in ``CMD_PORT_FILE`` by a running instance
       (covers the fallback-port case where the default was excluded).
    3. The compiled-in default ``CMD_SERVER_PORT`` (51677).
    """
    env_port = _env_port_override()
    if env_port is not None:
        return env_port
    file_port = read_cmd_port_file()
    if file_port is not None:
        return file_port
    return CMD_SERVER_PORT


def probe_running_instance(port: int, timeout: float = 0.4) -> bool:
    """Return True if a live PipPal instance is listening on *port*.

    Sends a GET /ping and checks for HTTP 200.  The short *timeout* keeps
    startup snappy even when nothing is there.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/ping", timeout=timeout
        ) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception:
        return False


# Caps to keep a malicious or accidental client from freezing the engine.
MAX_READ_FILE_BYTES = 200 * 1024     # 200 KB
MAX_READ_TEXT_BYTES = 200 * 1024
ALLOWED_EXTENSIONS = (".txt", ".md", ".log", ".csv", ".json", ".html", ".xml")
_CONTROL_COMMAND_ROUTES = {
    "/settings": "settings",
    "/voice-manager": "voice-manager",
    "/first-run-check": "first-run-check",
    "/stop": "stop",
    "/pause": "pause",
    "/prev": "prev",
    "/replay": "replay",
    "/next": "next",
}
_CONTROL_QUERY_ROUTES = {"/state": "state"}
_CONTROL_JSON_COMMAND_ROUTES = {
    "/settings/apply": "settings.apply",
    "/ui/click": "ui.click",
    "/ui/type": "ui.type",
    "/ui/set": "ui.set",
    "/ui/select": "ui.select",
    "/ui/window-move": "ui.window_move",
    "/ui/overlay-click": "ui.overlay_click",
}


def _looks_binary(sample: bytes) -> bool:
    """Heuristic: NUL bytes mean it's almost certainly not text."""
    return b"\x00" in sample[:1024]


def start_command_server(
    engine: Any,
    port: int = CMD_SERVER_PORT,
    commands: Mapping[str, Callable[[], None]] | None = None,
    json_commands: Mapping[str, Callable[[dict[str, Any]], Any]] | None = None,
    queries: Mapping[str, Callable[[], Any]] | None = None,
    control_routes_enabled: bool = False,
) -> ThreadingHTTPServer | None:
    """Spin up the listener on a daemon thread. Returns the server (or
    None if the port couldn't be bound).

    Production callers get the documented public IPC surface by default.
    UI/state automation routes are available only when an explicit E2E
    harness opts in with ``control_routes_enabled``.

    Hermeticity (opt-in, production unchanged): if ``port`` is left at
    its default and ``PIPPAL_CMD_SERVER_PORT`` is set, that env value is
    bound instead (``0`` => an OS-assigned free port). If
    ``PIPPAL_CMD_SERVER_TOKEN`` is set, every request must carry a
    matching ``X-PipPal-Token`` header or it is rejected (404), so a
    stale listener from another test/instance cannot answer this one.
    The actually-bound port is written back to ``PIPPAL_CMD_SERVER_PORT``
    so the harness can target exactly this instance.

    Bind-with-fallback (production default port only): when the caller
    uses the default ``CMD_SERVER_PORT`` and the OS refuses to bind it
    (e.g. Hyper-V / WSL2 excluded-port range, ``WinError 10013``), the
    server falls back to an OS-assigned free port (port 0) rather than
    returning ``None``.  The actually-bound port is persisted to
    ``CMD_PORT_FILE`` so the next startup's connect-first probe finds the
    right address.  Callers that pass an explicit non-default port keep the
    old contract (``None`` on bind failure) so existing tests are unaffected.
    """
    # Track whether we're in "production default" mode before any override.
    # Only in this mode do we apply bind-with-fallback and port persistence.
    _production_mode = (port == CMD_SERVER_PORT)

    # Only consult the env override when the caller didn't request a
    # specific non-default port — production callers (app.py) always pass
    # the default, so this is where the opt-in applies without ever
    # changing an explicit port a real caller chose.
    if _production_mode:
        env_port = _env_port_override()
        if env_port is not None:
            port = env_port
    required_token = _env_token()

    class CmdHandler(BaseHTTPRequestHandler):
        def _token_ok(self) -> bool:
            if required_token is None:
                return True
            if self.headers.get(TOKEN_HEADER) == required_token:
                return True
            # Wrong/absent identity: behave exactly like an unknown
            # route so a probing/stale client gets the same 404 it
            # would for any other unsupported request. Drain any request
            # body FIRST and ask for a clean close: a BaseHTTPRequest-
            # Handler that responds + closes without consuming the
            # pending POST body makes Windows RST the socket, which the
            # client sees as ConnectionAbortedError instead of a clean
            # 404 (an intermittent failure under load / parallel runs).
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except (TypeError, ValueError):
                length = 0
            if length > 0:
                try:
                    remaining = length
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 65536))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                except Exception:
                    pass
            self.close_connection = True
            self.send_error(404)
            return False

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
            if not self._token_ok():
                return
            if self.path == "/ping":
                self._ok()
            elif self.path in _CONTROL_QUERY_ROUTES:
                if not control_routes_enabled:
                    self.send_error(404)
                    return
                self._handle_query(_CONTROL_QUERY_ROUTES[self.path])
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            if not self._token_ok():
                return
            command = _CONTROL_COMMAND_ROUTES.get(self.path)
            if command is not None:
                if not control_routes_enabled:
                    self.send_error(404)
                    return
                self._handle_command(command)
                return

            json_command = _CONTROL_JSON_COMMAND_ROUTES.get(self.path)
            if json_command is not None and not control_routes_enabled:
                self.send_error(404)
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
            elif json_command is not None:
                self._handle_json_command(json_command, data)
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
        srv = _SingleInstanceHTTPServer(("127.0.0.1", port), CmdHandler)
    except OSError as e:
        if not _production_mode:
            # Explicit non-default port: preserve the existing contract.
            print(f"[cmd-server] cannot bind {port}: {e}", file=sys.stderr)
            return None
        # Production default port failed (e.g. WinError 10013 excluded-port
        # range, or WinError 10048 transient in-use). Fall back to an
        # OS-assigned free port — never mistake this for "already running".
        print(
            f"[cmd-server] cannot bind {port} ({e}); falling back to free port",
            file=sys.stderr,
        )
        try:
            srv = _SingleInstanceHTTPServer(("127.0.0.1", 0), CmdHandler)
        except OSError as e2:
            print(f"[cmd-server] cannot bind free port: {e2}", file=sys.stderr)
            return None

    actual_port = srv.server_address[1]

    # Publish the actually-bound port. With an OS-assigned ephemeral
    # port (env override = 0, or fallback from excluded default) this is
    # how the E2E harness and the next-startup connect-first probe learn
    # which port to target.
    if _env_port_override() is not None:
        os.environ[_ENV_PORT] = str(actual_port)

    # Always persist in production mode so the next startup can probe
    # the right address (crucial when the default port was excluded and
    # we fell back to a free port).
    if _production_mode:
        write_cmd_port_file(actual_port)

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
