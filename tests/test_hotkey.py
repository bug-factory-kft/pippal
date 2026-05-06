"""Pure-logic tests for ``pippal.hotkey``.

The HotkeyManager's ``start()`` installs a real Windows low-level
keyboard hook through the `keyboard` library, so we don't exercise
that path here. Instead we drive the dispatcher directly:

- ``parse_combo`` is a string parser, easy to test.
- ``_on_event`` is the matcher; we feed it synthetic events and patch
  ``_physical_modifiers`` so the modifier state is deterministic
  regardless of what's actually held on the test machine.

Bug-history this exists to pin:

- Stale modifier cache after a UAC / secure-desktop transition used
  to make plain trigger letters complete a ghost combo. Fix: read
  modifiers from the OS at match time, not from a hook-event cache.
- Key-repeat (Windows fires ``down`` every ~30 ms while a key is
  held) used to refire the handler on every repeat. Fix: track each
  non-modifier key between its first ``down`` and its ``up``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from pippal import hotkey

# ---------------------------------------------------------------------------
# parse_combo
# ---------------------------------------------------------------------------

class TestParseCombo:
    def test_valid_combo(self):
        assert hotkey.parse_combo("windows+shift+r") == (
            frozenset({"win", "shift"}), "r",
        )

    def test_modifier_aliases(self):
        # `control`, `super`, `windows` all normalise.
        assert hotkey.parse_combo("control+r") == (frozenset({"ctrl"}), "r")
        assert hotkey.parse_combo("super+a") == (frozenset({"win"}), "a")
        assert hotkey.parse_combo("left ctrl+x") == (frozenset({"ctrl"}), "x")

    def test_modifier_order_independent(self):
        a = hotkey.parse_combo("ctrl+shift+a")
        b = hotkey.parse_combo("shift+ctrl+a")
        assert a == b

    def test_case_insensitive(self):
        assert hotkey.parse_combo("WINDOWS+Shift+R") == (
            frozenset({"win", "shift"}), "r",
        )

    def test_no_trigger_returns_none(self):
        # All modifiers, no trigger key — was the original "returns None"
        # path.
        assert hotkey.parse_combo("ctrl+shift") is None

    def test_multiple_triggers_returns_none(self):
        # Was a silent bug: kept the last trigger and bound a different
        # combo than the user typed.
        assert hotkey.parse_combo("ctrl+a+b") is None

    def test_empty_returns_none(self):
        assert hotkey.parse_combo("") is None
        assert hotkey.parse_combo("   ") is None
        assert hotkey.parse_combo(None) is None  # type: ignore[arg-type]

    def test_trigger_only(self):
        assert hotkey.parse_combo("space") == (frozenset(), "space")


# ---------------------------------------------------------------------------
# _on_event dispatcher
# ---------------------------------------------------------------------------

def _ev(name: str, event_type: str) -> SimpleNamespace:
    """Build a minimal keyboard-lib event."""
    return SimpleNamespace(name=name, event_type=event_type)


def _ready_manager() -> hotkey.HotkeyManager:
    """A HotkeyManager with the started flag flipped so register()
    works without actually installing a hook. The dispatcher reads
    the handler dict directly so we can drive _on_event from a test."""
    m = hotkey.HotkeyManager()
    m._started = True
    return m


class TestOnEventMatching:
    def test_passes_through_unrelated_keystrokes(self):
        m = _ready_manager()
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset()):
            assert m._on_event(_ev("a", "down")) is True

    def test_suppresses_only_exact_combo(self):
        m = _ready_manager()
        called = []
        m.register("windows+shift+r", lambda: called.append(1))
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset({"win", "shift"})):
            # Win+Shift+R should suppress and dispatch.
            assert m._on_event(_ev("r", "down")) is False
        # Handler runs on a daemon thread; give it a heartbeat.
        import time
        time.sleep(0.05)
        assert called == [1]

    def test_does_not_suppress_when_only_some_modifiers_held(self):
        # Win+Shift+S (not registered) used to be eaten by the old
        # `keyboard.add_hotkey(suppress=True)` because of partial-prefix
        # matching. The new dispatcher must let it through.
        m = _ready_manager()
        m.register("windows+shift+r", lambda: None)
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset({"win", "shift"})):
            # `s` isn't our trigger — must pass through to the OS.
            assert m._on_event(_ev("s", "down")) is True

    def test_modifier_events_pass_through(self):
        m = _ready_manager()
        m.register("windows+shift+r", lambda: None)
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset()):
            assert m._on_event(_ev("shift", "down")) is True
            assert m._on_event(_ev("shift", "up")) is True
            assert m._on_event(_ev("win", "down")) is True


class TestOnEventKeyRepeat:
    def test_handler_fires_once_for_held_key(self):
        # Holding Win+Shift+R produces "down" every ~30 ms. The
        # handler must run only on the first one — repeats keep the
        # OS-side suppression consistent but don't re-spawn worker
        # threads.
        m = _ready_manager()
        called = []
        m.register("windows+shift+r", lambda: called.append(1))
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset({"win", "shift"})):
            assert m._on_event(_ev("r", "down")) is False  # first
            assert m._on_event(_ev("r", "down")) is False  # repeat
            assert m._on_event(_ev("r", "down")) is False  # repeat
        import time
        time.sleep(0.05)
        assert called == [1], "handler should fire exactly once per press"

    def test_up_clears_repeat_state(self):
        m = _ready_manager()
        called = []
        m.register("windows+shift+r", lambda: called.append(1))
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset({"win", "shift"})):
            m._on_event(_ev("r", "down"))
            m._on_event(_ev("r", "up"))
            m._on_event(_ev("r", "down"))  # second physical press
        import time
        time.sleep(0.05)
        assert called == [1, 1]

    def test_unmatched_repeat_passes_through_consistently(self):
        # Holding a non-combo key: the first event passes through,
        # subsequent repeats must also pass through (consistency
        # is what avoids surprising behaviour for the foreground app).
        m = _ready_manager()
        m.register("windows+shift+r", lambda: None)
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset()):
            assert m._on_event(_ev("a", "down")) is True
            assert m._on_event(_ev("a", "down")) is True
            assert m._on_event(_ev("a", "down")) is True


class TestOnEventStaleModifierFix:
    def test_dispatcher_trusts_GetAsyncKeyState_not_event_history(self):
        # Repro for the UAC / secure-desktop bug: the LL hook can miss
        # a modifier `up` while another desktop is active. With the
        # earlier event-cache implementation, the next plain trigger
        # letter would complete a ghost combo. The current dispatcher
        # reads modifier state from `GetAsyncKeyState` at match time,
        # so simulating "no modifiers held" must NOT trigger the
        # registered Win+Shift+R handler even after we feed the hook
        # plenty of stale modifier `down` events.
        m = _ready_manager()
        called = []
        m.register("windows+shift+r", lambda: called.append(1))
        # Simulate a sequence of modifier-down events the OS would
        # have replayed — these should be no-ops for the dispatcher
        # because `_on_event` doesn't track modifiers itself.
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset()):
            m._on_event(_ev("win", "down"))
            m._on_event(_ev("shift", "down"))
            # User releases physically while the hook is suspended,
            # then types plain `r`. `_physical_modifiers` (mocked
            # here) reports the truth: nothing held.
            assert m._on_event(_ev("r", "down")) is True
        import time
        time.sleep(0.05)
        assert called == [], "ghost-modifier match must not fire"


# ---------------------------------------------------------------------------
# register / unregister / failures
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_returns_false_when_unparseable(self):
        m = _ready_manager()
        assert m.register("ctrl+shift", lambda: None) is False  # no trigger

    def test_register_returns_false_when_hook_not_started(self):
        m = hotkey.HotkeyManager()  # _started stays False
        assert m.register("windows+shift+r", lambda: None) is False
        # And the failure is surfaced through `failures()`.
        fails = m.failures()
        assert any(reason == "hook not running" for _combo, reason in fails)

    def test_re_registering_replaces_callback(self):
        m = _ready_manager()
        first = []
        second = []
        m.register("windows+shift+r", lambda: first.append(1))
        m.register("windows+shift+r", lambda: second.append(1))
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset({"win", "shift"})):
            m._on_event(_ev("r", "down"))
        import time
        time.sleep(0.05)
        assert first == []
        assert second == [1]

    def test_unregister_all_drops_handlers(self):
        m = _ready_manager()
        called = []
        m.register("windows+shift+r", lambda: called.append(1))
        m.unregister_all()
        with patch.object(hotkey, "_physical_modifiers",
                           return_value=frozenset({"win", "shift"})):
            assert m._on_event(_ev("r", "down")) is True  # not ours anymore
        import time
        time.sleep(0.05)
        assert called == []

    def test_failures_drained_on_read(self):
        m = hotkey.HotkeyManager()
        m.register("oops", lambda: None)        # unparseable
        m.register("ctrl+shift", lambda: None)  # unparseable
        first = m.failures()
        assert len(first) == 2
        assert m.failures() == [], "failures() must drain the buffer"


class TestNormaliseAndIsModifier:
    def test_modifier_recognition(self):
        for name in ("ctrl", "shift", "alt", "win"):
            assert hotkey._is_modifier(name) is True
        for name in ("a", "r", "space", "f1", ""):
            assert hotkey._is_modifier(name) is False

    def test_normalise_aliases(self):
        assert hotkey._normalise_key("Left Ctrl") == "ctrl"
        assert hotkey._normalise_key("WINDOWS") == "win"
        assert hotkey._normalise_key("super") == "win"
        assert hotkey._normalise_key("") == ""
        # Non-modifier passes through lowercased.
        assert hotkey._normalise_key("R") == "r"
        assert hotkey._normalise_key("F1") == "f1"
