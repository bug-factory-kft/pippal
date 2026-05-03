"""End-to-end-ish tests for the local command server.

Spins a real server on a free port, posts JSON, verifies the engine
seam was called with the right payload."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from pippal.command_server import (
    ALLOWED_EXTENSIONS,
    MAX_READ_FILE_BYTES,
    start_command_server,
)


class _FakeEngine:
    """Captures calls so tests can assert against them."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def replay_text(self, text: str) -> None:
        self.calls.append(text)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(port: int, path: str, body: dict[str, Any]) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


@pytest.fixture()
def server() -> tuple[_FakeEngine, int]:
    engine = _FakeEngine()
    port = _free_port()
    srv = start_command_server(engine, port=port)
    assert srv is not None
    # Tiny wait so the listener thread is actually accepting.
    time.sleep(0.05)
    yield engine, port
    srv.shutdown()
    srv.server_close()


class TestReadEndpoint:
    def test_read_text_routes_to_engine(self, server):
        engine, port = server
        code, _ = _post(port, "/read", {"text": "hello"})
        assert code == 200
        assert engine.calls == ["hello"]

    def test_read_strips_whitespace_and_rejects_empty(self, server):
        engine, port = server
        code, _ = _post(port, "/read", {"text": "   "})
        assert code == 400
        assert engine.calls == []

    def test_read_oversize_text_rejected(self, server):
        engine, port = server
        big = "x" * (200 * 1024 + 10)
        code, _ = _post(port, "/read", {"text": big})
        assert code == 413
        assert engine.calls == []


class TestReadFileEndpoint:
    def test_known_extension_succeeds(self, tmp_path: Path, server):
        engine, port = server
        f = tmp_path / "note.txt"
        f.write_text("hello from a file", encoding="utf-8")
        code, _ = _post(port, "/read-file", {"path": str(f)})
        assert code == 200
        assert engine.calls == ["hello from a file"]

    def test_unknown_extension_rejected(self, tmp_path: Path, server):
        engine, port = server
        f = tmp_path / "thing.exe"
        f.write_bytes(b"not text")
        code, _ = _post(port, "/read-file", {"path": str(f)})
        assert code == 415
        assert engine.calls == []

    def test_oversize_file_rejected(self, tmp_path: Path, server):
        engine, port = server
        f = tmp_path / "big.txt"
        f.write_bytes(b"a" * (MAX_READ_FILE_BYTES + 1))
        code, _ = _post(port, "/read-file", {"path": str(f)})
        assert code == 413
        assert engine.calls == []

    def test_binary_content_rejected(self, tmp_path: Path, server):
        engine, port = server
        f = tmp_path / "ish.txt"
        # Allowed extension, but the bytes look binary (NUL inside the
        # first 1 KB heuristic).
        f.write_bytes(b"hello\x00world")
        code, _ = _post(port, "/read-file", {"path": str(f)})
        assert code == 415
        assert engine.calls == []

    def test_missing_file_404(self, tmp_path: Path, server):
        _, port = server
        code, _ = _post(port, "/read-file", {"path": str(tmp_path / "nope.txt")})
        assert code == 404


class TestServerWiring:
    def test_ping(self, server):
        _, port = server
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping",
                                     timeout=2) as r:
            assert r.status == 200

    def test_unknown_path_is_404(self, server):
        _, port = server
        code, _ = _post(port, "/nope", {})
        assert code == 404

    def test_allowed_extensions_constant(self):
        # Sanity check the constant is in sync with the docstring.
        for ext in ALLOWED_EXTENSIONS:
            assert ext.startswith(".") and ext == ext.lower()
