"""PipPal application composition.

This is where the parts wire up: load config, create the Tk root, the
overlay and the engine, register hotkeys, build the tray menu, start
the local IPC server, run the Tk mainloop."""

from __future__ import annotations

import os
import sys
import threading
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
from .onboarding import should_show_activation_panel
from .paths import PIPER_EXE, ensure_dirs
from .timing import TRAY_POLL_MS
from .tray import make_tray_icon
from .ui import Overlay, SettingsWindow
from .ui.activation_panel import FirstRunActivationPanel

# Keep a hard reference to the Tk PhotoImage so the GC doesn't collect
# it out from under the title bars. tk.PhotoImage objects have to
# outlive the window that uses them.
_ICON_PHOTO_REF: Any = None
_E2E_COMMAND_SERVER_ENV = "PIPPAL_E2E_COMMAND_SERVER"


def _e2e_command_server_enabled() -> bool:
    return os.environ.get(_E2E_COMMAND_SERVER_ENV) == "1"


def _widget_texts(widget: tk.Misc) -> list[str]:
    texts: list[str] = []
    try:
        text = str(widget.cget("text")).strip()  # type: ignore[attr-defined]
    except Exception:
        text = ""
    if text:
        texts.append(text)
    for child in widget.winfo_children():
        texts.extend(_widget_texts(child))
    return texts


def _widget_option(widget: tk.Misc, option: str) -> Any:
    try:
        return widget.cget(option)  # type: ignore[attr-defined]
    except Exception:
        return None


def _widget_label(widget: tk.Misc) -> str:
    parent = widget.master
    if parent is None:
        return ""
    label = ""
    try:
        siblings = parent.winfo_children()
    except Exception:
        return ""
    for sibling in siblings:
        if sibling is widget:
            break
        text = _widget_option(sibling, "text")
        if text:
            label = str(text).strip()
    return label


def _widget_variable_key(
    widget: tk.Misc,
    var_keys: dict[str, str] | None,
) -> str:
    if not var_keys:
        return ""
    for option in ("textvariable", "variable"):
        raw = _widget_option(widget, option)
        key = var_keys.get(str(raw)) if raw else None
        if key:
            return key
    return ""


def _widget_value(widget: tk.Misc) -> Any:
    try:
        if hasattr(widget, "get"):
            return widget.get()  # type: ignore[attr-defined]
    except Exception:
        return None
    return None


