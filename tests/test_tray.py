"""Tray-icon factory tests.

``make_tray_icon`` is a pure function in the ``Pillow ⇒ Image``
sense — it always returns a 64×64 RGBA canvas, the speaking variant
must differ visibly from the idle one, and it caches per-state so
the tray-tick (which calls it every ~400 ms) doesn't re-paint when
nothing has changed."""

from __future__ import annotations

import pytest
from PIL import Image

from pippal import tray


@pytest.fixture(autouse=True)
def _clean_icon_cache():
    """Each test starts with a fresh cache so order doesn't matter."""
    tray._icon_cache.clear()
    yield
    tray._icon_cache.clear()


class TestMakeTrayIcon:
    def test_returns_64x64_rgba_image(self):
        img = tray.make_tray_icon(speaking=False)
        assert isinstance(img, Image.Image)
        assert img.size == (64, 64)
        assert img.mode == "RGBA"

    def test_speaking_variant_differs_from_idle(self):
        idle = tray.make_tray_icon(speaking=False)
        speaking = tray.make_tray_icon(speaking=True)
        # Both 64x64 RGBA — but the speaking variant has a red badge,
        # so at least one pixel must differ.
        assert idle.tobytes() != speaking.tobytes()

    def test_caches_per_state(self):
        # Same state, same instance — the tray-tick calls this every
        # ~400 ms; recomputing every time would waste CPU.
        a = tray.make_tray_icon(speaking=False)
        b = tray.make_tray_icon(speaking=False)
        assert a is b

    def test_speaking_and_idle_are_separate_cache_entries(self):
        idle = tray.make_tray_icon(speaking=False)
        speaking = tray.make_tray_icon(speaking=True)
        # Cache holds both, distinctly.
        assert tray._icon_cache.get("idle") is idle
        assert tray._icon_cache.get("speaking") is speaking
