"""Tests for PipPalBridge.overlay_action — exercises the bridge dispatch
path directly so that a missing branch raises rather than silently passes.

These tests use a minimal stub engine that only exposes the surface the
bridge calls; no real TTS engine, winsound, or network involved.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pippal.web_ui.bridge import PipPalBridge

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stub_engine(*, is_paused: bool = False) -> MagicMock:
    """Return a minimal engine stub that satisfies the bridge's call sites."""
    engine = MagicMock()
    # Attributes the bridge reads under engine.lock
    engine.is_speaking = False
    engine._is_paused = is_paused
    engine._backend_name = "stub"
    engine._backend_cls = None
    engine._chunks = []
    engine._chunk_paths = []
    engine._queue = []
    # is_paused property — MagicMock needs explicit config for property access
    type(engine).is_paused = property(lambda self: self._is_paused)
    # lock must be a real re-entrant lock so `with engine.lock:` works
    import threading

    engine.lock = threading.Lock()
    return engine


def _make_bridge(engine: Any) -> PipPalBridge:
    return PipPalBridge(engine=engine, config={})


# ---------------------------------------------------------------------------
# overlay_action dispatch tests
# ---------------------------------------------------------------------------


class TestOverlayActionPause:
    """BUG 2 — overlay_action('pause') must invoke engine.pause_toggle()."""

    def test_pause_calls_pause_toggle(self) -> None:
        """RED on unpatched main: overlay_action('pause') raises RuntimeError.

        After fix: returns {"ok": True} and calls pause_toggle once.
        """
        engine = _make_stub_engine()
        bridge = _make_bridge(engine)

        result = bridge.overlay_action("pause")

        assert result == {"ok": True}, "bridge must return {'ok': True} on pause"
        engine.pause_toggle.assert_called_once_with()

    def test_pause_does_not_raise(self) -> None:
        """Regression guard: 'pause' must not raise RuntimeError."""
        engine = _make_stub_engine()
        bridge = _make_bridge(engine)

        # If the 'pause' branch is missing, this raises RuntimeError.
        bridge.overlay_action("pause")  # must not raise

    def test_known_actions_still_work(self) -> None:
        """Existing actions (close/prev/replay/next) must continue to work."""
        for tag, method in [
            ("close", "stop"),
            ("prev", "prev_chunk"),
            ("replay", "replay_chunk"),
            ("next", "next_chunk"),
        ]:
            engine = _make_stub_engine()
            bridge = _make_bridge(engine)
            result = bridge.overlay_action(tag)
            assert result == {"ok": True}, f"action '{tag}' must return ok"
            getattr(engine, method).assert_called_once_with()

    def test_unknown_action_raises(self) -> None:
        """Unknown tags must still raise RuntimeError (existing contract)."""
        engine = _make_stub_engine()
        bridge = _make_bridge(engine)
        with pytest.raises(RuntimeError, match="unknown overlay action"):
            bridge.overlay_action("bogus_action")


# ---------------------------------------------------------------------------
# engine_state includes is_paused
# ---------------------------------------------------------------------------


class TestEngineStateIsPaused:
    """BUG 2 (state half) — engine_state() must emit is_paused so the
    frontend can toggle the play/pause icon.
    """

    def test_engine_state_emits_is_paused_false(self) -> None:
        """RED if engine_state() does not include 'is_paused' key."""
        engine = _make_stub_engine(is_paused=False)
        bridge = _make_bridge(engine)

        state = bridge.engine_state()

        assert "is_paused" in state, (
            "engine_state() must include 'is_paused' so the frontend can "
            "render the correct play/pause icon"
        )
        assert state["is_paused"] is False

    def test_engine_state_emits_is_paused_true(self) -> None:
        """engine_state() must reflect is_paused=True when engine is paused."""
        engine = _make_stub_engine(is_paused=True)
        bridge = _make_bridge(engine)

        state = bridge.engine_state()

        assert state.get("is_paused") is True


# ---------------------------------------------------------------------------
# Real-lock deadlock regression test
# ---------------------------------------------------------------------------


class TestEngineStateNoDeadlock:
    """Regression: engine_state() must not deadlock when engine uses a real
    non-reentrant Lock.

    The mocked tests above hide this because MagicMock's property never
    acquires the lock.  This test uses a minimal real engine-like object whose
    ``is_paused`` property acquires the SAME ``threading.Lock`` that
    ``engine_state()`` holds — exactly replicating the production code path.

    On the unfixed branch, calling ``engine_state()`` inside a thread will
    block forever (deadlock).  The test guards this with a 5-second join
    timeout: if the thread is still alive after 5 s the lock was never
    released and the test FAILS.  After the fix the call returns immediately.
    """

    def _make_real_lock_engine(self, *, is_paused: bool = False) -> Any:
        """Minimal object that replicates the real TTSEngine locking contract.

        Uses a real non-reentrant Lock and a real ``is_paused`` property that
        acquires that same lock — the exact combination that causes the
        deadlock in the unfixed bridge.
        """
        import threading

        lock = threading.Lock()
        _backing: dict[str, Any] = {"_is_paused": is_paused}

        class _RealLockEngine:
            """Minimal engine stub with REAL locking semantics."""

            def __init__(self) -> None:
                # Public fields read by bridge.engine_state() under self.engine.lock
                self.is_speaking: bool = False
                self._backend_name: str | None = "stub"
                self._backend_cls: type | None = None
                self._chunks: list = []
                self._chunk_paths: list = []
                self._queue: list = []
                self.lock = lock
                self._is_paused: bool = _backing["_is_paused"]

            @property
            def is_paused(self) -> bool:
                # Real property: acquires the SAME lock as engine_state() holds.
                # This is what causes the deadlock on the unfixed branch.
                with self.lock:
                    return self._is_paused

        return _RealLockEngine()

    def test_engine_state_returns_without_deadlock(self) -> None:
        """engine_state() must complete within 5 s when the engine uses a real
        non-reentrant Lock.

        RED on unfixed branch: the thread blocks forever (is_paused property
        tries to acquire a lock already held by engine_state).
        GREEN after fix: engine_state reads _is_paused directly under the
        existing lock instead of calling the locking property.
        """
        import threading

        engine = self._make_real_lock_engine(is_paused=True)
        bridge = _make_bridge(engine)

        result_box: list[Any] = []

        def _call() -> None:
            result_box.append(bridge.engine_state())

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        t.join(timeout=5)

        assert not t.is_alive(), (
            "engine_state() deadlocked: thread still blocked after 5 s. "
            "The is_paused property must not be called while holding engine.lock."
        )
        assert len(result_box) == 1, "engine_state() did not return a result"
        assert result_box[0].get("is_paused") is True, (
            "engine_state() must correctly report is_paused=True"
        )
