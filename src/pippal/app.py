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

import pystray

from . import plugins
from .command_server import start_command_server
from .config import load_config, save_config
from .engine import TTSEngine
from .history import load_history, save_history
from .paths import CMD_SERVER_PORT, PIPER_EXE, ensure_dirs
from .timing import TRAY_POLL_MS
from .tray import make_tray_icon
from .ui import Overlay, SettingsWindow

# Keep a hard reference to the Tk PhotoImage so the GC doesn't collect
# it out from under the title bars. tk.PhotoImage objects have to
# outlive the window that uses them.
_ICON_PHOTO_REF: Any = None


def _set_app_user_model_id() -> None:
    """Tell Windows to group our windows under our own taskbar entry,
    not under pythonw.exe. Without this, the Settings window's task-
    bar slot shows the generic Python icon instead of the PipPal
    one. Must run BEFORE any Tk window is created — Windows reads
    the AppUserModelID at window creation time."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "BugFactory.PipPal.0"
        )
    except Exception as e:
        print(f"[icon] could not set AppUserModelID: {e}", file=sys.stderr)


def _set_window_icon(root: tk.Tk) -> None:
    """Set the title-bar icon for the Tk root (and, with default=True,
    every Toplevel that follows). PipPal uses the same PNG asset that
    the tray icon does — bbox-cropped and padded to a square so the
    title bar shows the character filling the cell, not floating in
    transparent margins."""
    global _ICON_PHOTO_REF
    try:
        from .paths import ASSET_ICON_PATH
        from .tray import _load_and_fit_icon
        if not ASSET_ICON_PATH.exists():
            return
        # 64×64 already cropped + squared by the tray helper. Reuse so
        # the title bar matches the system tray exactly.
        from PIL import ImageTk  # type: ignore[import-untyped]
        photo = ImageTk.PhotoImage(_load_and_fit_icon())
        _ICON_PHOTO_REF = photo  # keep alive
        root.iconphoto(True, photo)
    except Exception as e:
        print(f"[icon] could not set Tk window icon: {e}", file=sys.stderr)


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


def _another_instance_running() -> bool:
    """True when something else already holds the PipPal IPC port.

    PipPal is a tray app — running two copies is never useful, just
    confusing (two icons, double-played audio, fighting over hotkeys).
    The IPC port doubles as a cheap mutex: if we can't bind, somebody
    else is up. Avoids pulling in a Win32 mutex just for this."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            s.bind(("127.0.0.1", CMD_SERVER_PORT))
        return False
    except OSError:
        return True


def main() -> None:
    if _another_instance_running():
        # Surface a tiny modal so the user understands why "nothing
        # happened" when they clicked the Start menu shortcut a second
        # time — they should look in the system tray instead.
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None,
                "PipPal is already running.\n\n"
                "Look for the icon in the system tray (next to the clock).",
                "PipPal",
                0x40,  # MB_ICONINFORMATION
            )
        except Exception:
            pass
        sys.exit(0)

    ensure_dirs()
    config = load_config()

    # piper.exe is only required when Piper is actually selected;
    # users on a non-Piper engine (extension-supplied) can run with
    # the Piper binary absent.
    engine_name = (config.get("engine") or "piper").lower()
    if engine_name == "piper" and not PIPER_EXE.exists():
        print(
            f"piper.exe missing at {PIPER_EXE}; run setup.ps1 or "
            "switch engine in Settings.",
            file=sys.stderr,
        )
        sys.exit(1)

    _set_app_user_model_id()  # must run BEFORE the first Tk window
    root = tk.Tk()
    root.withdraw()
    _set_window_icon(root)

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
    #   2. Plugin-registered actions, looked up in
    #      ``plugins.plugin_actions()``. When an extension is loaded
    #      those are populated; otherwise they're empty and the
    #      corresponding hotkeys simply skip binding.
    builtin_handlers: dict[str, Callable[[], None]] = {
        "speak": engine.speak_selection_async,
        "queue": engine.queue_selection_async,
        "pause": engine.pause_toggle,
        "stop":  engine.stop,
    }

    def _resolve_handler(action_id: str) -> Callable[[], None] | None:
        if action_id in builtin_handlers:
            return builtin_handlers[action_id]
        ext = plugins.get_plugin_action(action_id)
        if ext is not None:
            # Route plugin-registered actions through the engine method
            # rather than calling the handler directly. The engine
            # method ``_async``-wraps (so hotkey / tray threads don't
            # block) and runs the no-voice gate (so a plugin action
            # whose synth would silently fail plays the onboarding
            # clip instead). Calling the handler directly would skip
            # both behaviours.
            return lambda aid=action_id: engine.dispatch_plugin_action(aid)
        # Legacy path: the engine still carries `speak_<action>_async`
        # methods kept for backwards compatibility until extension
        # plugins move every selection-driven flow over.
        legacy = getattr(engine, f"speak_{action_id}_async", None)
        return legacy if callable(legacy) else None

    # Low-level keyboard hook with a strict exact-match dispatcher
    # (see pippal.hotkey). Two earlier approaches were tried and
    # rejected:
    #
    #   - `keyboard.add_hotkey(combo, fn, suppress=True)` had a
    #     partial-prefix matching quirk that ate unrelated combos
    #     like Win+Shift+S (Snipping Tool) once we had any
    #     Win+Shift+... hotkey registered.
    #   - Win32 `RegisterHotKey` is first-come-first-served across
    #     the machine: PowerToys / Teams / OneDrive routinely claim
    #     Win+Shift+... combos at startup, leaving us with
    #     ERROR_HOTKEY_ALREADY_REGISTERED (1409).
    #
    # The current LL-hook approach: we see every keystroke before
    # Windows routes it, suppress only the *exact* combos we own,
    # and pass everything else through unchanged.
    from .hotkey import HotkeyManager
    hotkey_manager = HotkeyManager()
    hotkey_manager.start()
    # Unhook on exit so we don't leave a Windows hook installed
    # against a dead process.
    import atexit
    atexit.register(hotkey_manager.stop)

    def bind_hotkeys() -> list[tuple[str, str, str]]:
        """Re-bind every configured hotkey. Returns a list of
        `(action_id, combo, error)` for any combo we couldn't parse
        so the Settings UI can warn the user instead of silently
        saving a broken value."""
        hotkey_manager.unregister_all()
        for action_id, key, _label, default_combo in plugins.hotkey_actions():
            combo = config.get(key, default_combo)
            fn = _resolve_handler(action_id)
            if not combo or fn is None:
                continue
            hotkey_manager.register(combo, fn)
        failures: list[tuple[str, str, str]] = []
        for combo, reason in hotkey_manager.failures():
            aid = next(
                (a for a, k, _l, _d in plugins.hotkey_actions()
                 if config.get(k, _d) == combo),
                "?",
            )
            failures.append((aid, combo, reason))
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
            hotkey_manager.unregister_all()
            hotkey_manager.stop()
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
    # of pystray items. The core pippal package registers Recent,
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
