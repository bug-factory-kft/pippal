"""PipPal PySide6 application composition (migration spike).

This is the Qt analogue of ``pippal.app.main``: load config, create
the QApplication, the overlay, the engine, register global hotkeys
(reusing ``keyboard``), start the local IPC command server, build the
tray, run the Qt event loop. The backend modules (engine, config,
voices, history, playback, command_server, onboarding, hotkey,
plugins) are reused unchanged.

The Tk entrypoint ``pippal.app.main`` is untouched and still the
default; this module is the parallel frontend selected via
``reader_app_qt.py`` / ``python -m pippal.app_qt``.

A small ``_QtRoot`` shim gives the engine/command-server code the one
method they expect from a Tk root — ``after(ms, fn)`` — implemented by
marshalling onto the Qt GUI thread. That keeps the shared backend
contract identical to the Tk build instead of forking it."""

from __future__ import annotations

import os
import sys
import threading
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from . import plugins
from .command_server import start_command_server
from .config import load_config, save_config
from .engine import TTSEngine
from .history import load_history, save_history
from .onboarding import should_show_activation_panel
from .paths import PIPER_EXE, ensure_dirs
from .timing import TRAY_POLL_MS
from .ui_qt import (
    QtActivationPanel,
    QtOverlay,
    QtSettingsWindow,
    QtTray,
    apply_app_theme,
)

_E2E_COMMAND_SERVER_ENV = "PIPPAL_E2E_COMMAND_SERVER"


def _e2e_command_server_enabled() -> bool:
    return os.environ.get(_E2E_COMMAND_SERVER_ENV) == "1"


def _selected_piper_missing(config: dict[str, Any]) -> bool:
    engine_name = str(config.get("engine") or "piper").lower()
    return engine_name == "piper" and not PIPER_EXE.exists()


class _QtRoot(QObject):
    """Minimal Tk-root stand-in.

    The engine's ``_RootProto`` only needs ``after(ms, fn)``. The
    command server's ``_call_on_tk_thread`` needs the same hop to run
    UI mutations on the GUI thread. We implement it with a queued
    signal so calls from worker threads land on the Qt main thread,
    exactly like ``tk.Tk.after``'s scheduling guarantee."""

    _invoke = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._invoke.connect(lambda fn: fn())

    def after(self, ms: int, fn: Any, *args: Any) -> None:
        def call() -> None:
            fn(*args)
        if ms <= 0:
            self._invoke.emit(call)
        else:
            # singleShot must be armed on the GUI thread.
            self._invoke.emit(lambda: QTimer.singleShot(int(ms), call))

    def call_on_gui_thread(self, fn: Any, timeout: float = 5.0) -> Any:
        """Run ``fn`` on the GUI thread and return its result.

        The shared command-server adapters mutate widgets, so they must
        run on the GUI thread; the HTTP handler thread blocks on the
        result here — the Qt analogue of ``app._call_on_tk_thread``."""
        done = threading.Event()
        box: dict[str, Any] = {}

        def run() -> None:
            try:
                box["value"] = fn()
            except BaseException as exc:
                box["error"] = exc
            finally:
                done.set()

        self._invoke.emit(run)
        if not done.wait(timeout):
            raise RuntimeError("Qt GUI thread did not answer in time")
        if "error" in box:
            raise box["error"]
        return box.get("value")


def _show_already_running_message() -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "PipPal is already running.\n\nLook for the icon in the "
            "system tray (next to the clock).",
            "PipPal", 0x40,
        )
    except Exception:
        pass


