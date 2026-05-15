from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest

from pippal.ui import settings_window
from pippal.ui.settings_window import SettingsWindow


class _FakeWindow:
    def __init__(self, name: str) -> None:
        self.name = name
        self.after_idle_callback: Callable[[], None] | None = None

    def after_idle(self, callback: Callable[[], None]) -> None:
        self.after_idle_callback = callback

    def winfo_exists(self) -> bool:
        return True

    def fire_after_idle(self) -> None:
        assert self.after_idle_callback is not None
        self.after_idle_callback()


def test_native_dialog_frame_refreshes_rounded_corners_without_chromeless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        settings_window.theme,
        "apply_rounded_corners",
        lambda window: calls.append(window.name),
    )

    window = _FakeWindow("settings")

    settings_window.theme.apply_native_dialog_frame(window)
    window.fire_after_idle()

    assert calls == ["settings", "settings"]


def test_open_voice_manager_passes_first_run_install_callback_without_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeVoiceManagerDialog:
        def __init__(
            self,
            parent: object,
            *,
            on_changed: Callable[[], None],
            on_installed: Callable[[str], None] | None = None,
        ) -> None:
            captured["parent"] = parent
            captured["on_changed"] = on_changed
            captured["on_installed"] = on_installed

    monkeypatch.setattr(settings_window, "VoiceManagerDialog", FakeVoiceManagerDialog)

    class VoiceManagerParent:
        def after(self, delay_ms: int, callback: Callable[[], None]) -> None:
            captured["delay_ms"] = delay_ms
            callback()

        def winfo_exists(self) -> bool:
            return True

    settings = cast(Any, object.__new__(SettingsWindow))
    settings.win = VoiceManagerParent()
    settings._refresh_voice_list = lambda: captured.setdefault("refreshed", True)
    installed: list[str] = []

    settings._open_voice_manager(on_installed=installed.append)

    assert captured["parent"] is settings.win
    assert captured["delay_ms"] == 120
    captured["on_changed"]()
    captured["on_installed"]("en_US-ryan-high.onnx")
    assert captured["refreshed"] is True
    assert installed == ["en_US-ryan-high.onnx"]
