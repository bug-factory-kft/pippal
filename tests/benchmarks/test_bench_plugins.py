"""Benchmarks for the plugin-host registry lookups. The dispatcher
calls these on hot paths (every settings-card build, every engine
change, every keystroke) so a slowdown here is felt across the
whole UI."""

from __future__ import annotations

import pytest

from pippal import plugins

pytestmark = pytest.mark.benchmark(group="plugins")


@pytest.fixture(autouse=True)
def _seeded_registry():
    """Snapshot/restore plus a small population so the benchmarks see
    realistic non-empty registries."""
    snap = {
        "engines":    dict(plugins._engines),
        "ai":         dict(plugins._ai_actions),
        "hk":         list(plugins._hotkey_actions),
        "voices":     list(plugins._voices),
        "evo":        dict(plugins._engine_voice_options),
    }
    # Add one extra synthetic engine + a 100-entry voice catalogue so
    # the lookup is non-trivial.
    plugins._engines.setdefault("synthetic", object)  # type: ignore[arg-type]
    plugins._engine_voice_options["synthetic"] = (
        [(f"v_{i}", f"Voice {i}") for i in range(100)],
        lambda v: "English",
    )
    yield
    plugins._engines.clear()
    plugins._engines.update(snap["engines"])
    plugins._ai_actions.clear()
    plugins._ai_actions.update(snap["ai"])
    plugins._hotkey_actions.clear()
    plugins._hotkey_actions.extend(snap["hk"])
    plugins._voices.clear()
    plugins._voices.extend(snap["voices"])
    plugins._engine_voice_options.clear()
    plugins._engine_voice_options.update(snap["evo"])


def test_engines_snapshot(benchmark):
    benchmark(plugins.engines)


def test_get_engine_hit(benchmark):
    benchmark(plugins.get_engine, "piper")


def test_get_engine_miss(benchmark):
    benchmark(plugins.get_engine, "nonexistent")


def test_hotkey_actions_snapshot(benchmark):
    benchmark(plugins.hotkey_actions)


def test_voices_snapshot(benchmark):
    benchmark(plugins.voices)


def test_engine_voice_options(benchmark):
    benchmark(plugins.engine_voice_options, "synthetic")


def test_engine_language_extractor(benchmark):
    benchmark(plugins.engine_language_extractor, "synthetic")
