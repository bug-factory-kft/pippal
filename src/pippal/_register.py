"""core distribution self-registration.

Imported once at package import time (`pippal/__init__.py`) so that the
plugin registries (`pippal.plugins`) come up populated with everything
the core build provides:

- the Piper engine
- four selection-driven hotkey actions (read / queue / pause / stop)
- six settings cards (Voice / Speech / Hotkeys / Panel / Integration / About)
- three tray-item builders (Recent submenu, Settings, Quit)
- the core config defaults

If you're a third-party plugin author, this file is a good worked
example of how to fill the registries from your own package's
`__init__.py` — pippal_pro does the same thing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pystray

from . import plugins
from .config import DEFAULT_CONFIG
from .engines.piper import PiperBackend
from .plugins import Zone

# ---------------------------------------------------------------------------
# Tray item builders for the core package.
# ---------------------------------------------------------------------------
# Builders are called at app-compose time with a SimpleNamespace context
# (engine, config, overlay, settings, root, quit_action, tray_action,
# save_config, history_submenu_builder). They return an iterable of
# pystray items.

def _recent_tray_builder(ctx: Any) -> list:
    return [
        pystray.MenuItem("Recent", pystray.Menu(ctx.history_submenu_builder)),
    ]


def _settings_tray_builder(ctx: Any) -> list:
    return [
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Settings…",
            lambda _i, _it: ctx.root.after(0, ctx.settings.open),
            # Left-click (single-click) on the tray icon fires the
            # default item — Settings is the most useful target.
            default=True,
        ),
    ]


def _quit_tray_builder(ctx: Any) -> list:
    return [
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", ctx.quit_action),
    ]


def _register() -> None:
    # ----- Engine -----
    plugins.register_engine("piper", PiperBackend)

    # ----- Voice catalogue -----
    # Built-in 18-voice subset of the rhasspy/piper-voices catalogue.
    # Extension packages can extend this via plugins.register_voices().
    from .voices import KNOWN_VOICES
    plugins.register_voices(KNOWN_VOICES)

    # ----- Settings cards -----
    # Imported lazily so this module can be imported even in test
    # contexts that don't have Tk available — the import only resolves
    # when _register() is actually invoked at package-import time.
    from .ui import settings_cards as cards
    plugins.register_settings_card(cards.build_voice_card,       zone=Zone.VOICE)
    plugins.register_settings_card(cards.build_speech_card,      zone=Zone.SPEECH)
    plugins.register_settings_card(cards.build_hotkeys_card,     zone=Zone.HOTKEYS)
    plugins.register_settings_card(cards.build_panel_card,       zone=Zone.PANEL)
    plugins.register_settings_card(cards.build_integration_card, zone=Zone.INTEGRATION)
    plugins.register_settings_card(cards.build_about_card,       zone=Zone.ABOUT)

    # ----- Hotkey actions (selection-driven, no AI) -----
    plugins.register_hotkey_action(
        "speak", "hotkey_speak", "Read selection",
        "windows+shift+r",
    )
    plugins.register_hotkey_action(
        "queue", "hotkey_queue", "Queue selection",
        "windows+shift+q",
    )
    plugins.register_hotkey_action(
        "pause", "hotkey_pause", "Pause / Resume",
        "windows+shift+p",
    )
    plugins.register_hotkey_action(
        "stop", "hotkey_stop", "Stop",
        "windows+shift+b",
    )

    # ----- Tray items (Recent, then Pro can slot Mood here, then
    # Settings + Quit). The numeric orders give Pro plenty of room to
    # insert before Settings without colliding. -----
    plugins.register_tray_item(_recent_tray_builder,   zone=Zone.ADVANCED, order=10)
    plugins.register_tray_item(_settings_tray_builder, zone=Zone.ADVANCED, order=80)
    plugins.register_tray_item(_quit_tray_builder,     zone=Zone.ADVANCED, order=90)

    # ----- core config defaults -----
    free_defaults: dict[str, Any] = {
        k: v for k, v in DEFAULT_CONFIG.items()
        if not k.startswith("hotkey_")
    }
    plugins.register_defaults(free_defaults)


# Silence unused-import warnings for typing-only names.
_ = Callable

_register()
