"""Pure-logic tests for ``pippal.clipboard_capture``.

The full ``capture_selection`` dance involves the system clipboard,
synthetic Ctrl+C, and a polling loop — there are integration-flavoured
tests for that in ``test_engine.py`` (which mocks ``keyboard`` and
``pyperclip``). What lives here are the small string-parsing and
registry-lookup helpers that don't need any of that mocking."""

from __future__ import annotations

import threading

from pippal import clipboard_capture, plugins


class _FakeClipboard:
    def __init__(self, initial: str):
        self.value = initial
        self.copied: list[str] = []

    def paste(self) -> str:
        return self.value

    def copy(self, value: str) -> None:
        self.copied.append(value)
        self.value = value


class _FakeKeyboard:
    def __init__(self, pressed: set[str] | None = None, copied_text: str = ""):
        self.pressed = pressed or set()
        self.copied_text = copied_text
        self.clipboard: _FakeClipboard | None = None
        self.released: list[str] = []
        self.sent: list[str] = []

    def is_pressed(self, key: str) -> bool:
        return key in self.pressed

    def release(self, key: str) -> None:
        self.released.append(key)

    def send(self, hotkey: str) -> None:
        self.sent.append(hotkey)
        if self.clipboard is not None and hotkey == "ctrl+c":
            self.clipboard.value = self.copied_text


class _DummyEngine:
    def __init__(self):
        self._capture_lock = threading.Lock()


class TestHotkeyKeys:
    def test_splits_on_plus(self):
        assert clipboard_capture._hotkey_keys("ctrl+shift+x") == {
            "ctrl", "shift", "x",
        }

    def test_lowercases(self):
        assert clipboard_capture._hotkey_keys("CTRL+Shift+X") == {
            "ctrl", "shift", "x",
        }

    def test_strips_whitespace_around_tokens(self):
        assert clipboard_capture._hotkey_keys("  ctrl + shift + x ") == {
            "ctrl", "shift", "x",
        }

    def test_empty_combo_is_empty_set(self):
        assert clipboard_capture._hotkey_keys("") == set()
        assert clipboard_capture._hotkey_keys(None) == set()  # type: ignore[arg-type]

    def test_drops_empty_tokens(self):
        # Stray double-pluses or trailing pluses shouldn't yield "" keys.
        assert clipboard_capture._hotkey_keys("ctrl++x") == {"ctrl", "x"}
        assert clipboard_capture._hotkey_keys("ctrl+") == {"ctrl"}


class TestReleaseCopyHotkeyKeys:
    def test_releases_configured_combo_keys(self, monkeypatch):
        keyboard = _FakeKeyboard()
        monkeypatch.setattr(clipboard_capture, "keyboard", keyboard)

        clipboard_capture._release_copy_hotkey_keys("windows+shift+r")

        assert {"windows", "shift", "r"} <= set(keyboard.released)

    def test_does_not_release_inactive_universal_alt(self, monkeypatch):
        keyboard = _FakeKeyboard()
        monkeypatch.setattr(clipboard_capture, "keyboard", keyboard)

        clipboard_capture._release_copy_hotkey_keys("windows+shift+r")

        assert "alt" not in keyboard.released

    def test_releases_active_universal_modifier_missing_from_combo(self, monkeypatch):
        keyboard = _FakeKeyboard(pressed={"alt"})
        monkeypatch.setattr(clipboard_capture, "keyboard", keyboard)

        clipboard_capture._release_copy_hotkey_keys("windows+shift+r")

        assert "alt" in keyboard.released


class TestCaptureSelectionCopyInjection:
    def test_injects_ctrl_c_without_inactive_alt_release_and_restores_clipboard(
        self, monkeypatch,
    ):
        clipboard = _FakeClipboard("previous clipboard")
        keyboard = _FakeKeyboard(copied_text=" selected text ")
        keyboard.clipboard = clipboard
        monkeypatch.setattr(clipboard_capture, "pyperclip", clipboard)
        monkeypatch.setattr(clipboard_capture, "keyboard", keyboard)
        monkeypatch.setattr(clipboard_capture.time, "sleep", lambda _delay: None)

        captured = clipboard_capture.capture_selection(
            _DummyEngine(), "windows+shift+r",
        )

        assert captured == "selected text"
        assert keyboard.sent == ["ctrl+c"]
        assert "alt" not in keyboard.released
        assert clipboard.value == "previous clipboard"
        assert clipboard.copied[-1] == "previous clipboard"


class TestConfigKeyFor:
    """`_config_key_for(action)` walks the plugin host's hotkey-action
    registry. ``register_hotkey_action`` writes to both
    ``_hotkey_actions`` and ``_defaults`` (the default combo seeds the
    defaults registry), so snapshot/restore both around each case."""

    def setup_method(self):
        self._snap_actions = list(plugins._hotkey_actions)
        self._snap_defaults = dict(plugins._defaults)
        plugins._hotkey_actions.clear()
        plugins._defaults.clear()

    def teardown_method(self):
        plugins._hotkey_actions.clear()
        plugins._hotkey_actions.extend(self._snap_actions)
        plugins._defaults.clear()
        plugins._defaults.update(self._snap_defaults)

    def test_returns_registered_config_key(self):
        plugins.register_hotkey_action(
            "speak", "hotkey_speak", "Read selection", "ctrl+r",
        )
        assert clipboard_capture._config_key_for("speak") == "hotkey_speak"

    def test_unknown_action_returns_empty_string(self):
        # An unregistered action_id must not raise. Used in the
        # capture_for_action fallback so an extension-only action still
        # captures with an empty release set when that extension is absent.
        assert clipboard_capture._config_key_for("nope") == ""
