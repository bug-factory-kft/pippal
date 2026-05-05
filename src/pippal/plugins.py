"""Plugin host registries for PipPal.

PipPal is split into a public MIT core (`pippal`) and an optional
proprietary extension package (`pippal_pro`). The core has zero
name-awareness of Pro features: it never imports `kokoro`, `ai_runner`,
`moods`, etc. Instead, this module exposes registries that any plugin
package — including the core `pippal` package itself — can fill.

The core distribution self-registers Piper, the four selection-driven
hotkey actions (read / queue / pause / stop), the core settings cards,
the core tray items, and the core config defaults. The Pro distribution,
when installed alongside, self-registers Kokoro, the AI actions, AI
hotkeys, AI settings card, Mood tray submenu, and Pro defaults.

EXPERIMENTAL — the registry shape is not yet a stable API. It will move
toward a 1.0 contract once Pro has shipped against it for a few
releases. Third-party plugins should pin to a specific PipPal minor
version until then.

Discovery (`pippal/__init__.py`):

    if importlib.util.find_spec("pippal_pro") is not None:
        try:
            import pippal_pro  # self-registers
        except Exception as exc:
            # Don't silently swallow: a partial Pro install is worse
            # than no Pro install. Log and continue with built-in only.
            print(f"[pippal] pippal_pro present but failed to load: {exc}",
                  file=sys.stderr)

There is no `is_pro_user()` orthogonal license check. The presence of
`pippal_pro` IS the gate — Microsoft Store delivers an MSIX bundling
both packages to paid users; Public users `pip install pippal` and only
ever see the core registry.
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
# `_voices` is a list of `PiperVoice` (typed dict from pippal.voices).
# Contributors append to it via `register_voices`. The Voice Manager
# iterates `voices()` to build its catalogue, so the same dialog works
# both with the small built-in subset and with the larger lists that
# extension packages register on top.
_voices: list[Any] = []


# ---------------------------------------------------------------------------
# Engine registry
# ---------------------------------------------------------------------------

def register_engine(name: str, cls: EngineCls) -> None:
    """Register a TTSBackend subclass under a config-engine name.

    The engine name is what shows up in `config["engine"]` and in the
    Settings → Voice → Engine combobox. Re-registering an existing name
    overwrites — last writer wins, which is intentional so Pro can
    replace a core fallback if both are present."""
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
# Voice catalogue registry
# ---------------------------------------------------------------------------

def register_voices(catalog: list[Any]) -> None:
    """Append voice entries to the catalogue iterated by the Voice
    Manager. Each entry is a `PiperVoice` typed-dict (see
    `pippal.voices.PiperVoice`). De-dupes on `id` so an extension that
    re-registers the same voice doesn't double the row count."""
    seen = {v["id"] for v in _voices}
    for v in catalog:
        if v.get("id") and v["id"] not in seen:
            _voices.append(v)
            seen.add(v["id"])


def voices() -> list[Any]:
    """Snapshot of all registered voices (built-in + extension)."""
    return list(_voices)


# ---------------------------------------------------------------------------
# Per-engine voice options registry
# ---------------------------------------------------------------------------
# An engine plugin like the Kokoro backend ships with a flat list of
# voices that don't fit the Piper-style ``PiperVoice`` shape (no
# language code in the id, no ``.onnx`` filename to install). The
# Settings Voice card needs *some* way to populate the voice combo
# when the user selects that engine, but the core has no opinion on
# what those voices look like — so we expose a tiny opaque registry:
# the engine plugin hands us ``(value, label)`` pairs and an optional
# ``language_extractor(value) -> str`` for the language filter.

_engine_voice_options: dict[
    str,
    tuple[list[tuple[str, str]], Callable[[str], str] | None],
] = {}


