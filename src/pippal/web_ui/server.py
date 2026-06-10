"""Local static + bridge HTTP server for the web UI.

Serves the static frontend in ``webui/`` and a single JSON endpoint,
``POST /bridge`` ``{ "method": <name>, "args": [...] }``, that invokes
the matching :class:`PipPalBridge` method.

Two consumers:

* the desktop app, when pywebview can't inject ``js_api`` (and as the
  document host for ``webview.create_window(url=...)``);
* the Playwright E2E suite, which points a real browser at this server
  and drives the real DOM against the real backend.

Bound to 127.0.0.1 only. Method names are matched against an explicit
allow-list (public bridge methods, no dunders) so a crafted request
can't reach arbitrary attributes.
"""

from __future__ import annotations

import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .bridge import PipPalBridge

WEBUI_DIR = Path(__file__).resolve().parents[3] / "webui"


def _public_methods(bridge: PipPalBridge) -> set[str]:
    return {
        name
        for name in dir(bridge)
        if not name.startswith("_") and callable(getattr(bridge, name))
    }


class _Handler(SimpleHTTPRequestHandler):
    bridge: PipPalBridge
    allowed: set[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEBUI_DIR), **kwargs)

    def log_message(self, *args: Any, **kw: Any) -> None:  # silence
        return

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/bridge":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > 2 * 1024 * 1024:
            self.send_error(413, "payload too large")
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_error(400, "bad JSON")
            return
        method = str(data.get("method", ""))
        args = data.get("args") or []
        if not isinstance(args, list):
            self._send_json({"__error__": "args must be a list"}, 400)
            return
        if method not in self.allowed:
            self._send_json({"__error__": f"unknown method: {method}"}, 404)
            return
        try:
            result = getattr(self.bridge, method)(*args)
        except Exception as exc:
            self._send_json({"__error__": f"{type(exc).__name__}: {exc}"}, 500)
            return
        self._send_json(result if result is not None else {"ok": True})

    def end_headers(self) -> None:
        # Local-only UI; keep responses uncached so the E2E run always
        # sees the current static assets.
        if self.path.endswith((".js", ".css", ".html")) or self.path in ("/", ""):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def start_web_ui_server(
    bridge: PipPalBridge,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[ThreadingHTTPServer, int]:
    """Start the static + bridge server on a daemon thread.

    ``port=0`` lets the OS pick a free port (used by the desktop app and
    the E2E fixture). Returns ``(server, actual_port)``.
    """
    handler = type(
        "BoundHandler",
        (_Handler,),
        {"bridge": bridge, "allowed": _public_methods(bridge)},
    )
    srv = ThreadingHTTPServer((host, port), handler)
    actual_port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, actual_port
