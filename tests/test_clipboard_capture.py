"""Pure-logic tests for ``pippal.clipboard_capture``.

The full ``capture_selection`` dance involves the system clipboard,
synthetic Ctrl+C, and a polling loop — there are integration-flavoured
tests for that in ``test_engine.py`` (which mocks ``keyboard`` and
``pyperclip``). What lives here are the small string-parsing and
registry-lookup helpers that don't need any of that mocking."""

from __future__ import annotations

from pippal import clipboard_capture, plugins


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
        # capture_for_action fallback so a Pro-only action still
        # captures (with an empty release set) when Pro is absent.
        assert clipboard_capture._config_key_for("nope") == ""
