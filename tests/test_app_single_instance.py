from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest

from pippal import app


class _Root:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class _AppRoot(_Root):
    def __init__(self) -> None:
        super().__init__()
        self.after_calls: list[tuple[int, Callable[..., object], tuple[object, ...]]] = []
        self.mainloop_entered = False

    def withdraw(self) -> None:
        return None

    def after(self, delay_ms: int, callback: Callable[..., object], *args: object) -> None:
        self.after_calls.append((delay_ms, callback, args))

    def mainloop(self) -> None:
        self.mainloop_entered = True


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


def test_e2e_command_server_gate_requires_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PIPPAL_E2E_COMMAND_SERVER", raising=False)
    assert app._e2e_command_server_enabled() is False

    monkeypatch.setenv("PIPPAL_E2E_COMMAND_SERVER", "1")
    assert app._e2e_command_server_enabled() is True


def test_require_command_server_passes_control_route_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = object()
    root = _Root()
    captured: dict[str, object] = {}

    def fake_start_command_server(_engine: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return server

    monkeypatch.setattr(app, "start_command_server", fake_start_command_server)

    assert (
        app._require_command_server(
            object(),
            root,
            commands={},
            json_commands={},
            queries={},
            control_routes_enabled=True,
        )
        is server
    )
    assert captured["control_routes_enabled"] is True
    assert root.destroyed is False


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


def test_missing_selected_piper_starts_repairable_app_surfaces(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import pippal.hotkey as hotkey

    root = _AppRoot()
    missing_piper = tmp_path / "missing" / "piper.exe"
    events: list[str] = []

    class _FakeMenuItem:
        def __init__(self, text: str, *_args: object, **_kwargs: object) -> None:
            self.text = text

    class _FakeMenu:
        SEPARATOR = object()

        def __init__(self, *items: object) -> None:
            self.items = items

    class _FakeIcon:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            events.append("icon-created")

        def run_detached(self) -> None:
            events.append("tray-started")

        def stop(self) -> None:
            events.append("tray-stopped")

    def fake_start_command_server(_engine: object, **_kwargs: object) -> object:
        events.append("command-server-started")
        return object()

    class _FakeLock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_exc: object) -> None:
            return None

    class _FakeHotkeyManager:
        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def unregister_all(self) -> None:
            return None

        def register(self, *_args: object) -> None:
            return None

        def failures(self) -> list[tuple[str, str]]:
            return []

    def noop(*_args: object, **_kwargs: object) -> None:
        return None

    def fake_engine(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            lock=_FakeLock(),
            is_speaking=False,
            _backend_name=None,
            _backend_cls=None,
            _chunks=[],
            _chunk_idx=0,
            _chunk_paths=[],
            _is_paused=False,
            _queue=[],
            token=0,
            attach_history=noop,
            get_history=lambda: [],
            clear_history=noop,
            stop=noop,
            pause_toggle=noop,
            prev_chunk=noop,
            replay_chunk=noop,
            next_chunk=noop,
            speak_selection_async=noop,
            queue_selection_async=noop,
            read_text_async=noop,
            dispatch_plugin_action=noop,
            reset_backend=noop,
        )

    def fake_overlay(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            win=SimpleNamespace(winfo_viewable=lambda: False),
            state="hidden",
            _btn_rects={},
            action_label="",
            message="",
        )

    def fake_settings_window(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            vars={},
            win=None,
            open=noop,
            _open_voice_manager=noop,
            _on_engine_change=noop,
            _persist=noop,
        )

    monkeypatch.setattr(app, "PIPER_EXE", missing_piper)
    monkeypatch.setattr(app, "ensure_dirs", lambda: None)
    monkeypatch.setattr(app, "load_config", lambda: {"engine": "piper", "brand_name": "PipPal"})
    monkeypatch.setattr(app, "load_history", lambda: [])
    monkeypatch.setattr(app, "save_history", lambda _history: None)
    monkeypatch.setattr(app, "_set_app_user_model_id", lambda: None)
    monkeypatch.setattr(app, "_set_window_icon", lambda _root: None)
    monkeypatch.setattr(app.tk, "Tk", lambda: root)
    monkeypatch.setattr(app, "TTSEngine", fake_engine)
    monkeypatch.setattr(app, "Overlay", fake_overlay)
    monkeypatch.setattr(app, "SettingsWindow", fake_settings_window)
    monkeypatch.setattr(app, "start_command_server", fake_start_command_server)
    monkeypatch.setattr(app, "should_show_activation_panel", lambda: False)
    monkeypatch.setattr(app, "make_tray_icon", lambda _speaking: object())
    monkeypatch.setattr(app.plugins, "tray_items", lambda: [])
    monkeypatch.setattr(app.plugins, "hotkey_actions", lambda: [])
    monkeypatch.setattr(app.pystray, "MenuItem", _FakeMenuItem)
    monkeypatch.setattr(app.pystray, "Menu", _FakeMenu)
    monkeypatch.setattr(app.pystray, "Icon", _FakeIcon)
    monkeypatch.setattr(hotkey, "HotkeyManager", _FakeHotkeyManager)
    monkeypatch.setattr(hotkey, "duplicate_combo_failures", lambda *_args: [])

    app.main()

    captured = capsys.readouterr()
    assert "piper.exe missing" in captured.err
    assert "Starting repair state" in captured.err
    assert root.mainloop_entered is True
    assert "command-server-started" in events
    assert "tray-started" in events
    assert any(
        delay_ms == 500 and callback.__name__ == "open_activation_panel"
        for delay_ms, callback, _args in root.after_calls
    )
