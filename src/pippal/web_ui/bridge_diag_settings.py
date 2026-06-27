"""PipPal core — diagnostics SETTINGS bridge mixin.

Extracted from pippal-pro's bridge_diag.py: the SETTINGS half only.
The UPLOAD half (send_diag_logs, get_diag_upload_status, _run_diag_upload,
set_diag_upload_config) STAYS in Pro — NOT in this module.

``DiagSettingsBridgeMixin`` contains:
  - diag_js         — JS-side breadcrumb receiver (log GENERATION -> core)
  - get_diag_state  — returns settings-relevant fields (level, counts, folder)
                      cooperative: Pro calls super().get_diag_state() and merges
                      upload status / config on top.
  - set_diag_level  — persist + configure the diag level
  - open_diag_folder — open the log folder in the OS explorer
  - delete_diag_logs — delete all log files
  - get_crash_prompt / dismiss_crash_prompt — stub implementations
                      (core returns False; Pro can override with crash_sentinel)

Compose this mixin into ``PipPalBridge`` (core bridge) so the free core can
set level / open folder / clear logs.  Pro's bridge inherits from it too and
overrides ``get_diag_state`` to merge upload state.

Notes:
  - ``self.config`` must be a mutable dict with a ``diag_log_level`` key.
  - ``_active_webview_window`` is provided as a no-op stub here; the real
    pywebview host overrides it.  Needs real-app check: ``open_diag_folder``
    returns ``{"handled": False}`` in headless/test mode.
"""

from __future__ import annotations

import sys
from typing import Any


class DiagSettingsBridgeMixin:
    """Core diagnostics settings mixin (no upload, no anon-id)."""

    # ------------------------------------------------------------------
    # JS-side diagnostics breadcrumb receiver
    # ------------------------------------------------------------------

    def diag_js(
        self,
        event: str,
        method: str | None = None,
        ok: bool | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        """Receive a JS-side diagnostics breadcrumb and emit it as a trace event.

        Privacy: only the event name, method name, ok flag, and a sanitized
        error-type string are emitted.  No-op when diagnostics are off.
        """
        from .. import diagnostics as _diag
        from ..diag_trace import event_async as _event_async

        if _diag.current_level() == "off":
            return {"ok": True}

        _SAFE = _diag._IDENTIFIER_VALUE_RE
        safe_event = (event or "")[:64]
        if not _SAFE.match(safe_event):
            safe_event = "unknown"

        fields: dict[str, Any] = {"phase": safe_event}

        if method is not None:
            safe_method = (str(method) or "")[:64]
            if _SAFE.match(safe_method):
                fields["method"] = safe_method

        if ok is not None:
            fields["ok"] = bool(ok)

        if detail is not None:
            import re as _re

            safe_detail = _re.sub(r"[^A-Za-z0-9_.\-]", "-", str(detail)[:120])[:64]
            if safe_detail and _SAFE.match(safe_detail):
                fields["detail"] = safe_detail

        _event_async(_diag.EVT_JS, **fields)
        return {"ok": True}

    # ------------------------------------------------------------------
    # Settings state
    # ------------------------------------------------------------------

    def get_diag_state(self) -> dict[str, Any]:
        """Return current diagnostics state for the Settings UI card.

        Cooperative: Pro subclasses call ``super().get_diag_state()`` and
        add upload status / config fields on top.

        Response shape (core fields only)::

            {
                "level":       str,        # current diag_log_level
                "levels":      list[str],  # all valid options
                "log_count":   int,        # number of log files on disk
                "total_bytes": int,        # combined size of log files
                "folder":      str,        # path to DIAG_DIR
            }
        """
        from ..diagnostics import DIAG_DIR, DIAG_LEVELS, list_log_files

        level: str = self.config.get("diag_log_level", "off")  # type: ignore[attr-defined]
        files = list_log_files()
        total_bytes = sum(f.stat().st_size for f in files if f.exists())

        return {
            "level": level,
            "levels": list(DIAG_LEVELS),
            "log_count": len(files),
            "total_bytes": total_bytes,
            "folder": str(DIAG_DIR),
        }

    def set_diag_level(self, level: str) -> dict[str, Any]:
        """Persist diag_log_level to config and (re)configure the handler.

        Configure-first ordering: configure_diagnostics() is called BEFORE
        save_config() so the live-process level is always updated even when
        persistence fails.

        Returns ``{"ok": True}`` on success or ``{"ok": False, "error": str}``.
        """
        from pippal.config import save_config

        from ..diagnostics import DIAG_LEVELS, configure_diagnostics

        if level not in DIAG_LEVELS:
            return {
                "ok": False,
                "error": f"Invalid level {level!r}; must be one of {list(DIAG_LEVELS)}.",
            }

        self.config["diag_log_level"] = level  # type: ignore[attr-defined]
        # Apply to live process FIRST — safe regardless of persistence.
        configure_diagnostics(level)
        try:
            save_config(self.config)  # type: ignore[attr-defined]
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return {"ok": True}

    def open_diag_folder(self) -> dict[str, Any]:
        """Open the diagnostics log folder in the OS file explorer.

        Headless-safe: returns ``{"handled": False}`` when there is no
        pywebview host (no ``_active_webview_window``).
        """
        from ..diagnostics import DIAG_DIR

        win = self._active_webview_window()
        if win is None:
            return {"handled": False}

        target = DIAG_DIR.resolve()
        target.mkdir(parents=True, exist_ok=True)
        try:
            import subprocess

            if sys.platform == "win32":
                import os as _os

                subprocess.Popen(["explorer", _os.path.normpath(str(target))])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return {"handled": True}
        except Exception as exc:
            return {"handled": True, "ok": False, "error": str(exc)}

    def delete_diag_logs(self) -> dict[str, Any]:
        """Delete all per-day diagnostics log files under DIAG_DIR.

        Returns ``{"ok": True, "removed": N}`` where N is the count removed.
        """
        from ..diagnostics import delete_logs

        try:
            removed = delete_logs()
            return {"ok": True, "removed": removed}
        except Exception as exc:
            return {"ok": False, "removed": 0, "error": str(exc)}

    # ------------------------------------------------------------------
    # Crash prompt stubs (core: always no-prompt; Pro overrides)
    # ------------------------------------------------------------------

    def get_crash_prompt(self) -> dict[str, Any]:
        """Return crash-prompt state.

        Core stub: always returns ``{"prompt": False}``.
        Pro overrides this by importing crash_sentinel.

        Privacy (H2): prompt is only shown when diagnostics are opted in.
        """
        level: str = self.config.get("diag_log_level", "off")  # type: ignore[attr-defined]
        if level == "off":
            return {"prompt": False}
        return {"prompt": False}  # Core has no crash sentinel yet.

    def dismiss_crash_prompt(self) -> dict[str, Any]:
        """Dismiss the crash prompt for this session. Core stub — always ok."""
        return {"ok": True}

    # ------------------------------------------------------------------
    # Headless fallback — subclasses / real host can override
    # ------------------------------------------------------------------

    def _active_webview_window(self) -> Any:
        """Return the active pywebview window, or None in headless/test mode.

        Real desktop host overrides this; the stub always returns None so
        open_diag_folder safely returns ``{"handled": False}`` in tests.

        NEEDS REAL-APP CHECK: pywebview-based hosts must override this method
        on PipPalBridge (or inject via the constructor) for open_diag_folder
        to actually open the Explorer window.
        """
        return None
