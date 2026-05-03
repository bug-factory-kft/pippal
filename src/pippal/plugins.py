"""Plugin host registries for PipPal.

The core has no name-awareness of any specific extension: it never
imports `kokoro`, `ai_runner`, etc. directly. Instead, this module
exposes registries that any plugin package — including the `pippal`
package itself — can fill.

`pippal` self-registers Piper, the four selection-driven hotkey
actions (read / queue / pause / stop), the built-in settings cards,
the tray items, and the default config values. Optional extension
packages may add more engines, AI actions, settings cards, tray
items and defaults through the same API.

EXPERIMENTAL — the registry shape is not yet a stable API. Third-
party plugins should pin to a specific PipPal minor version until
the contract settles.

Discovery (`pippal/__init__.py`):

    if importlib.util.find_spec("pippal_extensions") is not None:
        try:
            import pippal_extensions  # self-registers
        except Exception as exc:
            print(f"[pippal] extension load failed: {exc}",
                  file=sys.stderr)

Discovery is presence-based: install the extension package alongside
`pippal` and it self-registers on import.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Named zones for ordered registries (settings cards, tray items)
# ---------------------------------------------------------------------------
# Codex review nudged us away from raw integer priority numbers
# because they become tribal knowledge ("why is this 25?"). Named
# zones with optional sub-order are easier for third-party plugins to
# target precisely.

class Zone:
    CORE     = 0     # always-shown housekeeping
    VOICE    = 100   # voice / engine selection
    SPEECH   = 200   # speed, variation
    HOTKEYS  = 300   # hotkey bindings
    AI       = 400   # AI / Ollama configuration
    PANEL    = 500   # reader panel / overlay
    INTEGRATION = 600  # Windows context menu etc.
    ADVANCED = 700   # advanced / power-user
    ABOUT    = 900   # version, copyright


# ---------------------------------------------------------------------------
# Type aliases — each registry stores plain callables / classes / data.
# Keep them simple so plugins don't have to learn a complicated DSL.
# ---------------------------------------------------------------------------

EngineCls = type  # subclass of TTSBackend; we don't import to avoid a cycle
AiHandler = Callable[[Any, str], None]   # (engine, action_id) -> None
HotkeyAction = tuple[str, str, str, str]  # (id, config_key, label, default)
SettingsCardBuilder = Callable[..., None]
TrayItem = Any   # opaque pystray.MenuItem-or-Menu


# ---------------------------------------------------------------------------
# Internal registries
# ---------------------------------------------------------------------------

_engines: dict[str, EngineCls] = {}
_ai_actions: dict[str, AiHandler] = {}
_hotkey_actions: list[HotkeyAction] = []
_settings_cards: list[tuple[int, int, SettingsCardBuilder]] = []
_tray_items: list[tuple[int, int, TrayItem]] = []
_defaults: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Engine registry
# ---------------------------------------------------------------------------

def register_engine(name: str, cls: EngineCls) -> None:
    """Register a TTSBackend subclass under a config-engine name.

    The engine name is what shows up in `config["engine"]` and in the
    Settings → Voice → Engine combobox. Re-registering an existing name
    overwrites — last writer wins, which is intentional so an extension can
    replace a built-in fallback if both are present."""
    _engines[name] = cls


def engines() -> dict[str, EngineCls]:
    """Snapshot of registered engines. Returned as a fresh dict so
    callers can iterate without holding a reference into the live
    registry."""
    return dict(_engines)


def get_engine(name: str) -> EngineCls | None:
    return _engines.get(name)


# ---------------------------------------------------------------------------
# AI action registry
# ---------------------------------------------------------------------------

def register_ai_action(action_id: str, handler: AiHandler) -> None:
    """Register a handler for a named AI action (e.g. 'summary'). The
    handler receives `(engine, action_id)` and is responsible for the
    full capture → prompt → speak round-trip."""
    _ai_actions[action_id] = handler


def ai_actions() -> dict[str, AiHandler]:
    return dict(_ai_actions)


def get_ai_action(action_id: str) -> AiHandler | None:
    return _ai_actions.get(action_id)


# ---------------------------------------------------------------------------
# Hotkey action registry
# ---------------------------------------------------------------------------

def register_hotkey_action(
    action_id: str,
    config_key: str,
    label: str,
    default_combo: str,
) -> None:
    """Register an action that can be bound to a global hotkey.

    `config_key` is the JSON key in config.json (e.g. 'hotkey_summary').
    `default_combo` populates `_defaults` so the user gets a sensible
    starting binding even if they've never opened Settings."""
    _hotkey_actions.append((action_id, config_key, label, default_combo))
    _defaults[config_key] = default_combo


