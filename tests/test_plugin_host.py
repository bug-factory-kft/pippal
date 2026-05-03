"""Public contract tests for `pippal.plugins`.

These pin the registry's behaviour from the perspective of a hypothetical
third-party plugin. The public `pippal` package guarantees:

- engines, ai_actions, hotkey_actions, settings cards, tray items and
  defaults can be registered from any imported module
- registrations are visible to the engine factory and the app composer
- a name registered later WINS (last-writer semantics) so an extension
  can replace a default registration
- unknown / unregistered names degrade gracefully (Piper fallback for
  engines, no-op for AI actions, skipped for hotkeys)

If anyone ships a `pippal-elevenlabs` or `pippal-edge-tts` plugin
tomorrow, these tests are the contract they're coding against."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pippal import plugins
from pippal.engines import PiperBackend, make_backend
from pippal.engines.base import TTSBackend


class _FakeBackend(TTSBackend):
    """Tiny TTSBackend that pretends to work and doesn't touch disk."""
    name = "fake-test-engine"

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, out_path: Path) -> bool:
        return True


@pytest.fixture()
def _isolated_registry():
    """Snapshot every registry, run the test, restore. Tests that
    register fakes in the engine / ai-action / hotkey-action /
    settings-card / tray-item registries can use this to leave the
    global registry exactly as they found it."""
    snap = {
        "engines": dict(plugins._engines),
        "ai":      dict(plugins._ai_actions),
        "hk":      list(plugins._hotkey_actions),
        "cards":   list(plugins._settings_cards),
        "tray":    list(plugins._tray_items),
        "def":     dict(plugins._defaults),
    }
    yield
    plugins._engines.clear()
    plugins._engines.update(snap["engines"])
    plugins._ai_actions.clear()
    plugins._ai_actions.update(snap["ai"])
    plugins._hotkey_actions.clear()
    plugins._hotkey_actions.extend(snap["hk"])
    plugins._settings_cards.clear()
    plugins._settings_cards.extend(snap["cards"])
    plugins._tray_items.clear()
    plugins._tray_items.extend(snap["tray"])
    plugins._defaults.clear()
    plugins._defaults.update(snap["def"])


class TestEngineRegistry:
    def test_third_party_plugin_can_register_engine(self, _isolated_registry):
        plugins.register_engine("fake-test-engine", _FakeBackend)
        assert "fake-test-engine" in plugins.engines()

    def test_factory_uses_registered_engine(self, _isolated_registry):
        plugins.register_engine("fake-test-engine", _FakeBackend)
        backend = make_backend({"engine": "fake-test-engine"})
        assert isinstance(backend, _FakeBackend)

    def test_unknown_engine_falls_back_to_piper(self, _isolated_registry):
        # No 'never-heard-of-it' engine registered — factory falls back.
        backend = make_backend({"engine": "never-heard-of-it"})
        assert isinstance(backend, PiperBackend)

    def test_factory_falls_back_when_registered_engine_unavailable(
        self, _isolated_registry,
    ):
        class _BrokenBackend(TTSBackend):
            name = "broken"

            def is_available(self) -> bool:
                return False

            def synthesize(self, text: str, out_path: Path) -> bool:
                return False

        plugins.register_engine("broken", _BrokenBackend)
        backend = make_backend({"engine": "broken"})
        # Falls back to whatever's registered for 'piper'.
        assert isinstance(backend, PiperBackend)

    def test_re_register_overwrites(self, _isolated_registry):
        plugins.register_engine("fake-test-engine", _FakeBackend)

        class _Replacement(_FakeBackend):
            pass

        plugins.register_engine("fake-test-engine", _Replacement)
        assert plugins.get_engine("fake-test-engine") is _Replacement


class TestAiActionRegistry:
    def test_register_and_lookup(self, _isolated_registry):
        seen: dict[str, Any] = {}

        def handler(engine: Any, action_id: str) -> None:
            seen["engine"] = engine
            seen["action_id"] = action_id

        plugins.register_ai_action("fake-action", handler)
        h = plugins.get_ai_action("fake-action")
        assert h is handler

        sentinel_engine = MagicMock()
        h(sentinel_engine, "fake-action")
        assert seen["engine"] is sentinel_engine
        assert seen["action_id"] == "fake-action"

    def test_get_unknown_returns_none(self, _isolated_registry):
        assert plugins.get_ai_action("never-registered") is None


class TestHotkeyRegistry:
    def test_register_seeds_default_into_defaults_registry(
        self, _isolated_registry,
    ):
        plugins.register_hotkey_action(
            "fake", "hotkey_fake", "Fake action", "alt+shift+x",
        )
        # The default combo lands in the defaults registry too — that's
        # how a plugin's hotkey shows up in the user's effective config.
        assert plugins.defaults().get("hotkey_fake") == "alt+shift+x"
        # And the action itself is iterable through hotkey_actions().
        ids = {a[0] for a in plugins.hotkey_actions()}
        assert "fake" in ids


class TestSettingsCardRegistry:
    def test_zone_order_drives_iteration(self, _isolated_registry):
        plugins._settings_cards.clear()
        calls: list[str] = []
        plugins.register_settings_card(
            lambda *_a, **_k: calls.append("late"),
            zone=plugins.Zone.ABOUT,
        )
        plugins.register_settings_card(
            lambda *_a, **_k: calls.append("voice"),
            zone=plugins.Zone.VOICE,
        )
        plugins.register_settings_card(
            lambda *_a, **_k: calls.append("ai"),
            zone=plugins.Zone.AI,
        )
        for builder in plugins.settings_cards():
            builder()
        assert calls == ["voice", "ai", "late"]


class TestTrayItemRegistry:
    def test_zone_order_drives_iteration(self, _isolated_registry):
        plugins._tray_items.clear()
        plugins.register_tray_item(
            lambda ctx: ["q"], zone=plugins.Zone.ADVANCED, order=90,
        )
        plugins.register_tray_item(
            lambda ctx: ["r"], zone=plugins.Zone.ADVANCED, order=10,
        )
        plugins.register_tray_item(
            lambda ctx: ["m"], zone=plugins.Zone.ADVANCED, order=20,
        )
        out: list[str] = []
        for b in plugins.tray_items():
            out.extend(b(None))
        assert out == ["r", "m", "q"]
