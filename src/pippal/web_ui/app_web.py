"""Web-frontend application composition — PipPal's only entry point.

Load config, build the real ``TTSEngine``, register the native global
hotkeys, build the native pystray tray — and host the **windows** as
pywebview (WebView2) windows serving the static UI in ``webui/``.

System tray + global hotkey are native: ``pystray`` and ``keyboard``.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Any

import pystray

from .. import plugins
from ..command_server import start_command_server
from ..config import load_config
from ..engine import TTSEngine
from ..history import load_history, save_history
from ..onboarding import should_show_activation_panel
from ..paths import PIPER_EXE, ensure_dirs
from ..tray import make_tray_icon
from .bridge import PipPalBridge
from .overlay_state import WebOverlay
from .server import start_web_ui_server
from .startup_toast import show_startup_toast
from .windows import WebWindowManager


def _selected_piper_missing(config: dict[str, Any]) -> bool:
    engine_name = str(config.get("engine") or "piper").lower()
    return engine_name == "piper" and not PIPER_EXE.exists()


def build_tray_menu(
    *,
    engine: Any,
    config: dict[str, Any],
    windows: Any,
    hotkey_manager: Any,
) -> tuple[pystray.Menu, dict[str, Any]]:
    """Compose the native pystray menu the web app runs in the tray.

    Extracted verbatim from :func:`main` so the *exact same* menu and
    callables can be exercised head-less by the integration suite (a
    ``pystray.MenuItem`` is callable — ``item(icon)`` is precisely the
    dispatch a real tray click performs, minus the OS pixel rendering).

    Returns ``(menu, primitives)``; ``primitives`` exposes the bound
    callables (``quit_action``, ``history_submenu``, ...) so a test can
    assert their real effect without re-deriving them. ``main`` only
    consumes ``menu`` — behaviour is unchanged.
    """

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
        windows.shutdown()

    def replay_handler(text: str) -> Callable[[Any, Any], None]:
        return lambda _i, _it: engine.replay_text(text)

    def history_submenu() -> list[pystray.MenuItem]:
        items = engine.get_history()
        if not items:
            return [pystray.MenuItem("(empty)", lambda _i, _it: None, enabled=False)]
        out = []
        for t in items[:10]:
            preview = t.replace("\n", " ").strip()
            if len(preview) > 70:
                preview = preview[:67] + "…"
            out.append(pystray.MenuItem(preview, replay_handler(t)))
        out.append(pystray.Menu.SEPARATOR)
        out.append(
            pystray.MenuItem("Clear history", lambda _i, _it: engine.clear_history())
        )
        return out

    menu = pystray.Menu(
        pystray.MenuItem("Recent", pystray.Menu(history_submenu)),
        pystray.MenuItem("First-run check", lambda _i, _it: windows.open("onboarding")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Settings…",
            lambda _i, _it: windows.open("settings"),
            default=True,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_action),
    )
    primitives = {
        "quit_action": quit_action,
        "history_submenu": history_submenu,
        "replay_handler": replay_handler,
    }
    return menu, primitives


def main() -> None:
    ensure_dirs()
    config = load_config()

    if _selected_piper_missing(config):
        print(
            f"piper.exe missing at {PIPER_EXE}; run setup.ps1 or "
            "switch engine in Settings.",
            file=sys.stderr,
        )

    # ----- Backend -----
    overlay = WebOverlay(config)
    engine = TTSEngine(config=config, root=_NullRoot(), overlay_ref=lambda: overlay)
    engine.attach_history(load_history(), save_history)

    # ----- Hotkeys (native HotkeyManager) -----
    from ..hotkey import HotkeyManager, duplicate_combo_failures

    hotkey_manager = HotkeyManager()
    hotkey_manager.start()
    import atexit

    atexit.register(hotkey_manager.stop)

    builtin_handlers = {
        "speak": engine.speak_selection_async,
        "queue": engine.queue_selection_async,
        "pause": engine.pause_toggle,
        "stop": engine.stop,
    }

    def _resolve_handler(action_id: str):
        if action_id in builtin_handlers:
            return builtin_handlers[action_id]
        ext = plugins.get_plugin_action(action_id)
        if ext is not None:
            return lambda aid=action_id: engine.dispatch_plugin_action(aid)
        legacy = getattr(engine, f"speak_{action_id}_async", None)
        return legacy if callable(legacy) else None

    def bind_hotkeys() -> list[tuple[str, str, str]]:
        hotkey_manager.unregister_all()
        actions = plugins.hotkey_actions()
        failures = duplicate_combo_failures(config, actions)
        dup = {aid for aid, _c, _r in failures}
        for action_id, key, _label, default_combo in actions:
            if action_id in dup:
                continue
            combo = config.get(key, default_combo)
            fn = _resolve_handler(action_id)
            if not combo or fn is None:
                continue
            hotkey_manager.register(combo, fn)
        for combo, reason in hotkey_manager.failures():
            aid = next(
                (a for a, k, _l, _d in actions if config.get(k, _d) == combo),
                "?",
            )
            failures.append((aid, combo, reason))
        return failures

    bind_hotkeys()

    # ----- Bridge + local static/JSON server -----
    windows = WebWindowManager()
    bridge = PipPalBridge(
        engine,
        config,
        overlay,
        on_open_settings=lambda: windows.open("settings"),
        on_open_voice_manager=lambda: windows.open("voices"),
        on_open_notices=lambda: windows.open("notices"),
        on_close_window=windows.close_active,
        on_hotkey_change=bind_hotkeys,
        on_engine_change=engine.reset_backend,
    )
    _server, port = start_web_ui_server(bridge)
    base_url = f"http://127.0.0.1:{port}"
    windows.configure(base_url, bridge)

    # ----- Local IPC / single-instance gate -----
    command_callbacks = {
        "settings": lambda: windows.open("settings"),
        "stop": engine.stop,
        "pause": engine.pause_toggle,
        "prev": engine.prev_chunk,
        "replay": engine.replay_chunk,
        "next": engine.next_chunk,
        "voice-manager": lambda: windows.open("voices"),
        "first-run-check": lambda: windows.open("onboarding"),
    }
    cmd_server = start_command_server(engine, commands=command_callbacks)
    if cmd_server is None:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                "PipPal is already running.\n\nLook for the icon in the "
                "system tray (next to the clock).",
                "PipPal",
                0x40,
            )
        except Exception:
            pass
        raise SystemExit(0)

    # ----- Tray (native pystray) -----
    tray: dict[str, Any] = {"icon": None}

    def update_tray_icon() -> None:
        ic = tray.get("icon")
        if ic is None:
            return
        with engine.lock:
            speaking = engine.is_speaking
        brand = config.get("brand_name", "PipPal")
        try:
            ic.icon = make_tray_icon(speaking)
            ic.title = f"{brand} — speaking" if speaking else brand
        except Exception:
            pass

    def tray_poll() -> None:
        while True:
            update_tray_icon()
            threading.Event().wait(1.0)

    threading.Thread(target=tray_poll, daemon=True).start()

    menu, _tray_primitives = build_tray_menu(
        engine=engine,
        config=config,
        windows=windows,
        hotkey_manager=hotkey_manager,
    )
    icon = pystray.Icon(
        "pippal",
        make_tray_icon(False),
        config.get("brand_name", "PipPal"),
        menu,
    )
    tray["icon"] = icon
    icon.run_detached()

    # Show a brief "running in background" toast once at startup.
    # Fires ~200 ms after the tray icon is ready; silently skipped in CI
    # (PIPPAL_NO_STARTUP_NOTIFICATION=1) and on any display error.
    show_startup_toast()

    if _selected_piper_missing(config) or should_show_activation_panel():
        windows.open("onboarding")

    # pywebview MUST own the main thread. windows.run() blocks here until
    # the last window closes / shutdown() is called.
    try:
        windows.run()
    finally:
        try:
            icon.stop()
        except Exception:
            pass


class _NullRoot:
    """Stand-in for the Tk root the engine takes for thread hops.

    The engine calls ``root.after(ms, fn)`` to bounce work onto the Tk
    UI thread. ``WebOverlay`` is thread-safe and owns its OWN auto-hide
    timer, so an ``ms == 0`` immediate hop runs inline (same net effect
    as the engine's thread-hop). A ``ms > 0`` call is a genuinely
    *delayed* callback — running it inline would fire it immediately
    (this is exactly the ``auto_hide_ms`` regression). So a timed call
    schedules a real ``threading.Timer`` and exposes ``after_cancel``
    for parity with Tk's cancellable ``after`` ids.
    """

    def __init__(self) -> None:
        self._timers: dict[int, threading.Timer] = {}
        self._next_id = 1

    def after(self, ms: int, fn=None, *args: Any) -> str | None:
        if fn is None:
            return None
        if not ms or ms <= 0:
            try:
                fn(*args)
            except Exception:
                pass
            return None
        tid = self._next_id
        self._next_id += 1

        def _run() -> None:
            self._timers.pop(tid, None)
            try:
                fn(*args)
            except Exception:
                pass

        t = threading.Timer(ms / 1000.0, _run)
        t.daemon = True
        self._timers[tid] = t
        t.start()
        return str(tid)

    def after_cancel(self, tid: str | None) -> None:
        if tid is None:
            return
        try:
            t = self._timers.pop(int(tid), None)
        except (TypeError, ValueError):
            return
        if t is not None:
            t.cancel()


if __name__ == "__main__":
    main()