def hotkey_actions() -> list[HotkeyAction]:
    return list(_hotkey_actions)


# ---------------------------------------------------------------------------
# Settings card registry — zoned + ordered
# ---------------------------------------------------------------------------

def register_settings_card(
    builder: SettingsCardBuilder,
    *,
    zone: int = Zone.ADVANCED,
    order: int = 0,
) -> None:
    """Register a settings card. `zone` picks the broad section
    (use the Zone constants); `order` is a tie-breaker within the zone."""
    _settings_cards.append((zone, order, builder))


def settings_cards() -> list[SettingsCardBuilder]:
    """Builders sorted by (zone, order). Plugins added after import-time
    re-registration will reflect in the next call — Settings reopens
    rebuild from this list."""
    return [b for _, _, b in sorted(_settings_cards, key=lambda t: (t[0], t[1]))]


# ---------------------------------------------------------------------------
# Tray item registry — zoned + ordered
# ---------------------------------------------------------------------------

def register_tray_item(
    builder: Callable[..., Any],
    *,
    zone: int = Zone.ADVANCED,
    order: int = 0,
) -> None:
    """Register a tray-item builder. The builder is called at app-
    compose time with a context object (`engine`, `config`, `overlay`,
    `settings`, `root`, `quit_action`) and is expected to return an
    iterable of `pystray.MenuItem` / `pystray.Menu.SEPARATOR` values.

    Builders (rather than pre-built items) are required because the
    items need real handles to the engine and the Settings window,
    which don't exist yet when plugins import."""
    _tray_items.append((zone, order, builder))


def tray_items() -> list[Callable[..., Any]]:
    """Return tray-item builders sorted by (zone, order). Caller is
    expected to invoke each one with a TrayContext-shaped argument
    and flatten the returned iterables into the final pystray.Menu."""
    return [b for _, _, b in sorted(_tray_items, key=lambda t: (t[0], t[1]))]


# ---------------------------------------------------------------------------
# Defaults registry — layered config
# ---------------------------------------------------------------------------

def register_defaults(d: dict[str, Any]) -> None:
    """Contribute config defaults. Re-registering a key overwrites
    (last writer wins). The effective config is computed at load time
    as `core_defaults + plugin_defaults + user_overrides`; user
    overrides are the only thing actually persisted to config.json."""
    _defaults.update(d)


def defaults() -> dict[str, Any]:
    return dict(_defaults)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

# Names of optional extension packages this build looks for at
# import time. Each must self-register on import (call into the
# `register_*` functions from this module). Add a name here, ship a
# package by that name, and the host picks it up automatically.
_EXTENSION_NAMES: tuple[str, ...] = ("pippal_pro",)


def load_extensions() -> int:
    """Discover and load any optional extension packages installed
    alongside `pippal`. Returns the number of extensions loaded.

    Uses `find_spec` before `import_module` so an `ImportError` from
    inside an extension (broken dependency) isn't conflated with
    'not installed'. A partial install logs to stderr and we
    continue; a half-loaded plugin would be worse than none.
    """
    import importlib
    import importlib.util

    loaded = 0
    for name in _EXTENSION_NAMES:
        if importlib.util.find_spec(name) is None:
            continue
        try:
            importlib.import_module(name)
            loaded += 1
        except Exception as exc:
            print(
                f"[pippal] extension {name!r} is installed but failed "
                f"to load: {exc}. Continuing without it.",
                file=sys.stderr,
            )
    return loaded


# ---------------------------------------------------------------------------
# Test support — clean reset so tests don't leak state between cases.
# ---------------------------------------------------------------------------

def _reset_for_tests() -> None:
    """Public for tests only. Clears every registry. Production code
    should never call this."""
    _engines.clear()
    _ai_actions.clear()
    _hotkey_actions.clear()
    _settings_cards.clear()
    _tray_items.clear()
    _defaults.clear()
