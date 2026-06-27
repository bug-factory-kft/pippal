"""Pure geometry / position helpers for the PipPal web UI windows.

These functions are PURE / stateless: they take ``spec`` / ``position``
as explicit arguments and touch no ``WebWindowManager`` instance state.
``windows.py`` imports this module LAZILY (at call-time, not at module
top level) so that ``import pippal`` remains headless-safe (H3).

Behaviour: #247 (screen-centre fallback), #280 (overlay bottom-centre
anchor), B3 (off-screen clamp check).
"""

from __future__ import annotations

from typing import Any

import webview


def valid_position_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def centered_on_screen(spec: dict[str, Any]) -> dict[str, int] | None:
    """Return x/y to centre ``spec``-sized window on the primary screen."""
    try:
        screen = webview.screens[0]
        screen_x = int(getattr(screen, "x", 0))
        screen_y = int(getattr(screen, "y", 0))
        screen_width = int(screen.width)
        screen_height = int(screen.height)
        width = int(spec["width"])
        height = int(spec["height"])
    except (AttributeError, IndexError, TypeError, ValueError):
        return None
    return {
        "x": screen_x + (screen_width - width) // 2,
        "y": screen_y + (screen_height - height) // 2,
    }


def position_on_any_screen(
    position: dict[str, int],
    spec: dict[str, Any],
) -> bool:
    """Return True if *position* places the window so it intersects at
    least one current screen by at least 1x1 pixel.

    Uses ``webview.screens`` which pywebview >=5.0 exposes as a list of
    screen objects with ``.x``, ``.y``, ``.width``, ``.height``.  If the
    screens list is unavailable (headless / CI) we return ``True`` so the
    saved position is used as-is (safest degradation).
    """
    try:
        screens = webview.screens
        if not screens:
            return True  # no screen info — trust the saved value
    except Exception:
        return True  # no webview host — trust the saved value
    try:
        wx = int(position["x"])
        wy = int(position["y"])
        ww = int(spec.get("width", 1))
        wh = int(spec.get("height", 1))
    except (KeyError, TypeError, ValueError):
        return False
    # Window rect: [wx, wx+ww) x [wy, wy+wh)
    for screen in screens:
        try:
            sx = int(getattr(screen, "x", 0))
            sy = int(getattr(screen, "y", 0))
            sw = int(screen.width)
            sh = int(screen.height)
        except (AttributeError, TypeError, ValueError):
            continue
        # Check axis-aligned rectangle intersection (at least 1px overlap).
        if wx < sx + sw and wx + ww > sx and wy < sy + sh and wy + wh > sy:
            return True
    return False


def overlay_position(spec: dict[str, Any]) -> dict[str, int] | None:
    """Return bottom-centre position for the overlay on the active screen.

    Places the overlay horizontally centred, 40 px above the bottom of
    the primary screen.  Returns None when headless / no screen available
    (e.g. CI).  (#280)
    """
    try:
        screen = webview.screens[0]
        screen_x = int(getattr(screen, "x", 0))
        screen_y = int(getattr(screen, "y", 0))
        screen_width = int(screen.width)
        screen_height = int(screen.height)
        width = int(spec["width"])
        height = int(spec["height"])
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None
    return {
        "x": screen_x + (screen_width - width) // 2,
        "y": screen_y + screen_height - height - 40,
    }
