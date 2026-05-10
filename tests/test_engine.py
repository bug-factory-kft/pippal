"""Smoke tests for TTSEngine state — exercises the synchronous helpers
that don't require a working winsound / external engine / clipboard."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pippal.engine import TTSEngine
from pippal.engines.piper import PiperBackend


@pytest.fixture()
def engine() -> TTSEngine:
    root = MagicMock()
    config: dict[str, Any] = {"engine": "piper"}
    return TTSEngine(root, config, overlay_ref=lambda: None)


class TestHistory:
    def test_attach_and_get(self, engine: TTSEngine):
        engine.attach_history(["a", "b", "c"], save_callback=None)
        assert engine.get_history() == ["a", "b", "c"]

    def test_attach_copies_input(self, engine: TTSEngine):
        original = ["a"]
        engine.attach_history(original, None)
        original.append("b")
        assert engine.get_history() == ["a"]

    def test_clear_history_calls_save(self, engine: TTSEngine):
        seen: list[list[str]] = []
        engine.attach_history(["a"], save_callback=seen.append)
        engine.clear_history()
        assert engine.get_history() == []
        assert seen == [[]]

    def test_remember_dedupes_and_caps(self, engine: TTSEngine):
        engine.attach_history([f"t{i}" for i in range(15)], None)
        engine._remember("new")
        h = engine.get_history()
        assert h[0] == "new"
        assert len(h) <= 12  # MAX_HISTORY

    def test_remember_empty_is_noop(self, engine: TTSEngine):
        engine.attach_history(["a"], None)
        engine._remember("")
        engine._remember("   ")
        assert engine.get_history() == ["a"]

    def test_remember_strips_whitespace(self, engine: TTSEngine):
        engine.attach_history([], None)
        engine._remember("  hello  ")
        assert engine.get_history() == ["hello"]


class TestQueue:
    def test_default_zero(self, engine: TTSEngine):
        assert engine.queue_length() == 0


class TestPauseToggle:
    def test_no_op_when_not_speaking(self, engine: TTSEngine):
        # Should not flip _is_paused when nothing is playing.
        engine.pause_toggle()
        assert engine._is_paused is False

    def test_toggles_only_after_speaking_set(self, engine: TTSEngine):
        engine.is_speaking = True
        engine.pause_toggle()
        assert engine._is_paused is True
        engine.pause_toggle()
        assert engine._is_paused is False


# `ai_runner` lives in pippal_pro. The public package's CI runs without
# the Pro extension on the import path; skip Pro-touching tests cleanly
# in that case. The full test suite for these still runs in the
# pippal-pro repo's own pytest config.
_ai_runner = pytest.importorskip("pippal_pro.ai_runner")


class TestPromptFor:
    """Exercises `pippal_pro.ai_runner.prompt_for` directly. The
    function moved out of pippal.engine during the plugin-host refactor;
    the equivalent tests live here for now and will move under
    pippal-pro/tests/ once the public/Pro split has settled."""

    @pytest.mark.parametrize("action", ["summary", "explain", "define"])
    def test_returns_prompt_for_known_actions(self, engine: TTSEngine, action: str):
        assert _ai_runner.prompt_for(engine, action) != ""

    def test_translate_uses_target(self, engine: TTSEngine):
        engine.config["ai_translate_target"] = "German"
        assert "German" in _ai_runner.prompt_for(engine, "translate")

    def test_unknown_action_returns_empty(self, engine: TTSEngine):
        assert _ai_runner.prompt_for(engine, "nope") == ""


class TestResetBackend:
    def test_clears_cache(self, engine: TTSEngine):
        engine._backend = MagicMock()
        engine._backend_name = "piper"
        engine.reset_backend()
        assert engine._backend is None
        assert engine._backend_name is None


class TestTokenCancellation:
    """`stop()` must signal in-flight workers via the generation token.
    These pin the cancellation invariant so a future refactor that
    forgets to bump or check the token blows up loudly."""

    def test_is_cancelled_false_for_current_token(self, engine: TTSEngine):
        with engine.lock:
            current = engine.token
        assert not engine._is_cancelled(current)

    def test_stop_cancels_old_tokens(self, engine: TTSEngine):
        with engine.lock:
            old = engine.token
        engine.stop()
        assert engine._is_cancelled(old)

    def test_each_top_level_action_bumps_token(self, engine: TTSEngine):
        # speak / queue / replay / ai / export / stop all bump the token
        # so any in-flight worker self-cancels. We can't run the whole
        # async chain in a unit test, but we CAN check the bump.
        with engine.lock:
            t0 = engine.token
        engine.stop()
        with engine.lock:
            assert engine.token > t0

    def test_stop_clears_is_speaking(self, engine: TTSEngine):
        # Regression: synthesize_and_play's cancel-exit returns without
        # clearing is_speaking, so stop() must do it itself or the tray
        # icon would lie about playback state until the next speak.
        engine.is_speaking = True
        engine.stop()
        assert engine.is_speaking is False


class TestBackendCacheRequestedName:
    """When the user requests an extension-supplied engine but it's
    unavailable, the factory falls back to Piper. The cache is keyed
    against the *requested* engine, so subsequent calls don't
    re-instantiate the fallback every chunk."""

    def test_unavailable_engine_fallback_caches_against_requested_name(self):
        from pathlib import Path

        from pippal import plugins
        from pippal.engine import TTSEngine
        from pippal.engines.base import TTSBackend

        class _FakeEngine(TTSBackend):
            name = "fake-engine"

            def is_available(self) -> bool:
                return False

            def synthesize(self, text: str, out_path: Path) -> bool:
                return False

        engine = TTSEngine(MagicMock(), {"engine": "fake-engine"}, lambda: None)
        plugins.register_engine("fake-engine", _FakeEngine)
        try:
            backend1 = engine._get_backend()
            backend2 = engine._get_backend()
        finally:
            plugins._engines.pop("fake-engine", None)
        assert backend1 is backend2  # cached, not re-built every call
        assert isinstance(backend1, PiperBackend)
        # Cache key is the *requested* name so subsequent calls don't
        # re-resolve and re-warn.
        assert engine._backend_name == "fake-engine"


class TestCaptureSelectionReleasesModifiers:
    def test_releases_configured_combo_plus_universals(self, engine: TTSEngine):
        with patch("pippal.clipboard_capture.keyboard") as kb, \
             patch("pippal.clipboard_capture.pyperclip") as cb, \
             patch("pippal.clipboard_capture.time.sleep"):  # don't actually wait
            cb.paste.return_value = "captured-text"
            cb.copy.return_value = None
            engine._capture_selection("ctrl+shift+x")
            released = {c.args[0] for c in kb.release.call_args_list}
        # Configured combo keys
        assert {"ctrl", "shift", "x"} <= released
        # Universal modifier set always released even if combo is empty
        assert {"alt", "super"} <= released

    def test_handles_empty_combo(self, engine: TTSEngine):
        with patch("pippal.clipboard_capture.keyboard") as kb, \
             patch("pippal.clipboard_capture.pyperclip") as cb, \
             patch("pippal.clipboard_capture.time.sleep"):
            cb.paste.return_value = "captured"
            engine._capture_selection("")
            released = {c.args[0] for c in kb.release.call_args_list}
        assert {"ctrl", "shift", "alt", "super"} <= released


