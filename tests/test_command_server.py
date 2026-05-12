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
        self.replay_calls: list[str] = []

    def read_text_async(self, text: str) -> None:
        self.calls.append(text)

    def replay_text(self, text: str) -> None:
        self.replay_calls.append(text)


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


def _post_empty(port: int, path: str) -> tuple[int, str]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=b"",
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _get(port: int, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}",
                                     timeout=2) as r:
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
        assert engine.replay_calls == []

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
        assert engine.replay_calls == []

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

    def test_settings_command_routes_to_callback(self):
        engine = _FakeEngine()
        port = _free_port()
        calls: list[str] = []
        srv = start_command_server(
            engine,
            port=port,
            commands={"settings": lambda: calls.append("settings")},
        )
        assert srv is not None
        time.sleep(0.05)
        try:
            code, _ = _post_empty(port, "/settings")
            assert code == 200
            assert calls == ["settings"]
        finally:
            srv.shutdown()
            srv.server_close()

    def test_voice_manager_command_routes_to_callback(self):
        engine = _FakeEngine()
        port = _free_port()
        calls: list[str] = []
        srv = start_command_server(
            engine,
            port=port,
            commands={"voice-manager": lambda: calls.append("voice-manager")},
        )
        assert srv is not None
        time.sleep(0.05)
        try:
            code, _ = _post_empty(port, "/voice-manager")
            assert code == 200
            assert calls == ["voice-manager"]
        finally:
            srv.shutdown()
            srv.server_close()

    @pytest.mark.parametrize("path", ["/stop", "/pause", "/prev", "/replay", "/next"])
    def test_player_commands_route_to_callbacks(self, path: str):
        engine = _FakeEngine()
        port = _free_port()
        calls: list[str] = []
        name = path.removeprefix("/")
        srv = start_command_server(
            engine,
            port=port,
            commands={name: lambda n=name: calls.append(n)},
        )
        assert srv is not None
        time.sleep(0.05)
        try:
            code, _ = _post_empty(port, path)
            assert code == 200
            assert calls == [name]
        finally:
            srv.shutdown()
            srv.server_close()

    def test_settings_command_is_404_without_callback(self, server):
        _, port = server
        code, _ = _post_empty(port, "/settings")
        assert code == 404

    def test_json_settings_apply_command_routes_payload(self):
        engine = _FakeEngine()
        port = _free_port()
        calls: list[dict[str, Any]] = []
        srv = start_command_server(
            engine,
            port=port,
            json_commands={
                "settings.apply": lambda data: calls.append(data) or {"ok": True}
            },
        )
        assert srv is not None
        time.sleep(0.05)
        try:
            code, body = _post(port, "/settings/apply", {"values": {"speed": 1.2}})
            assert code == 200
            assert calls == [{"values": {"speed": 1.2}}]
            assert json.loads(body) == {"ok": True}
        finally:
            srv.shutdown()
            srv.server_close()

    def test_json_settings_apply_is_404_without_callback(self, server):
        _, port = server
        code, _ = _post(port, "/settings/apply", {"values": {}})
        assert code == 404

    @pytest.mark.parametrize(
        ("path", "name"),
        [
            ("/ui/click", "ui.click"),
            ("/ui/type", "ui.type"),
            ("/ui/set", "ui.set"),
            ("/ui/select", "ui.select"),
            ("/ui/overlay-click", "ui.overlay_click"),
        ],
    )
    def test_ui_json_commands_route_payload(self, path: str, name: str):
        engine = _FakeEngine()
        port = _free_port()
        calls: list[tuple[str, dict[str, Any]]] = []
        srv = start_command_server(
            engine,
            port=port,
            json_commands={
                name: lambda data, n=name: calls.append((n, data)) or {"ok": True}
            },
        )
        assert srv is not None
        time.sleep(0.05)
        try:
            code, body = _post(path=path, port=port, body={"target": "x"})
            assert code == 200
            assert calls == [(name, {"target": "x"})]
            assert json.loads(body) == {"ok": True}
        finally:
            srv.shutdown()
            srv.server_close()

    @pytest.mark.parametrize(
        "path",
        ["/ui/click", "/ui/type", "/ui/set", "/ui/select", "/ui/overlay-click"],
    )
    def test_ui_json_commands_are_404_without_callback(self, path: str, server):
        _, port = server
        code, _ = _post(port, path, {"target": "x"})
        assert code == 404

    def test_state_query_returns_json_payload(self):
        engine = _FakeEngine()
        port = _free_port()
        srv = start_command_server(
            engine,
            port=port,
            queries={"state": lambda: {"settings_open": True}},
        )
        assert srv is not None
        time.sleep(0.05)
        try:
            code, body = _get(port, "/state")
            assert code == 200
            assert json.loads(body) == {"settings_open": True}
        finally:
            srv.shutdown()
            srv.server_close()

    def test_state_query_is_404_without_callback(self, server):
        _, port = server
        code, _ = _get(port, "/state")
        assert code == 404

    def test_allowed_extensions_constant(self):
        # Sanity check the constant is in sync with the docstring.
        for ext in ALLOWED_EXTENSIONS:
            assert ext.startswith(".") and ext == ext.lower()

    def test_start_returns_none_when_port_is_already_bound(self):
        engine = _FakeEngine()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]

            assert start_command_server(engine, port=port) is None
