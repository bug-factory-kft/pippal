from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import pytest

from pippal import onboarding
from pippal.ui import activation_panel, voice_manager
from pippal.voices import voice_filename, voice_url_base


class _FakeStringVar:
    def __init__(self, *, master: object | None = None, value: str = "") -> None:
        self.master = master
        self.value = value

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _FakeWidget:
    def __init__(self, parent: _FakeWidget | None = None, **kwargs: object) -> None:
        self.parent = parent
        self.children: list[_FakeWidget] = []
        self.destroyed = False
        self.options = dict(kwargs)
        if parent is not None:
            parent.children.append(self)

    def pack(self, **kwargs: object) -> None:
        self.options["pack"] = kwargs

    def winfo_children(self) -> list[_FakeWidget]:
        return [child for child in self.children if not child.destroyed]

    def winfo_exists(self) -> bool:
        return not self.destroyed

    def destroy(self) -> None:
        self.destroyed = True
        for child in self.children:
            child.destroy()


class _FakeFrame(_FakeWidget):
    pass


class _FakeLabel(_FakeWidget):
    pass


class _FakeButton(_FakeWidget):
    created: ClassVar[list[_FakeButton]] = []

    def __init__(
        self,
        parent: _FakeWidget | None = None,
        *,
        text: str = "",
        command: Callable[[], object] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(parent, text=text, command=command, **kwargs)
        self.text = text
        self.command = command
        self.state = "normal"
        self.created.append(self)

    def config(self, **kwargs: object) -> None:
        self.options.update(kwargs)
        if "state" in kwargs:
            self.state = str(kwargs["state"])

    def invoke(self) -> object | None:
        if self.state == "disabled":
            raise AssertionError(f"button is disabled: {self.text}")
        if self.command is None:
            return None
        return self.command()


class _FakeText(_FakeWidget):
    def __init__(self, parent: _FakeWidget | None = None, **kwargs: object) -> None:
        super().__init__(parent, **kwargs)
        self.content = ""

    def insert(self, _index: str, text: str) -> None:
        self.content += text


class _FakeWindow(_FakeWidget):
    def __init__(self, _root: object) -> None:
        super().__init__(None)
        self.window_title = ""
        self.geometry_value = ""

    def title(self, value: str) -> None:
        self.window_title = value

    def resizable(self, *_args: object) -> None:
        return None

    def protocol(self, *_args: object) -> None:
        return None

    def deiconify(self) -> None:
        return None

    def lift(self) -> None:
        return None

    def focus_force(self) -> None:
        return None

    def update_idletasks(self) -> None:
        return None

    def winfo_reqwidth(self) -> int:
        return 500

    def winfo_reqheight(self) -> int:
        return 320

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def geometry(self, value: str) -> None:
        self.geometry_value = value


class _FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, Callable[..., object], tuple[object, ...]]] = []
        self.cancelled_after_ids: list[str] = []

    def after(self, delay_ms: int, callback: Callable[..., object], *args: object) -> str:
        self.after_calls.append((delay_ms, callback, args))
        after_id = f"after-{len(self.after_calls)}"
        if delay_ms == 0:
            callback(*args)
        return after_id

    def after_cancel(self, after_id: str) -> None:
        self.cancelled_after_ids.append(after_id)


class _ImmediateThread:
    def __init__(self, *, target: Callable[[], object], daemon: bool) -> None:
        self.target = target
        self.daemon = daemon

    def start(self) -> None:
        self.target()


def _install_headless_tk(monkeypatch: pytest.MonkeyPatch) -> list[_FakeButton]:
    _FakeButton.created = []

    def fake_make_card(parent: _FakeWidget, _title: str | None = None) -> tuple[_FakeFrame, _FakeFrame]:
        outer = _FakeFrame(parent)
        card = _FakeFrame(outer)
        return outer, card

    monkeypatch.setattr(activation_panel.tk, "StringVar", _FakeStringVar)
    monkeypatch.setattr(activation_panel.tk, "Toplevel", _FakeWindow)
    monkeypatch.setattr(activation_panel.tk, "Text", _FakeText)
    monkeypatch.setattr(activation_panel.ttk, "Frame", _FakeFrame)
    monkeypatch.setattr(activation_panel.ttk, "Label", _FakeLabel)
    monkeypatch.setattr(activation_panel.ttk, "Button", _FakeButton)
    monkeypatch.setattr(activation_panel, "apply_dark_theme", lambda _window: None)
    monkeypatch.setattr(activation_panel, "make_card", fake_make_card)
    monkeypatch.setattr(activation_panel.threading, "Thread", _ImmediateThread)
    return _FakeButton.created


def _button(buttons: list[_FakeButton], text: str) -> _FakeButton:
    for button in reversed(buttons):
        if button.text == text and not button.destroyed:
            return button
    raise AssertionError(f"missing visible button: {text}")