def main() -> None:
    ensure_dirs()
    config = load_config()

    if _selected_piper_missing(config):
        print(
            f"piper.exe missing at {PIPER_EXE}; run setup.ps1 or switch "
            "engine in Settings. Starting repair state.",
            file=sys.stderr,
        )

    app = QApplication.instance() or QApplication(sys.argv)
    apply_app_theme(app)
    app.setApplicationName(str(config.get("brand_name", "PipPal")))
    app.setQuitOnLastWindowClosed(False)

    root = _QtRoot()

    overlay_box: list[QtOverlay | None] = [None]
    engine = TTSEngine(root, config, overlay_ref=lambda: overlay_box[0])

    overlay = QtOverlay(
        config,
        on_stop=engine.stop,
        on_prev=engine.prev_chunk,
        on_replay=engine.replay_chunk,
        on_next=engine.next_chunk,
    )
    overlay_box[0] = overlay
    engine.attach_history(load_history(), save_history)

    settings_box: list[QtSettingsWindow | None] = [None]
    activation_box: list[QtActivationPanel | None] = [None]

    # ----- Hotkeys (reuse pippal.hotkey + the keyboard backend) -----
    from .hotkey import HotkeyManager, duplicate_combo_failures
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
        duplicate_ids = {aid for aid, _c, _r in failures}
        for action_id, key, _label, default_combo in actions:
            if action_id in duplicate_ids:
                continue
            combo = config.get(key, default_combo)
            fn = _resolve_handler(action_id)
            if not combo or fn is None:
                continue
            hotkey_manager.register(combo, fn)
        for combo, reason in hotkey_manager.failures():
            aid = next(
                (a for a, k, _l, _d in actions
                 if config.get(k, _d) == combo), "?")
            failures.append((aid, combo, reason))
        return failures

    bind_hotkeys()

    # ----- Settings window -----
    settings = QtSettingsWindow(
        config,
        on_save=save_config,
        on_hotkey_change=bind_hotkeys,
        on_engine_change=engine.reset_backend,
    )
    settings_box[0] = settings

    def open_settings_command() -> None:
        root.after(0, settings.open)

    def voice_manager_command() -> None:
        def _open() -> None:
            settings.open()
            settings._open_voice_manager()
        root.after(0, _open)

    def open_setup_instructions() -> None:
        import webbrowser
        webbrowser.open("https://github.com/bug-factory-kft/pippal#readme")

    def open_activation_panel() -> None:
        def _open() -> None:
            panel = activation_box[0]
            if panel is None:
                def _vm_from_first_run() -> None:
                    settings.open()
                    cur = activation_box[0]
                    settings._open_voice_manager(
                        on_installed=(cur.apply_installed_voice
                                      if cur is not None else None))
                panel = QtActivationPanel(
                    config,
                    on_play_sample=engine.read_text_async,
                    on_open_settings=settings.open,
                    on_open_voice_manager=_vm_from_first_run,
                    on_open_setup=open_setup_instructions,
                )
                activation_box[0] = panel
            panel.open()
        root.after(0, _open)

    # ----- Command server (same control surface as the Tk build) -----
    from .qt_command_adapters import build_command_callbacks
    callbacks = build_command_callbacks(
        root, engine, config, settings_box, overlay_box,
        activation_box, open_activation_panel,
        open_settings_command, voice_manager_command,
    )
    server = start_command_server(
        engine,
        commands=callbacks["commands"],
        json_commands=callbacks["json_commands"],
        queries=callbacks["queries"],
        control_routes_enabled=_e2e_command_server_enabled(),
    )
    if server is None:
        _show_already_running_message()
        raise SystemExit(0)

    # ----- Tray -----
    tray_holder: dict[str, Any] = {}

    def do_quit() -> None:
        engine.stop()
        try:
            hotkey_manager.unregister_all()
            hotkey_manager.stop()
        except Exception:
            pass
        t = tray_holder.get("tray")
        if t is not None:
            t.stop()
        try:
            server.shutdown()
        except Exception:
            pass
        app.quit()

    tray = QtTray(
        brand=str(config.get("brand_name", "PipPal")),
        engine=engine,
        on_settings=lambda: root.after(0, settings.open),
        on_first_run_check=open_activation_panel,
        on_quit=lambda: root.after(0, do_quit),
    )
    tray_holder["tray"] = tray

    def tray_tick() -> None:
        with engine.lock:
            speaking = engine.is_speaking
        tray.update_speaking(speaking)

    poll = QTimer()
    poll.setInterval(TRAY_POLL_MS)
    poll.timeout.connect(tray_tick)
    poll.start()

    if _selected_piper_missing(config) or should_show_activation_panel():
        QTimer.singleShot(500, open_activation_panel)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
