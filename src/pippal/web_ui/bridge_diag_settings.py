"""PipPal core — diagnostics settings bridge mixin.

Settings half only (level, open folder, clear logs, crash-prompt stubs).
Upload pipeline stays in Pro. Pro's bridge inherits this and overrides
``get_diag_state`` to merge upload state.

Requires ``self.config`` (dict with ``diag_log_level``). ``_active_webview_window``
is a no-op stub; real host must override it.
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
        """Return diagnostics state for the Settings UI (level, counts, folder).

        Cooperative: Pro subclasses call ``super().get_diag_state()`` and
        merge upload fields on top.
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

        configure_diagnostics() runs before save_config() so the live level
        is always updated even if persistence fails.
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

        Headless-safe: returns ``{"handled": False}`` when no pywebview host.
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
        """Return crash-prompt state. Core stub: always ``{"prompt": False}``.

        Privacy (H2): prompt only shown when diagnostics are opted in.
        Pro overrides with real crash_sentinel logic.
        """
        return {"prompt": False}

    def dismiss_crash_prompt(self) -> dict[str, Any]:
        """Dismiss the crash prompt for this session. Core stub — always ok."""
        return {"ok": True}

    # ------------------------------------------------------------------
    # Headless fallback — subclasses / real host can override
    # ------------------------------------------------------------------

    def _active_webview_window(self) -> Any:
        """Return the active pywebview window, or None in headless/test mode.

        NEEDS REAL-APP CHECK: hosts must override this on PipPalBridge for
        ``open_diag_folder`` to actually open the Explorer window.
        """
        return None