def test_first_run_activation_click_through_installs_default_voice_and_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buttons = _install_headless_tk(monkeypatch)
    piper_exe = tmp_path / "piper.exe"
    piper_exe.write_bytes(b"exe")
    voices_dir = tmp_path / "voices"
    state_path = tmp_path / "first_run_activation.json"
    config = {
        "engine": "piper",
        "voice": "en_US-ryan-high.onnx",
        "hotkey_speak": "windows+shift+r",
    }
    downloaded: list[tuple[str, str]] = []

    def fake_download(url: str, dest: Path) -> None:
        downloaded.append((url, dest.name))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f"downloaded:{dest.name}".encode())

    def fake_install_default_voice(voice: dict[str, str]) -> str:
        return voice_manager.install_piper_voice(
            voice,
            voices_dir=voices_dir,
            streaming_download=fake_download,
        )

    def build_readiness(config_values: dict[str, Any]) -> onboarding.FirstRunReadiness:
        return onboarding.build_activation_readiness(
            config_values,
            piper_exe=piper_exe,
            voices_dir=voices_dir,
        )

    monkeypatch.setattr(activation_panel, "install_piper_voice", fake_install_default_voice)
    monkeypatch.setattr(activation_panel, "build_activation_readiness", build_readiness)
    monkeypatch.setattr(
        activation_panel,
        "load_activation_state",
        lambda: onboarding.load_activation_state(path=state_path),
    )
    monkeypatch.setattr(
        activation_panel,
        "mark_activation_complete",
        lambda method: onboarding.mark_activation_complete(
            method,
            path=state_path,
            completed_at="2026-05-14T00:00:00Z",
        ),
    )

    played_samples: list[str] = []
    panel = activation_panel.FirstRunActivationPanel(
        _FakeRoot(),
        config,
        on_play_sample=played_samples.append,
        on_open_settings=lambda: None,
        on_open_voice_manager=lambda: None,
        on_open_setup=lambda: None,
    )

    panel.open()

    assert panel._status_var.get().startswith("No local voice is installed yet.")

    _button(buttons, "Install default voice").invoke()

    default_voice = activation_panel.default_piper_voice()
    default_filename = voice_filename(default_voice)
    default_base_url = voice_url_base(default_voice)
    assert downloaded == [
        (default_base_url + default_filename, f"{default_filename}.part"),
        (default_base_url + f"{default_filename}.json", f"{default_filename}.json.part"),
    ]
    assert (voices_dir / default_filename).is_file()
    assert (voices_dir / f"{default_filename}.json").is_file()
    assert list(voices_dir.glob("*.part")) == []
    assert config["voice"] == default_filename
    assert panel._status_var.get().startswith("Default English voice installed")

    _button(buttons, "Play sample").invoke()

    assert played_samples == [onboarding.activation_sample_text("Win+Shift+R")]
    assert panel._status_var.get() == "Playing sample..."

    _button(buttons, "Yes, continue").invoke()

    activation_state = onboarding.load_activation_state(path=state_path)
    assert activation_state.completed_with == "sample"
    assert activation_state.completed_at == "2026-05-14T00:00:00Z"
    assert activation_state.last_failure is None
    assert panel._status_var.get() == "Done. PipPal can read selected text on this PC."


def test_missing_piper_repair_state_actions_are_reachable_without_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buttons = _install_headless_tk(monkeypatch)
    missing_piper = tmp_path / "missing" / "piper.exe"
    voices_dir = tmp_path / "voices"
    config = {
        "engine": "piper",
        "voice": "en_US-ryan-high.onnx",
        "hotkey_speak": "windows+shift+r",
    }
    opened: list[str] = []

    def build_readiness(config_values: dict[str, Any]) -> onboarding.FirstRunReadiness:
        return onboarding.build_activation_readiness(
            config_values,
            piper_exe=missing_piper,
            voices_dir=voices_dir,
        )

    monkeypatch.setattr(activation_panel, "build_activation_readiness", build_readiness)
    monkeypatch.setattr(activation_panel, "load_activation_state", onboarding.load_activation_state)

    panel = activation_panel.FirstRunActivationPanel(
        _FakeRoot(),
        config,
        on_play_sample=lambda _text: opened.append("sample"),
        on_open_settings=lambda: opened.append("settings"),
        on_open_voice_manager=lambda: opened.append("voice-manager"),
        on_open_setup=lambda: opened.append("setup"),
    )

    panel.open()

    assert panel.win is not None
    assert panel.win.winfo_exists()
    assert panel._status_var.get().startswith("The local Piper engine is missing.")

    _button(buttons, "Open setup instructions").invoke()
    _button(buttons, "Open Settings").invoke()

    assert opened == ["setup", "settings"]
    assert panel.win.winfo_exists()
