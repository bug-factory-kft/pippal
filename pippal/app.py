"""PipPal application composition.

This is where the parts wire up: load config, create the Tk root, the
overlay and the engine, register hotkeys, build the tray menu, start
the local IPC server, run the Tk mainloop."""

from __future__ import annotations

import sys
import tkinter as tk
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import keyboard
import pystray

from . import plugins
from .command_server import start_command_server
from .config import load_config, save_config
from .engine import TTSEngine
from .history import load_history, save_history
from .paths import PIPER_EXE, ensure_dirs
from .timing import TRAY_POLL_MS
from .tray import make_tray_icon
from .ui import Overlay, SettingsWindow


def _build_history_submenu(engine: TTSEngine,
                            on_clear: Callable[[Any, Any], None]) -> Callable[[], list[pystray.MenuItem]]:
    """Return a callable that pystray re-evaluates each time the menu is
    opened so the recent-readings list stays fresh."""

    def make_replay_handler(text: str) -> Callable[[Any, Any], None]:
        def _h(_icon: Any, _item: Any) -> None:
            engine.replay_text(text)
        return _h

    def builder() -> list[pystray.MenuItem]:
        items = engine.get_history()
        if not items:
            return [
                pystray.MenuItem("(empty)", lambda _i, _it: None, enabled=False),
            ]
        out: list[pystray.MenuItem] = []
        for t in items[:10]:
            preview = t.replace("\n", " ").strip()
            if len(preview) > 70:
                preview = preview[:67] + "…"
            out.append(pystray.MenuItem(preview, make_replay_handler(t)))
        out.append(pystray.Menu.SEPARATOR)
        out.append(pystray.MenuItem("Clear history", on_clear))
        return out

    return builder