def _widget_controls(
    widget: tk.Misc,
    var_keys: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    class_name = ""
    try:
        class_name = widget.winfo_class()
    except Exception:
        pass
    text = _widget_option(widget, "text")
    state = _widget_option(widget, "state")
    values = _widget_option(widget, "values")
    variable_key = _widget_variable_key(widget, var_keys)
    role_by_class = {
        "TButton": "button",
        "Button": "button",
        "TEntry": "input",
        "Entry": "input",
        "TSpinbox": "input",
        "Spinbox": "input",
        "TCombobox": "select",
        "TCheckbutton": "checkbox",
        "Checkbutton": "checkbox",
        "TScale": "slider",
        "Scale": "slider",
        "Text": "text",
    }
    role = role_by_class.get(class_name, "")
    if role or text or variable_key:
        control: dict[str, Any] = {
            "path": str(widget),
            "class": class_name,
            "role": role,
            "text": str(text).strip() if text is not None else "",
            "label": _widget_label(widget),
            "state": str(state) if state is not None else "",
            "value": _widget_value(widget),
            "variable": variable_key,
            "visible": bool(widget.winfo_viewable()),
        }
        if values is not None:
            control["values"] = list(values) if isinstance(values, tuple) else values
        controls.append(control)

    for child in widget.winfo_children():
        controls.extend(_widget_controls(child, var_keys))
    return controls


def _toplevels(
    root: tk.Misc,
    var_keys: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for widget in _iter_widgets(root):
        if not isinstance(widget, tk.Toplevel):
            continue
        try:
            exists = bool(widget.winfo_exists())
            visible = bool(widget.winfo_viewable())
            title = str(widget.title())
        except Exception:
            continue
        if not exists:
            continue
        windows.append({
            "title": title,
            "visible": visible,
            "texts": _widget_texts(widget),
            "controls": _widget_controls(widget, var_keys),
        })
    return windows


def _iter_widgets(widget: tk.Misc) -> list[tk.Misc]:
    out = [widget]
    for child in widget.winfo_children():
        out.extend(_iter_widgets(child))
    return out


def _target_windows(root: tk.Misc, target: dict[str, Any]) -> list[tk.Misc]:
    title = str(target.get("title", "")).lower()
    if not title:
        return [root]
    windows: list[tk.Misc] = []
    for widget in _iter_widgets(root):
        if not isinstance(widget, tk.Toplevel):
            continue
        try:
            widget_title = str(widget.title()).lower()
        except Exception:
            continue
        if title in widget_title:
            windows.append(widget)
    return windows


def _target_matches(
    widget: tk.Misc,
    target: dict[str, Any],
    var_keys: dict[str, str],
) -> bool:
    path = target.get("path")
    if path and str(widget) != str(path):
        return False
    class_name = target.get("class")
    if class_name and widget.winfo_class() != str(class_name):
        return False
    role = target.get("role")
    if role:
        control = _widget_controls(widget, var_keys)
        if not control or control[0].get("role") != role:
            return False
    text = target.get("text")
    if text is not None and str(_widget_option(widget, "text")).strip() != str(text):
        return False
    label = target.get("label")
    if label is not None and _widget_label(widget).lower() != str(label).lower():
        return False
    var_key = target.get("var_key") or target.get("variable")
    if var_key and _widget_variable_key(widget, var_keys) != str(var_key):
        return False
    return True


def _find_widget(
    root: tk.Misc,
    target: dict[str, Any],
    var_keys: dict[str, str],
) -> tk.Misc:
    matches: list[tk.Misc] = []
    for window in _target_windows(root, target):
        for widget in _iter_widgets(window):
            try:
                if _target_matches(widget, target, var_keys):
                    matches.append(widget)
            except Exception:
                continue
    visible = [widget for widget in matches if widget.winfo_viewable()]
    found = visible or matches
    if not found:
        raise RuntimeError(f"UI target not found: {target}")
    index = int(target.get("index", 0) or 0)
    try:
        return found[index]
    except IndexError as exc:
        raise RuntimeError(f"UI target index out of range: {target}") from exc


def _audio_chunks(paths: list[Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for path in paths:
        info: dict[str, Any] = {
            "path": str(path),
            "exists": False,
            "size": 0,
            "riff_wave": False,
        }
        try:
            exists = path.exists()
            info["exists"] = bool(exists)
            if exists:
                info["size"] = path.stat().st_size
                with path.open("rb") as handle:
                    header = handle.read(12)
                info["riff_wave"] = header[:4] == b"RIFF" and header[8:12] == b"WAVE"
        except OSError as exc:
            info["error"] = str(exc)
        chunks.append(info)
    return chunks


def _call_on_tk_thread(root: tk.Misc, fn: Callable[[], Any], timeout: float = 2.0) -> Any:
    done = threading.Event()
    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:
            result["error"] = exc
        finally:
            done.set()

    root.after(0, run)
    if not done.wait(timeout):
        raise RuntimeError("Tk thread did not answer in time")
    if "error" in result:
        raise result["error"]
    return result.get("value")


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


def _show_already_running_message() -> None:
    """Tell the user why a second app launch did not open a new window."""
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


def _require_command_server(
    engine: TTSEngine,
    root: tk.Tk | None = None,
    commands: dict[str, Callable[[], None]] | None = None,
    json_commands: dict[str, Callable[[dict[str, Any]], Any]] | None = None,
    queries: dict[str, Callable[[], Any]] | None = None,
    control_routes_enabled: bool = False,
) -> Any:
    """Start the local listener and treat it as the single-instance owner."""
    if commands is None and json_commands is None and queries is None:
        if control_routes_enabled:
            server = start_command_server(
                engine,
                control_routes_enabled=control_routes_enabled,
            )
        else:
            server = start_command_server(engine)
    else:
        server = start_command_server(
            engine,
            commands=commands,
            json_commands=json_commands,
            queries=queries,
            control_routes_enabled=control_routes_enabled,
        )
    if server is not None:
        return server

    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass
    _show_already_running_message()
    raise SystemExit(0)


def main() -> None:

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

    # Local IPC server for the right-click context-menu helper. The
    # listener also owns the single-instance gate: if the port cannot
    # be bound, exit before registering hotkeys or adding a tray icon.
    settings_box: list[SettingsWindow | None] = [None]
    activation_panel_box: list[FirstRunActivationPanel | None] = [None]

    def open_settings_command() -> None:
        settings = settings_box[0]
        if settings is None:
            raise RuntimeError("settings window is not ready")
        root.after(0, settings.open)

    def runtime_snapshot() -> dict[str, Any]:
        settings = settings_box[0]
        overlay_current = overlay_box[0]
        settings_open = bool(
            settings is not None
            and settings.win is not None
            and settings.win.winfo_exists()
        )
        settings_texts = (
            _widget_texts(settings.win)
            if settings_open and settings is not None and settings.win is not None
            else []
        )
        settings_vars = {
            key: var.get()
            for key, var in (settings.vars.items() if settings is not None else [])
        }
        var_keys = {
            str(var): key
            for key, var in (settings.vars.items() if settings is not None else [])
        }
        with engine.lock:
            chunk_paths = list(engine._chunk_paths)
            backend_cls = engine._backend_cls
            playback_state = {
                "backend_name": engine._backend_name,
                "backend_class": backend_cls.__name__ if backend_cls is not None else None,
                "chunks": list(engine._chunks),
                "chunk_idx": engine._chunk_idx,
                "chunk_paths": [str(path) for path in chunk_paths],
                "is_speaking": bool(engine.is_speaking),
                "is_paused": bool(engine._is_paused),
                "queue_length": len(engine._queue),
                "token": engine.token,
            }
        playback_state["audio_chunks"] = _audio_chunks(chunk_paths)
        overlay_state: dict[str, Any] = {}
        if overlay_current is not None:
            try:
                overlay_state = {
                    "overlay_visible": bool(overlay_current.win.winfo_viewable()),
                    "overlay_state": overlay_current.state,
                    "overlay_buttons": sorted(overlay_current._btn_rects),
                    "overlay_action_label": overlay_current.action_label,
                    "overlay_message": overlay_current.message,
                }
            except Exception as exc:
                overlay_state = {"overlay_error": str(exc)}
        return {
            "settings_open": settings_open,
            "settings_texts": settings_texts,
            "settings_vars": settings_vars,
            "windows": _toplevels(root, var_keys),
            "controls": _widget_controls(root, var_keys),
            "config": dict(config),
            "history": engine.get_history(),
            **overlay_state,
            **playback_state,
            "engines": sorted(plugins.engines()),
            "plugin_actions": sorted(plugins.plugin_actions()),
            "hotkey_actions": [
                action_id for action_id, _key, _label, _default in plugins.hotkey_actions()
            ],
            "settings_cards": [
                f"{callback.__module__}.{getattr(callback, '__name__', '<callable>')}"
                for callback in plugins.settings_cards()
            ],
            "tray_items": [
                f"{callback.__module__}.{getattr(callback, '__name__', '<callable>')}"
                for callback in plugins.tray_items()
            ],
        }

    def state_query() -> dict[str, Any]:
        return _call_on_tk_thread(root, runtime_snapshot)

    def voice_manager_command() -> None:
        settings = settings_box[0]
        if settings is None:
            raise RuntimeError("settings window is not ready")
        root.after(0, lambda: (settings.open(), settings._open_voice_manager()))

    def open_setup_instructions() -> None:
        import webbrowser

        webbrowser.open("https://github.com/bug-factory-kft/pippal#readme")

    def open_activation_panel() -> None:
        def _open() -> None:
            settings = settings_box[0]
            if settings is None:
                raise RuntimeError("settings window is not ready")
            panel = activation_panel_box[0]
            if panel is None:
                panel = FirstRunActivationPanel(
                    root,
                    config,
                    on_play_sample=engine.read_text_async,
                    on_open_settings=settings.open,
                    on_open_voice_manager=lambda: (
                        settings.open(),
                        settings._open_voice_manager(),
                    ),
                    on_open_setup=open_setup_instructions,
                )
                activation_panel_box[0] = panel
            panel.open()

        root.after(0, _open)

    def apply_settings_command(data: dict[str, Any]) -> dict[str, Any]:
        values = data.get("values", {})
        if not isinstance(values, dict):
            raise RuntimeError("values must be an object")
        close = bool(data.get("close", False))

        def apply() -> dict[str, Any]:
            settings = settings_box[0]
            if settings is None:
                raise RuntimeError("settings window is not ready")
            settings.open()
            missing: list[str] = []
            pending_values = dict(values)
            engine_value = pending_values.pop("engine", None)
            if engine_value is not None:
                var = settings.vars.get("engine")
                if var is None:
                    missing.append("engine")
                else:
                    var.set(engine_value)
                    settings._on_engine_change()
            for key, value in pending_values.items():
                var = settings.vars.get(str(key))
                if var is None:
                    missing.append(str(key))
                    continue
                var.set(value)
            if missing:
                raise RuntimeError(f"unknown settings vars: {', '.join(missing)}")
            settings._persist(close=close)
            return runtime_snapshot()

        return _call_on_tk_thread(root, apply, timeout=5.0)

    def _settings_var_keys() -> dict[str, str]:
        settings = settings_box[0]
        if settings is None:
            return {}
        return {str(var): key for key, var in settings.vars.items()}

    def _coerce_var_value(var: tk.Variable, value: Any) -> Any:
        try:
            current = var.get()
        except Exception:
            return value
        if isinstance(current, bool):
            return bool(value)
        if isinstance(current, int) and not isinstance(current, bool):
            return int(value)
        if isinstance(current, float):
            return float(value)
        return str(value)

    def _after_ui_var_change(settings: SettingsWindow | None, key: str) -> None:
        if settings is None:
            return
        if key == "engine":
            settings._on_engine_change()
        elif key == "speed":
            settings._update_speed_label()
        elif key == "noise_scale":
            settings._update_var_label()

    def _with_dialog_defaults(fn: Callable[[], Any], *, confirm: bool = True) -> Any:
        import webbrowser
        from tkinter import messagebox

        originals = {
            "askyesno": messagebox.askyesno,
            "showinfo": messagebox.showinfo,
            "showwarning": messagebox.showwarning,
            "showerror": messagebox.showerror,
        }
        opened_urls: list[str] = []
        messagebox.askyesno = lambda *_a, **_kw: bool(confirm)  # type: ignore[method-assign]
        messagebox.showinfo = lambda *_a, **_kw: "ok"  # type: ignore[method-assign]
        messagebox.showwarning = lambda *_a, **_kw: "ok"  # type: ignore[method-assign]
        messagebox.showerror = lambda *_a, **_kw: "ok"  # type: ignore[method-assign]
        original_web_open = webbrowser.open
        webbrowser.open = (  # type: ignore[assignment]
            lambda url, *_a, **_kw: opened_urls.append(str(url)) or True
        )
        try:
            payload = fn()
            if isinstance(payload, dict) and opened_urls:
                payload["opened_urls"] = opened_urls
            return payload
        finally:
            messagebox.askyesno = originals["askyesno"]  # type: ignore[method-assign]
            messagebox.showinfo = originals["showinfo"]  # type: ignore[method-assign]
            messagebox.showwarning = originals["showwarning"]  # type: ignore[method-assign]
            messagebox.showerror = originals["showerror"]  # type: ignore[method-assign]
            webbrowser.open = original_web_open  # type: ignore[assignment]

    def ui_click_command(data: dict[str, Any]) -> dict[str, Any]:
        target = data.get("target", {})
        if not isinstance(target, dict):
            raise RuntimeError("target must be an object")
        target = {"role": "button", **target}
        confirm = bool(data.get("confirm", True))

        def click() -> dict[str, Any]:
            widget = _find_widget(root, target, _settings_var_keys())
            def invoke_or_click() -> dict[str, Any]:
                if hasattr(widget, "invoke"):
                    widget.invoke()  # type: ignore[attr-defined]
                else:
                    widget.event_generate("<Button-1>", x=1, y=1)
                root.update_idletasks()
                return runtime_snapshot()

            return _with_dialog_defaults(invoke_or_click, confirm=confirm)

        return _call_on_tk_thread(root, click, timeout=5.0)

    def ui_type_command(data: dict[str, Any]) -> dict[str, Any]:
        target = data.get("target", {})
        if not isinstance(target, dict):
            raise RuntimeError("target must be an object")
        text = str(data.get("text", ""))
        clear = bool(data.get("clear", True))

        def type_text() -> dict[str, Any]:
            widget = _find_widget(root, target, _settings_var_keys())
            if not (hasattr(widget, "delete") and hasattr(widget, "insert")):
                raise RuntimeError(f"UI target is not a text input: {target}")
            try:
                widget.focus_set()
            except Exception:
                pass
            if clear:
                widget.delete(0, "end")  # type: ignore[attr-defined]
            for ch in text:
                widget.insert("end", ch)  # type: ignore[attr-defined]
                root.update_idletasks()
            key = str(target.get("var_key") or target.get("variable") or "")
            _after_ui_var_change(settings_box[0], key)
            return runtime_snapshot()

        return _call_on_tk_thread(root, type_text, timeout=5.0)

    def ui_set_command(data: dict[str, Any]) -> dict[str, Any]:
        key = str(data.get("var_key") or data.get("variable") or "")
        if not key:
            raise RuntimeError("var_key is required")
        value = data.get("value")

        def set_value() -> dict[str, Any]:
            settings = settings_box[0]
            if settings is None:
                raise RuntimeError("settings window is not ready")
            var = settings.vars.get(key)
            if var is None:
                raise RuntimeError(f"unknown settings var: {key}")
            var.set(_coerce_var_value(var, value))
            _after_ui_var_change(settings, key)
            root.update_idletasks()
            return runtime_snapshot()

        return _call_on_tk_thread(root, set_value, timeout=5.0)

    def ui_select_command(data: dict[str, Any]) -> dict[str, Any]:
        target = data.get("target", {})
        if not isinstance(target, dict):
            raise RuntimeError("target must be an object")
        target = {"role": "select", **target}
        value = str(data.get("value", ""))

        def select_value() -> dict[str, Any]:
            widget = _find_widget(root, target, _settings_var_keys())
            if not hasattr(widget, "set"):
                raise RuntimeError(f"UI target is not selectable: {target}")
            widget.set(value)  # type: ignore[attr-defined]
            try:
                widget.event_generate("<<ComboboxSelected>>")
            except Exception:
                pass
            key = str(target.get("var_key") or target.get("variable") or "")
            _after_ui_var_change(settings_box[0], key)
            root.update_idletasks()
            return runtime_snapshot()

        return _call_on_tk_thread(root, select_value, timeout=5.0)

    def ui_overlay_click_command(data: dict[str, Any]) -> dict[str, Any]:
        tag = str(data.get("tag", ""))
        if tag not in {"close", "prev", "replay", "next"}:
            raise RuntimeError("tag must be one of: close, prev, replay, next")

        def click_overlay() -> dict[str, Any]:
            overlay = overlay_box[0]
            if overlay is None:
                raise RuntimeError("overlay is not ready")
            if tag == "close":
                x1, y1, x2, y2 = overlay._CLOSE_BTN_RECT
            else:
                rect = overlay._btn_rects.get(tag)
                if rect is None:
                    raise RuntimeError(f"overlay button is not visible: {tag}")
                x1, y1, x2, y2 = rect
            overlay._on_click(SimpleNamespace(x=(x1 + x2) // 2, y=(y1 + y2) // 2))
            root.update_idletasks()
            return runtime_snapshot()

        return _call_on_tk_thread(root, click_overlay, timeout=5.0)

    command_callbacks = {
        "settings": open_settings_command,
        "stop": engine.stop,
        "pause": engine.pause_toggle,
        "prev": engine.prev_chunk,
        "replay": engine.replay_chunk,
        "next": engine.next_chunk,
        "voice-manager": voice_manager_command,
        "first-run-check": open_activation_panel,
    }
    json_command_callbacks = {
        "settings.apply": apply_settings_command,
        "ui.click": ui_click_command,
        "ui.type": ui_type_command,
        "ui.set": ui_set_command,
        "ui.select": ui_select_command,
        "ui.overlay_click": ui_overlay_click_command,
    }
    state_queries = {"state": state_query}
    _command_server = _require_command_server(
        engine,
        root,
        command_callbacks,
        json_command_callbacks,
        state_queries,
        control_routes_enabled=_e2e_command_server_enabled(),
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
    from .hotkey import HotkeyManager, duplicate_combo_failures
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
        actions = plugins.hotkey_actions()
        failures = duplicate_combo_failures(config, actions)
        duplicate_action_ids = {aid for aid, _combo, _reason in failures}
        for action_id, key, _label, default_combo in actions:
            if action_id in duplicate_action_ids:
                continue
            combo = config.get(key, default_combo)
            fn = _resolve_handler(action_id)
            if not combo or fn is None:
                continue
            hotkey_manager.register(combo, fn)
        for combo, reason in hotkey_manager.failures():
            aid = next(
                (a for a, k, _l, _d in actions
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
    settings_box[0] = settings

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
    # of pystray items. The core package registers Recent, Settings,
    # and Quit; extension packages can add their own items. Order is
    # controlled by the registered (zone, order) tuple — see
    # plugins.tray_items().
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
    activation_item = pystray.MenuItem(
        "First-run check",
        lambda _i, _it: open_activation_panel(),
    )
    insert_at = len(composed)
    for idx, item in enumerate(composed):
        if str(getattr(item, "text", "")).startswith("Settings"):
            insert_at = idx
            break
    composed.insert(insert_at, activation_item)

    icon = pystray.Icon(
        "pippal",
        make_tray_icon(False),
        config.get("brand_name", "PipPal"),
        pystray.Menu(*composed),
    )
    tray["icon"] = icon
    icon.run_detached()
    if should_show_activation_panel():
        root.after(500, open_activation_panel)

    try:
        root.mainloop()
    finally:
        try:
            icon.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
