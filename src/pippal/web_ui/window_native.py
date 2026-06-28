"""Win32 / DWM native window operations for the PipPal web UI.

These functions are PURE / stateless: they take ``win`` / ``hwnd`` as
explicit arguments and touch no ``WebWindowManager`` instance state.
``windows.py`` calls them through lazy imports (at call-time, not at
module top level) so that ``import pippal`` remains headless-safe (H3).

Behaviour: DWM rounded corners + layered colour-key transparency,
and ``show_no_activate`` overlay focus-steal fix.
"""

from __future__ import annotations

import sys
from typing import Any

# Win32 constants for the layered colour-key transparency approach.
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_LWA_COLORKEY = 0x00000001

# DWM rounded-corner constants.
# Windows 11 auto-rounds normal (framed) windows via DWM, but frameless
# windows (FormBorderStyle.None) do NOT get rounded corners automatically.
# Explicit DWMWA_WINDOW_CORNER_PREFERENCE=DWMWCP_ROUND is required.
_DWMWA_WINDOW_CORNER_PREFERENCE = 33  # attribute index
_DWMWCP_ROUND = 2  # always round (matches system corner radius)
# The opaque host colour the WinForms Form paints behind the WebView2 on
# pywebview 6.x + WebView2.  pywebview sets the WebView2
# ``DefaultBackgroundColor = Transparent`` for ``transparent=True`` windows
# but does NOT make the underlying WinForms ``Form`` transparent — the Form
# keeps its default ``SystemColors.Control`` BackColor (#f0f0f0 on the
# default light theme), so the host renders as an OPAQUE light rectangle
# behind the page's panel.  Colour-keying that exact host colour with a
# layered window makes the empty area genuinely transparent.
_HOST_COLORKEY = 0x00F0F0F0  # COLORREF 0x00BBGGRR for RGB #f0f0f0


def host_hwnd(win: Any) -> int | None:
    """Return the native top-level HWND of a pywebview window, or None.

    pywebview's WinForms backend stores the host ``Form`` on
    ``win.native`` after creation; its ``.Handle.ToInt32()`` is the
    HWND.  Returns None if the native handle is not (yet) available."""
    native = getattr(win, "native", None)
    if native is None:
        return None
    handle = getattr(native, "Handle", None)
    if handle is None:
        return None
    try:
        return int(handle.ToInt32())
    except Exception:
        try:
            return int(handle)
        except Exception:
            return None


def apply_dwm_round_corners(win: Any) -> None:
    """Apply Win11 DWM rounded corners to a frameless pywebview window.

    Windows 11 auto-rounds FRAMED windows via DWM, but FRAMELESS windows
    (pywebview uses FormBorderStyle.None) do NOT get rounded corners
    automatically — they require an explicit
    DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE=33,
    DWMWCP_ROUND=2) call.

    This is the root cause of the overlay showing square corners while
    Settings appears rounded: both are frameless, but Windows 11's default
    (DWMWCP_DEFAULT=0) only rounds framed windows.  Applying DWMWCP_ROUND
    to all frameless app windows makes them match consistently.

    No-ops off Windows or before the native HWND is available.
    Swallows all failures — corner rounding is cosmetic and must never
    break window creation."""
    if sys.platform != "win32":
        return
    hwnd = host_hwnd(win)
    if not hwnd:
        return
    try:
        import ctypes as _ctypes

        _ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            _DWMWA_WINDOW_CORNER_PREFERENCE,
            _ctypes.byref(_ctypes.c_int(_DWMWCP_ROUND)),
            4,
        )
    except Exception:
        # Cosmetic — never break window creation.
        pass


def apply_layered_colorkey(win: Any) -> None:
    """Make a transparent-spec host genuinely transparent.

    Adds ``WS_EX_LAYERED`` to the host window and colour-keys the
    opaque WinForms BackColor (#f0f0f0) so the empty host area shows
    the desktop through — only the page's rounded panel paints.  This
    is the robust fix on pywebview 6.x + WebView2, where the WebView2
    ``DefaultBackgroundColor = Transparent`` alone leaves the host
    opaque (the WinForms Form keeps its default light BackColor).

    No-ops off Windows or before the native handle exists.  Defensive:
    a transparency failure must never break window creation."""
    if sys.platform != "win32":
        return
    hwnd = host_hwnd(win)
    if not hwnd:
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        ex = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        if not (ex & _WS_EX_LAYERED):
            user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex | _WS_EX_LAYERED)
        # LWA_COLORKEY: pixels matching the key become fully
        # transparent; everything else (the panel) stays opaque.
        user32.SetLayeredWindowAttributes(hwnd, _HOST_COLORKEY, 0, _LWA_COLORKEY)
        # Force a repaint so the key takes effect immediately.
        # RDW_INVALIDATE | RDW_ERASE | RDW_UPDATENOW.
        user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0100)
    except Exception:
        # Transparency is best-effort; never break the window.
        pass


def show_no_activate(win: Any) -> bool:
    """Show *win* WITHOUT stealing foreground focus.

    ``pywebview``'s ``show()`` / ``restore()`` ACTIVATE the window, which
    steals the foreground. For the reader overlay that must be avoided: a
    selection-read must not have focus yanked during capture, and the
    activation is jarring for the user. Instead we drive Win32
    ``ShowWindow(hwnd, SW_SHOWNOACTIVATE)`` + a topmost
    ``SetWindowPos`` with ``SWP_NOACTIVATE`` so the overlay pops on top
    instantly while the user's app keeps the foreground/caret. Returns
    True if applied, False (caller falls back to activating show())."""
    if sys.platform != "win32":
        return False
    hwnd = host_hwnd(win)
    if not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        _SW_SHOWNOACTIVATE = 4
        user32.ShowWindow(hwnd, _SW_SHOWNOACTIVATE)
        _HWND_TOPMOST = -1
        _SWP_NOSIZE = 0x0001
        _SWP_NOMOVE = 0x0002
        _SWP_NOACTIVATE = 0x0010
        _SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(
            hwnd,
            _HWND_TOPMOST,
            0,
            0,
            0,
            0,
            _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW,
        )
        return True
    except Exception:
        return False


def bring_to_foreground(win: Any) -> bool:
    """Raise + activate *win* and pull it to the foreground.

    Used when a tray action or hotkey asks the already-running instance
    to OPEN its window: restore from minimized, raise to the top, and
    grab the foreground so the user actually SEES the window.

    Unlike :func:`show_no_activate` (which deliberately avoids stealing
    focus for the capture overlay), this DOES activate — that is the whole
    point of a user-initiated "open the app" action.

    No-ops (returns False) off Windows or before the native HWND exists.
    Swallows all failures — foregrounding must never crash the open path."""
    if sys.platform != "win32":
        return False
    hwnd = host_hwnd(win)
    if not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        _SW_RESTORE = 9
        _SW_SHOW = 5
        # Restore if minimized, then ensure shown.
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, _SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, _SW_SHOW)
        # Briefly assert TOPMOST then drop it, a well-known trick to pull a
        # window above others without permanently pinning it on top.
        _HWND_TOPMOST = -1
        _HWND_NOTOPMOST = -2
        _SWP_NOSIZE = 0x0001
        _SWP_NOMOVE = 0x0002
        _SWP_SHOWWINDOW = 0x0040
        flags = _SWP_NOSIZE | _SWP_NOMOVE | _SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, _HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False