def main() -> None:
    ensure_dirs()
    config = load_config()

    # The user can opt into Kokoro-only setups; only require piper.exe
    # when Piper is the configured engine.
    engine_name = (config.get("engine") or "piper").lower()
    if engine_name == "piper" and not PIPER_EXE.exists():
        print(
            f"piper.exe missing at {PIPER_EXE}; run setup.ps1 or "
            "switch engine to Kokoro in Settings.",
            file=sys.stderr,
        )
        sys.exit(1)

    root = tk.Tk()
    root.withdraw()

    # Overlay needs the engine for its player buttons; engine needs the
    # overlay to drive the panel. We hold an overlay reference inside a
    # tiny mutable cell so the engine can resolve it lazily — the
    # overlay can then be created BEFORE the engine.
    overlay_box: list[Overlay | None] = [None]
    engine = TTSEngine(root, config, overlay_ref=lambda: overlay_box[0])

    overlay = Overlay(
        root, config,
        on_stop=engine.stop,
        on_prev=engine.prev_chunk,
        on_replay=engine.replay_chunk,
        on_next=engine.next_chunk,
    )
    overlay_box[0] = overlay
    engine.attach_history(load_history(), save_history)

    # Local IPC server for the right-click context-menu helper. If the
    # port is already busy (PipPal already running, or some other
    # process), the helper just won't function — surface that loudly so
    # we don't pretend everything's fine.
    if start_command_server(engine) is None:
        print(
            "[pippal] right-click integration disabled: "
            "could not bind 127.0.0.1:51677",
            file=sys.stderr,
        )

    # ----- Hotkeys -----
    # The action → handler mapping is composed from two sources:
    #   1. Built-in selection-driven actions, supplied by the engine.
    #   2. AI actions, looked up in plugins.ai_actions(). When pippal_pro
    #      is loaded, those are populated; in a Free build they're empty
    #      and the corresponding hotkeys simply skip binding.
    builtin_handlers: dict[str, Callable[[], None]] = {
        "speak": engine.speak_selection_async,
        "queue": engine.queue_selection_async,
        "pause": engine.pause_toggle,
        "stop":  engine.stop,
    }

    def _resolve_handler(action_id: str) -> Callable[[], None] | None:
        if action_id in builtin_handlers:
            return builtin_handlers[action_id]
        ai = plugins.get_ai_action(action_id)
        if ai is not None:
            return lambda aid=action_id: ai(engine, aid)
        # Legacy path: the engine still carries `speak_<action>_async`
        # methods until Stage 2 moves them to pippal_pro. Once
        # pippal.engine drops those, this branch becomes unreachable
        # in a Free build (correctly — no Pro = no AI hotkeys).
        legacy = getattr(engine, f"speak_{action_id}_async", None)
        return legacy if callable(legacy) else None

    handles: dict[str, Any] = {}

    def bind_hotkeys() -> list[tuple[str, str, str]]:
        """Returns a list of (action_id, combo, error) for any binding
        that failed, so the Settings window can warn the user instead of
        silently saving a broken combo to disk."""
        failures: list[tuple[str, str, str]] = []
        for name, h in list(handles.items()):
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
            handles.pop(name, None)
        for action_id, key, _label, default_combo in plugins.hotkey_actions():
            combo = config.get(key, default_combo)
            fn = _resolve_handler(action_id)
            if not combo or fn is None:
                continue
            try:
                # suppress=True so other apps (Chrome, Word, etc.)
                # don't also see the combo. Without this, e.g.
                # `ctrl+shift+t` would simultaneously fire PipPal's
                # Translate AND Chrome's "reopen closed tab".
                handles[action_id] = keyboard.add_hotkey(
                    combo, fn, suppress=True,
                )
            except Exception as e:
                print(f"[hotkey] failed to bind {action_id}={combo}: {e}",
                      file=sys.stderr)
                failures.append((action_id, combo, str(e)))
        return failures

    bind_hotkeys()

    # ----- Settings window -----
    settings = SettingsWindow(
        root, config,
        on_save=save_config,
        on_hotkey_change=bind_hotkeys,
        on_engine_change=engine.reset_backend,
    )

    # ----- Tray -----
    tray: dict[str, Any] = {"icon": None}

    def update_tray_icon() -> None:
        ic = tray.get("icon")
        if ic is None:
            return
        # Snapshot under the lock so the icon and title can't disagree
        # if state flips between the two reads (rare with the GIL, but
        # the post-stop() invariant is "is_speaking is only mutated
        # under engine.lock" — keep readers honest too).
        with engine.lock:
            speaking = engine.is_speaking
        brand = config.get("brand_name", "PipPal")
        try:
            ic.icon = make_tray_icon(speaking)
            ic.title = f"{brand} — speaking" if speaking else brand
        except Exception:
            pass

    def tray_tick() -> None:
        update_tray_icon()
        root.after(TRAY_POLL_MS, tray_tick)
    root.after(TRAY_POLL_MS, tray_tick)

    def tray_action(fn: Callable[[], None]) -> Callable[[Any, Any], None]:
        """Adapt a no-arg engine method to pystray's (icon, item) signature."""
        return lambda _i, _it: fn()

    def quit_action(icon: Any, _item: Any) -> None:
        engine.stop()
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            icon.stop()
        except Exception:
            pass
        root.after(0, root.destroy)

    # Tray menu is composed from registered builders. Each builder
    # gets a context object (engine, config, overlay, settings, root,
    # quit_action, tray_action, save_config) and returns an iterable
    # of pystray items. The Free pippal package registers Recent,
    # Settings and Quit; pippal_pro adds Mood. Order is controlled by
    # the registered (zone, order) tuple — see plugins.tray_items().
    tray_ctx = SimpleNamespace(
        engine=engine,
        config=config,
        overlay=overlay,
        settings=settings,
        root=root,
        quit_action=quit_action,
        tray_action=tray_action,
        save_config=save_config,
        history_submenu_builder=_build_history_submenu(
            engine, tray_action(engine.clear_history),
        ),
    )
    composed: list[Any] = []
    for builder in plugins.tray_items():
        composed.extend(builder(tray_ctx))

    icon = pystray.Icon(
        "pippal",
        make_tray_icon(False),
        config.get("brand_name", "PipPal"),
        pystray.Menu(*composed),
    )
    tray["icon"] = icon
    icon.run_detached()

    try:
        root.mainloop()
    finally:
        try:
            icon.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
