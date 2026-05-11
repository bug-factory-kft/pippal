from __future__ import annotations

import pytest

from pippal import app


class _Root:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


def test_require_command_server_returns_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    server = object()
    root = _Root()
    messages: list[str] = []

    monkeypatch.setattr(app, "start_command_server", lambda _engine: server)
    monkeypatch.setattr(
        app, "_show_already_running_message", lambda: messages.append("shown")
    )

    assert app._require_command_server(object(), root) is server
    assert root.destroyed is False
    assert messages == []


def test_require_command_server_exits_before_app_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _Root()
    messages: list[str] = []

    monkeypatch.setattr(app, "start_command_server", lambda _engine: None)
    monkeypatch.setattr(
        app, "_show_already_running_message", lambda: messages.append("shown")
    )

    with pytest.raises(SystemExit) as exc:
        app._require_command_server(object(), root)

    assert exc.value.code == 0
    assert root.destroyed is True
    assert messages == ["shown"]
