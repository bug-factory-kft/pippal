"""Startup tray notification — shows a brief "running in background" toast.

Displayed once at app launch, ~200 ms after the tray icon appears, so the
main window is already up before the toast is drawn.

The toast is a small frameless, always-on-top, transparent pywebview window
(320 × 80 px) positioned in the bottom-right corner of the primary screen.
It closes automatically after 4 seconds.

Set the environment variable ``PIPPAL_NO_STARTUP_NOTIFICATION=1`` to suppress
the toast entirely (useful for CI, headless test environments, etc.).

Any exception inside ``_display_toast`` is silently swallowed so a missing
WebView2 runtime or other GUI problem never crashes app startup.
"""

from __future__ import annotations

import os
import threading

# Delay (ms) from tray-icon ready to toast appearing.
_DELAY_MS = 200
# How long (s) the toast stays visible before auto-closing.
_VISIBLE_SECONDS = 4


_TOAST_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: rgba(30, 32, 40, 0.92);
    border-radius: 10px;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 18px;
    font-family: 'Segoe UI', system-ui, sans-serif;
    color: #e8eaf0;
    font-size: 13px;
    line-height: 1.4;
    border: 1px solid rgba(255,255,255,0.10);
    height: 100%;
    overflow: hidden;
  }
  .icon {
    font-size: 22px;
    flex-shrink: 0;
    line-height: 1;
  }
  .text strong { display: block; font-weight: 600; font-size: 14px; }
  .text span   { color: #9da3b4; font-size: 12px; }
</style>
</head>
<body>
  <div class="icon">🎧</div>
  <div class="text">
    <strong>PipPal</strong>
    <span>Running in the background</span>
  </div>
</body>
</html>"""


def _display_toast() -> None:
    """Create and show the toast window, then auto-close after a delay.

    Called from a background thread; any exception is intentionally allowed
    to propagate — the caller (``show_startup_toast``) wraps it in try/except.
    """
    import ctypes

    import webview  # lazy — not available in headless CI

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)

    w, h = 320, 80
    margin = 16
    x = screen_w - w - margin
    y = screen_h - h - margin - 48  # 48 ≈ taskbar height

    win = webview.create_window(
        title="",
        html=_TOAST_HTML,
        width=w,
        height=h,
        x=x,
        y=y,
        frameless=True,
        on_top=True,
        transparent=True,
        focus=False,
        easy_drag=False,
    )

    def _auto_close() -> None:
        try:
            win.destroy()
        except Exception:
            pass

    close_timer = threading.Timer(_VISIBLE_SECONDS, _auto_close)
    close_timer.daemon = True

    def _on_shown() -> None:
        close_timer.start()

    win.events.shown += _on_shown

    # pywebview.start() blocks — run in a throwaway thread so we don't steal
    # the main-thread GUI loop that belongs to the main windows.
    webview.start()


def show_startup_toast() -> None:
    """Schedule a one-shot startup notification toast.

    Safe to call on any thread.  Silently skipped when
    ``PIPPAL_NO_STARTUP_NOTIFICATION`` is set in the environment.
    Any display error is swallowed so it never crashes app launch.
    """
    if os.environ.get("PIPPAL_NO_STARTUP_NOTIFICATION"):
        return

    def _run() -> None:
        try:
            _display_toast()
        except Exception:
            pass

    t = threading.Timer(_DELAY_MS / 1000.0, _run)
    t.daemon = True
    t.start()
