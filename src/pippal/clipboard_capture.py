"""Selection capture via the system clipboard.

`capture_selection` saves the current clipboard, sends Ctrl+C to the
foreground app, reads what it produced, and restores the original
clipboard. Two near-simultaneous hotkey actions cannot interleave
their probes — `capture_selection` holds a per-engine lock for the
entire dance."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pyperclip

# `keyboard` is a Windows-only runtime dep — its Linux backend tries
# to grab the X DISPLAY (or read /dev/input/event*, requiring root)
# at import time. PipPal never runs on Linux outside CI; soft-import
# here so module collection works on a headless runner. Tests that
# exercise the keyboard surface patch this attribute, so a None
# fallback is fine for CI.
try:
    import keyboard  # type: ignore[import-untyped]
except Exception:
    keyboard = None  # type: ignore[assignment]

from . import plugins
from .timing import (
    CLIPBOARD_POLL_S,
    CLIPBOARD_READ_DEADLINE_S,
    CLIPBOARD_RELEASE_GAP_S,
)

if TYPE_CHECKING:  # pragma: no cover
    from .engine import TTSEngine

CLIPBOARD_PROBE_TOKEN: str = "__pippal_no_selection__"
UNIVERSAL_MODIFIER_KEYS: set[str] = {"ctrl", "shift", "alt", "super", "windows"}

__all__ = ["CLIPBOARD_PROBE_TOKEN",
           "capture_for_action", "capture_selection"]


def _config_key_for(action: str) -> str:
    """Look up the config-key for an action_id by walking the registry.
    Returns an empty string if the action isn't registered (core build
    that doesn't include AI actions, or unknown action)."""
    for action_id, config_key, _label, _default in plugins.hotkey_actions():
        if action_id == action:
            return config_key
    return ""


def _hotkey_keys(combo: str) -> set[str]:
    """Split a `ctrl+shift+x`-style combo into its individual keys."""
    return {p.strip().lower() for p in (combo or "").split("+") if p.strip()}


def _keyboard_key_is_pressed(key: str) -> bool:
    if keyboard is None:
        return False
    try:
        return bool(keyboard.is_pressed(key))
    except Exception:
        return False


def _release_keyboard_key(key: str) -> None:
    if keyboard is None:
        return
    try:
        keyboard.release(key)
    except Exception:
        pass


def _release_copy_hotkey_keys(hotkey_combo: str) -> None:
    combo_keys = _hotkey_keys(hotkey_combo)
    release_keys = set(combo_keys)
    release_keys.update(
        key for key in UNIVERSAL_MODIFIER_KEYS
        if key not in combo_keys and _keyboard_key_is_pressed(key)
    )
    for key in release_keys:
        _release_keyboard_key(key)


def capture_selection(engine: TTSEngine, hotkey_combo: str = "") -> str:
    """Save clipboard, send Ctrl+C, read clipboard, restore. Serialised
    across hotkey actions via `engine._capture_lock`."""
    with engine._capture_lock:
        saved = ""
        try:
            saved = pyperclip.paste()
        except Exception:
            pass
        try:
            pyperclip.copy(CLIPBOARD_PROBE_TOKEN)
        except Exception:
            pass

        # Release the actual configured combo plus the universal modifier
        # keys that are truly down so a held shortcut doesn't garble Ctrl+C.
        _release_copy_hotkey_keys(hotkey_combo)
        time.sleep(CLIPBOARD_RELEASE_GAP_S)
        try:
            keyboard.send("ctrl+c")
        except Exception:
            pass

        text = ""
        deadline = time.time() + CLIPBOARD_READ_DEADLINE_S
        while time.time() < deadline:
            try:
                cur = pyperclip.paste()
            except Exception:
                cur = CLIPBOARD_PROBE_TOKEN
            if cur != CLIPBOARD_PROBE_TOKEN:
                text = cur
                break
            time.sleep(CLIPBOARD_POLL_S)

        try:
            pyperclip.copy(saved)
        except Exception:
            pass
        return (text or "").strip()


def capture_for_action(engine: TTSEngine, action: str) -> str:
    """`capture_selection` with the configured hotkey combo for `action`,
    so the modifier-release dance covers exactly the right keys."""
    key = _config_key_for(action)
    combo = engine.config.get(key, "") if key else ""
    return capture_selection(engine, combo)
