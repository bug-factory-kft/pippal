"""Command-server adapters for the PySide6 frontend.

The localhost IPC command server (``pippal.command_server``) is reused
unchanged. This module supplies the Qt-side callbacks it routes to —
the analogue of the closures defined inline in ``pippal.app.main`` for
the Tk build:

* control commands: settings / stop / pause / prev / replay / next /
  voice-manager / first-run-check
* json commands: settings.apply / ui.click / ui.set / ui.type /
  ui.select / ui.overlay_click
* queries: state (a runtime snapshot mirroring the Tk ``/state``
  payload shape so the existing E2E harness contract holds)

All widget mutation runs on the Qt GUI thread via
``_QtRoot.call_on_gui_thread`` (the HTTP handler runs on a worker
thread), exactly like the Tk build's ``_call_on_tk_thread`` hop."""

from __future__ import annotations

from typing import Any

from . import plugins


def _audio_chunks(paths: list[Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for path in paths:
        info: dict[str, Any] = {
            "path": str(path), "exists": False, "size": 0,
            "riff_wave": False,
        }
        try:
            exists = path.exists()
            info["exists"] = bool(exists)
            if exists:
                info["size"] = path.stat().st_size
                with path.open("rb") as handle:
                    header = handle.read(12)
                info["riff_wave"] = (
                    header[:4] == b"RIFF" and header[8:12] == b"WAVE")
        except OSError as exc:
            info["error"] = str(exc)
        chunks.append(info)
    return chunks


def _settings_controls(settings: Any) -> list[dict[str, Any]]:
    """Inventory the Settings window's actionable controls in the same
    shape the Tk ``_widget_controls`` produces (role/text/label/
    variable/value) so coverage assertions port over."""
    if settings is None:
        return []
    out: list[dict[str, Any]] = []
    for key, var in settings.vars.items():
        try:
            value = var.get()
        except Exception:
            value = None
        out.append({
            "role": "input",
            "text": "",
            "label": key,
            "variable": key,
            "value": value,
            "class": "QtVar",
            "visible": True,
        })
    return out


def build_command_callbacks(
    root: Any,
    engine: Any,
    config: dict[str, Any],
    settings_box: list[Any],
    overlay_box: list[Any],
    activation_box: list[Any],
    open_activation_panel: Any,
    open_settings_command: Any,
    voice_manager_command: Any,
) -> dict[str, Any]:

    def runtime_snapshot() -> dict[str, Any]:
        settings = settings_box[0]
        overlay = overlay_box[0]
        settings_open = bool(settings is not None and settings.isVisible())
        settings_vars = {}
        if settings is not None:
            for key, var in settings.vars.items():
                try:
                    settings_vars[key] = var.get()
                except Exception:
                    settings_vars[key] = None
        with engine.lock:
            chunk_paths = list(engine._chunk_paths)
            backend_cls = engine._backend_cls
            playback_state = {
                "backend_name": engine._backend_name,
                "backend_class": (backend_cls.__name__
                                  if backend_cls is not None else None),
                "chunks": list(engine._chunks),
                "chunk_idx": engine._chunk_idx,
                "chunk_paths": [str(p) for p in chunk_paths],
                "is_speaking": bool(engine.is_speaking),
                "is_paused": bool(engine._is_paused),
                "queue_length": len(engine._queue),
                "token": engine.token,
            }
        playback_state["audio_chunks"] = _audio_chunks(chunk_paths)
        overlay_state: dict[str, Any] = {}
        if overlay is not None:
            try:
                overlay_state = {
                    "overlay_visible": bool(overlay.isVisible()),
                    "overlay_state": overlay.state,
                    "overlay_buttons": sorted(overlay._btn_rects),
                    "overlay_action_label": overlay.action_label,
                    "overlay_message": overlay.message,
                }
            except Exception as exc:
                overlay_state = {"overlay_error": str(exc)}
        controls = _settings_controls(settings)
        return {
            "frontend": "pyside6",
            "settings_open": settings_open,
            "settings_vars": settings_vars,
            "controls": controls,
            "windows": [{
                "title": str(config.get("brand_name", "PipPal")),
                "visible": settings_open,
                "controls": controls,
            }] if settings_open else [],
            "config": dict(config),
            "history": engine.get_history(),
            **overlay_state,
            **playback_state,
            "engines": sorted(plugins.engines()),
            "hotkey_actions": [
                aid for aid, _k, _l, _d in plugins.hotkey_actions()
            ],
        }

    def state_query() -> dict[str, Any]:
        return root.call_on_gui_thread(runtime_snapshot, timeout=4.0)

    # ---- json commands ----

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
            pending = dict(values)
            engine_value = pending.pop("engine", None)
            if engine_value is not None:
                var = settings.vars.get("engine")
                if var is None:
                    missing.append("engine")
                else:
                    var.set(engine_value)
                    settings._on_engine_change()
            for key, value in pending.items():
                var = settings.vars.get(str(key))
                if var is None:
                    missing.append(str(key))
                    continue
                var.set(value)
            if missing:
                raise RuntimeError(
                    f"unknown settings vars: {', '.join(missing)}")
            settings._persist(close=close)
            return runtime_snapshot()

        return root.call_on_gui_thread(apply, timeout=8.0)

    def _coerce(var: Any, value: Any) -> Any:
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

    def _after_var_change(settings: Any, key: str) -> None:
        if settings is None:
            return
        if key == "engine":
            settings._on_engine_change()
        elif key == "speed":
            settings._update_speed_label()
        elif key == "noise_scale":
            settings._update_var_label()

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
            var.set(_coerce(var, value))
            _after_var_change(settings, key)
            return runtime_snapshot()

        return root.call_on_gui_thread(set_value, timeout=5.0)

    def ui_type_command(data: dict[str, Any]) -> dict[str, Any]:
        target = data.get("target", {})
        key = str((target or {}).get("var_key")
                  or (target or {}).get("variable")
                  or data.get("var_key") or "")
        text = str(data.get("text", ""))
        if not key:
            raise RuntimeError("target.var_key is required")

        def type_text() -> dict[str, Any]:
            settings = settings_box[0]
            if settings is None:
                raise RuntimeError("settings window is not ready")
            var = settings.vars.get(key)
            if var is None:
                raise RuntimeError(f"unknown settings var: {key}")
            var.set(text)
            _after_var_change(settings, key)
            return runtime_snapshot()

        return root.call_on_gui_thread(type_text, timeout=5.0)

    def ui_select_command(data: dict[str, Any]) -> dict[str, Any]:
        return ui_set_command({
            "var_key": (data.get("target", {}) or {}).get("var_key")
            or data.get("var_key"),
            "value": data.get("value"),
        })

    def ui_click_command(data: dict[str, Any]) -> dict[str, Any]:
        target = data.get("target", {})
        if not isinstance(target, dict):
            raise RuntimeError("target must be an object")
        text = str(target.get("text", ""))

        def click() -> dict[str, Any]:
            settings = settings_box[0]
            if settings is None:
                raise RuntimeError("settings window is not ready")
            btn_map = {
                "Save": settings._save,
                "Apply": settings._apply,
                "Cancel": settings.close,
                "Reset to defaults": settings._reset_to_defaults,
                "Manage…": settings._open_voice_manager,
                "Install": settings._install_ctx,
                "Remove": settings._remove_ctx,
            }
            fn = btn_map.get(text)
            if fn is None:
                raise RuntimeError(f"no Qt button mapped for: {text!r}")
            fn()
            return runtime_snapshot()

        return root.call_on_gui_thread(click, timeout=5.0)

    def ui_overlay_click_command(data: dict[str, Any]) -> dict[str, Any]:
        tag = str(data.get("tag", ""))
        if tag not in {"close", "prev", "replay", "next"}:
            raise RuntimeError(
                "tag must be one of: close, prev, replay, next")

        def click_overlay() -> dict[str, Any]:
            overlay = overlay_box[0]
            if overlay is None:
                raise RuntimeError("overlay is not ready")
            handler = {
                "close": overlay.on_stop,
                "prev": overlay.on_prev,
                "replay": overlay.on_replay,
                "next": overlay.on_next,
            }[tag]
            if handler is not None:
                handler()
            return runtime_snapshot()

        return root.call_on_gui_thread(click_overlay, timeout=5.0)

    commands = {
        "settings": open_settings_command,
        "stop": engine.stop,
        "pause": engine.pause_toggle,
        "prev": engine.prev_chunk,
        "replay": engine.replay_chunk,
        "next": engine.next_chunk,
        "voice-manager": voice_manager_command,
        "first-run-check": open_activation_panel,
    }
    json_commands = {
        "settings.apply": apply_settings_command,
        "ui.click": ui_click_command,
        "ui.type": ui_type_command,
        "ui.set": ui_set_command,
        "ui.select": ui_select_command,
        "ui.overlay_click": ui_overlay_click_command,
    }
    queries = {"state": state_query}
    return {
        "commands": commands,
        "json_commands": json_commands,
        "queries": queries,
    }
