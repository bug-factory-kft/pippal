from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest

from pippal.ui import settings_window
from pippal.ui.settings_window import SettingsWindow


class _FakeWindow:
    def __init__(self, name: str) -> None:
        self.name = name
        self.map_callback: Callable[[Any], None] | None = None
        self.after_callback: Callable[[Any], None] | None = None

    def bind(self, sequence: str, callback: Callable[[Any], None]) -> None:
        if sequence == "<Map>":
            self.map_callback = callback

    def after(self, _delay_ms: int, callback: Callable[[Any], None]) -> None:
        self.after_callback = callback

    def fire_map(self) -> None:
        assert self.map_callback is not None
        self.map_callback(None)

    def fire_after(self) -> None:
        assert self.after_callback is not None
        self.after_callback(None)


def test_settings_chromeless_guard_is_per_toplevel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        settings_window.theme,
        "make_chromeless_keep_taskbar",
        lambda window: calls.append(("chromeless", window.name)),
    )
    monkeypatch.setattr(
        settings_window.theme,
        "apply_rounded_corners",
        lambda window: calls.append(("rounded", window.name)),
    )

    sw = object.__new__(SettingsWindow)
    first = _FakeWindow("first")
    second = _FakeWindow("second")

    sw._install_chromeless_handlers(cast(Any, first))
    first.fire_map()
    first.fire_after()
    first.fire_map()

    sw._install_chromeless_handlers(cast(Any, second))
    second.fire_after()
    second.fire_map()

    assert calls == [
        ("chromeless", "first"),
        ("rounded", "first"),
        ("chromeless", "second"),
        ("rounded", "second"),
    ]
    assert not hasattr(sw, "_did_chromeless")