def register_engine_voice_options(
    engine_name: str,
    options: list[tuple[str, str]],
    language_extractor: Callable[[str], str] | None = None,
) -> None:
    """Register the voice combo content for an engine.

    ``options`` is a list of ``(value, label)`` pairs as the Settings
    voice combo will display them. ``language_extractor`` is an
    optional callable that derives a human-readable language name from
    a voice value — when present, the Voice card shows a Language
    filter row that lets the user trim a long list to one language at
    a time."""
    _engine_voice_options[engine_name] = (list(options), language_extractor)


def engine_voice_options(engine_name: str) -> list[tuple[str, str]]:
    """``(value, label)`` pairs the engine's voice combo should show.
    Empty list when no plugin has registered options for ``engine_name``
    — the Settings card hides the engine-specific UI in that case."""
    return list(_engine_voice_options.get(engine_name, ([], None))[0])


def engine_language_extractor(engine_name: str) -> Callable[[str], str] | None:
    """Optional ``value -> language`` callable for an engine. Returns
    None when the registered engine doesn't categorise voices by
    language (or when no engine is registered for ``engine_name``)."""
    return _engine_voice_options.get(engine_name, ([], None))[1]


# ---------------------------------------------------------------------------
# Voice card extension hooks
# ---------------------------------------------------------------------------
# Engines whose Settings UI needs more than the generic Engine + Voice
# combo (e.g. Kokoro wants a Language filter row and an Install
# button) register two callbacks here. The core Voice-card builder
# walks the registries — it has no engine-specific code.

# Builders that attach extra widgets to the Voice card. Each builder is
# called once at card-build time with ``(sw, card)`` and is expected
# to attach widgets to ``sw`` (e.g. ``sw.kokoro_lang_row = ...``) so
# the engine-change handler can show / hide them later.
_voice_card_extras_builders: list[Callable[[Any, Any], None]] = []

# Handlers that run on every engine-combo change. Receive
# ``(sw, current_engine_name)`` and are expected to show their own
# widgets when the user picked their engine and hide them otherwise.
# A handler may also override the voice combo content (Pro's Kokoro
# handler does this via ``plugins.engine_voice_options``).
_voice_card_engine_handlers: list[Callable[[Any, str], None]] = []


def register_voice_card_extras_builder(
    builder: Callable[[Any, Any], None],
) -> None:
    """Add widgets to the Settings → Voice card. ``builder(sw, card)``
    runs once at card-build time. Use this from an engine plugin to
    attach engine-specific controls to the card; pair with
    ``register_voice_card_engine_handler`` for the show/hide logic."""
    _voice_card_extras_builders.append(builder)


def voice_card_extras_builders() -> list[Callable[[Any, Any], None]]:
    return list(_voice_card_extras_builders)


def register_voice_card_engine_handler(
    handler: Callable[[Any, str], None],
) -> None:
    """Run on every engine-combo selection. ``handler(sw, engine_name)``
    sees the new engine name and is expected to show / hide its own
    widgets and (optionally) override the voice combo content."""
    _voice_card_engine_handlers.append(handler)


def voice_card_engine_handlers() -> list[Callable[[Any, str], None]]:
    return list(_voice_card_engine_handlers)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def load_pro_plugin() -> bool:
    """Try to load `pippal_pro` if installed. Returns True on success.

    Uses `find_spec` first so an `ImportError` from inside the package
    (broken Pro dependency) doesn't get conflated with 'Pro not
    installed'. A partial install logs to stderr and we continue with
    the built-in package only — the user shouldn't get a half-Pro experience silently.
    """
    import importlib
    import importlib.util

    if importlib.util.find_spec("pippal_pro") is None:
        return False
    try:
        importlib.import_module("pippal_pro")
        return True
    except Exception as exc:
        print(
            f"[pippal] pippal_pro is installed but failed to load: {exc}. "
            "Continuing with built-in features only.",
            file=sys.stderr,
        )
        return False


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
    _voices.clear()
    _engine_voice_options.clear()
    _voice_card_extras_builders.clear()
    _voice_card_engine_handlers.clear()
