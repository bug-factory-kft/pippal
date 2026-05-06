"""Benchmarks for ``pippal.hotkey``.

The dispatcher runs on Windows' low-level keyboard hook thread.
Hooks that take longer than ``LowLevelHooksTimeout`` (default 1 s)
get silently uninstalled by the OS, so we want hard data on how
fast the hot path really is. The numbers below should be in the
single-digit microseconds on modern hardware; if a benchmark drifts
into hundreds of microseconds, something has gone wrong."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pippal import hotkey

pytestmark = pytest.mark.benchmark(group="hotkey")


def _ev(name: str, event_type: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, event_type=event_type)


def test_parse_combo(benchmark):
    benchmark(hotkey.parse_combo, "windows+shift+r")


def test_normalise_key(benchmark):
    benchmark(hotkey._normalise_key, "left ctrl")


def test_dispatch_pass_through(benchmark):
    """Most keystrokes go straight through — this is the fast path
    that runs on every key event for a user not using PipPal hotkeys."""
    m = hotkey.HotkeyManager()
    m._started = True
    m.register("windows+shift+r", lambda: None)

    with patch.object(hotkey, "_physical_modifiers",
                       return_value=frozenset()):
        benchmark(m._on_event, _ev("a", "down"))


def test_dispatch_match_and_suppress(benchmark):
    """The slow path: matched combo, schedule callback, return False
    to suppress. Includes the ``threading.Thread.start`` call, which
    is the most expensive step. (We can't easily exclude it without
    breaking the dispatcher API.)"""
    m = hotkey.HotkeyManager()
    m._started = True
    m.register("windows+shift+r", lambda: None)

    with patch.object(hotkey, "_physical_modifiers",
                       return_value=frozenset({"win", "shift"})):
        # Each iteration treats the trigger as a fresh first-down by
        # clearing the held-key set so we always exercise the matching
        # path, not the repeat-suppress path.
        def run():
            m._held_non_mod.clear()
            m._suppressed_non_mod.clear()
            return m._on_event(_ev("r", "down"))
        benchmark(run)


def test_dispatch_repeat_suppress(benchmark):
    """The repeat path — held trigger key. Cheaper than first-press
    because it skips the modifier query and the dict lookup."""
    m = hotkey.HotkeyManager()
    m._started = True
    m.register("windows+shift+r", lambda: None)
    # Prime the held set so the first event in the benchmark is a
    # repeat from the dispatcher's perspective.
    m._held_non_mod.add("r")
    m._suppressed_non_mod.add("r")

    with patch.object(hotkey, "_physical_modifiers",
                       return_value=frozenset({"win", "shift"})):
        benchmark(m._on_event, _ev("r", "down"))
