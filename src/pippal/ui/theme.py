"""Dark Tk/ttk theme: a single colour palette and one configuration
function applied to every Toplevel, plus a `make_card` helper."""

from __future__ import annotations

import re
import sys
import tkinter as tk
from tkinter import ttk

UI: dict[str, str] = {
    "bg":         "#13151c",
    "bg_card":    "#1a1d28",
    "bg_input":   "#1f2230",
    "bg_hover":   "#262a3a",
    "border":     "#262a3a",
    "border_lt":  "#2f3447",
    "text":       "#e8ebfa",
    "text_dim":   "#8a90a8",
    "text_mute":  "#6c7088",
    "accent":     "#6dd9b8",
    "accent_dk":  "#0c1e1a",
    "accent_lt":  "#82e6c5",
    "danger":     "#c14d4d",
}


def apply_dark_theme(toplevel: tk.Misc) -> None:
    """Configure ttk styles for a dark theme on the given Toplevel/Tk.
    Also asks DWM to render the native title bar in dark mode and
    paints its caption + border in PipPal's accent palette so the
    window header reads as part of the app instead of a light slab
    glued to the top."""
    toplevel.configure(bg=UI["bg"])
    _apply_native_titlebar(toplevel)
    style = ttk.Style(toplevel)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Root + frames
    style.configure(".", background=UI["bg"], foreground=UI["text"],
                    font=("Segoe UI", 10), borderwidth=0)
    style.configure("TFrame", background=UI["bg"])
    style.configure("Card.TFrame", background=UI["bg_card"], relief="flat")
    style.configure("Header.TFrame", background=UI["bg"])

    # Labels
    style.configure("TLabel", background=UI["bg"], foreground=UI["text"])
    style.configure("Card.TLabel", background=UI["bg_card"], foreground=UI["text"])
    style.configure("Title.TLabel", background=UI["bg"], foreground=UI["text"],
                    font=("Segoe UI Semibold", 16))
    style.configure("Sub.TLabel", background=UI["bg"], foreground=UI["text_dim"],
                    font=("Segoe UI", 9))
    style.configure("Section.TLabel", background=UI["bg_card"], foreground=UI["text_dim"],
                    font=("Segoe UI Semibold", 9))
    style.configure("CardHint.TLabel", background=UI["bg_card"], foreground=UI["text_mute"],
                    font=("Segoe UI", 8))

    # Buttons
    style.configure("TButton", background=UI["bg_input"], foreground=UI["text"],
                    bordercolor=UI["border_lt"], lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"], focusthickness=0, padding=(14, 7),
                    font=("Segoe UI", 9))
    style.map("TButton",
              background=[("active", UI["bg_hover"]), ("pressed", UI["bg_hover"])],
              bordercolor=[("active", UI["accent"])])

    style.configure("Primary.TButton", background=UI["accent"], foreground=UI["accent_dk"],
                    bordercolor=UI["accent"], lightcolor=UI["accent"],
                    darkcolor=UI["accent"], focusthickness=0, padding=(16, 7),
                    font=("Segoe UI Semibold", 9))
    style.map("Primary.TButton",
              background=[("active", UI["accent_lt"]), ("pressed", UI["accent_lt"])])

    style.configure("Card.TButton", background=UI["bg_input"], foreground=UI["text"],
                    bordercolor=UI["border_lt"], lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"], focusthickness=0, padding=(12, 6),
                    font=("Segoe UI", 9))
    style.map("Card.TButton",
              background=[("active", UI["bg_hover"]), ("pressed", UI["bg_hover"])],
              bordercolor=[("active", UI["accent"])])

    style.configure("Danger.TButton", background=UI["bg_input"], foreground="#e8b0b0",
                    bordercolor="#5a2a2a", lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"], focusthickness=0, padding=(12, 6))
    style.map("Danger.TButton",
              background=[("active", "#3a2030")],
              bordercolor=[("active", UI["danger"])])

    # Entries
    style.configure("TEntry", fieldbackground=UI["bg_input"], foreground=UI["text"],
                    bordercolor=UI["border_lt"], lightcolor=UI["border_lt"],
                    darkcolor=UI["border_lt"], insertcolor=UI["text"], padding=6)
    style.map("TEntry",
              bordercolor=[("focus", UI["accent"])],
              lightcolor=[("focus", UI["accent"])],
              darkcolor=[("focus", UI["accent"])])

    # Combobox
    style.configure("TCombobox", fieldbackground=UI["bg_input"], foreground=UI["text"],
                    background=UI["bg_input"], bordercolor=UI["border_lt"],
                    arrowcolor=UI["text_dim"], padding=4, lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"])
    style.map("TCombobox",
              fieldbackground=[("readonly", UI["bg_input"])],
              foreground=[("readonly", UI["text"])],
              selectbackground=[("readonly", UI["bg_input"])],
              selectforeground=[("readonly", UI["text"])],
              bordercolor=[("focus", UI["accent"])])

    # Spinbox
    style.configure("TSpinbox", fieldbackground=UI["bg_input"], foreground=UI["text"],
                    bordercolor=UI["border_lt"], arrowcolor=UI["text_dim"],
                    padding=4, lightcolor=UI["bg_input"], darkcolor=UI["bg_input"])
    style.map("TSpinbox", bordercolor=[("focus", UI["accent"])])

    # Checkbutton
    style.configure("TCheckbutton", background=UI["bg_card"], foreground=UI["text"],
                    indicatorbackground=UI["bg_input"], focusthickness=0,
                    indicatorforeground=UI["accent"], padding=4)
    style.map("TCheckbutton",
              background=[("active", UI["bg_card"])],
              indicatorbackground=[("selected", UI["accent"])])

    # Scale
    style.configure("Horizontal.TScale", background=UI["bg_card"],
                    troughcolor=UI["bg_input"], bordercolor=UI["border_lt"],
                    lightcolor=UI["accent"], darkcolor=UI["accent"])

    # Scrollbar
    style.configure("Vertical.TScrollbar", background=UI["bg_input"],
                    troughcolor=UI["bg"], bordercolor=UI["bg"],
                    arrowcolor=UI["text_dim"], lightcolor=UI["bg_input"],
                    darkcolor=UI["bg_input"])

    # Combobox dropdown listbox (it's not a ttk widget — use option_add).
    toplevel.option_add("*TCombobox*Listbox.background", UI["bg_input"])
    toplevel.option_add("*TCombobox*Listbox.foreground", UI["text"])
    toplevel.option_add("*TCombobox*Listbox.selectBackground", UI["accent"])
    toplevel.option_add("*TCombobox*Listbox.selectForeground", UI["accent_dk"])
    toplevel.option_add("*TCombobox*Listbox.borderWidth", 0)
    toplevel.option_add("*TCombobox*Listbox.relief", "flat")
    toplevel.option_add("*TCombobox*Listbox.font", "Segoe\\ UI 10")


# ---------------------------------------------------------------------------
# Native title-bar styling via DWM (Windows only).
# ---------------------------------------------------------------------------
# Tk windows inherit Windows' title-bar colour from the system theme by
# default — light grey on a light-mode system, which clashes with our
# dark client area. The Desktop Window Manager has been able to recolour
# title bars per-window since Windows 10 1809; Win 11 22H2 added explicit
# caption + text + border colour attributes. We push the immersive dark-
# mode flag, then (best-effort) the explicit caption / border colours
# matching our palette. Failure on older Windows is silent.

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20      # Win 10 1903+ (19 on 1809)
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
_DWMWA_CAPTION_COLOR = 35                # Win 11 22H2+
_DWMWA_BORDER_COLOR = 34                 # Win 11 22H2+
_DWMWA_TEXT_COLOR = 36                   # Win 11 22H2+


def _hex_to_dwm_colorref(hex_str: str) -> int:
    """`#RRGGBB` → Windows COLORREF (0x00BBGGRR)."""
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def _apply_native_titlebar(window: tk.Misc) -> None:
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # Tk's window id is the child HWND; the actual top-level
        # window with a title bar is the one returned by GetParent
        # (Tk wraps every window in an outer frame).
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            return
        dwmapi = ctypes.windll.dwmapi

        def _set(attr: int, value: int) -> bool:
            v = ctypes.c_int(value)
            return dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(v), ctypes.sizeof(v),
            ) == 0

        # 1. Immersive dark mode — flips the title bar's standard
        #    chrome to dark. Try the modern attribute first, fall
        #    back to the 1809 number.
        if not _set(_DWMWA_USE_IMMERSIVE_DARK_MODE, 1):
            _set(_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
        # 2. Explicit caption + border + text colour (Win 11 22H2+).
        #    Older Windows ignores the call.
        _set(_DWMWA_CAPTION_COLOR, _hex_to_dwm_colorref(UI["bg"]))
        _set(_DWMWA_BORDER_COLOR,  _hex_to_dwm_colorref(UI["border"]))
        _set(_DWMWA_TEXT_COLOR,    _hex_to_dwm_colorref(UI["text"]))
    except Exception:
        # Best-effort; we never want a styling tweak to crash the
        # window opening.
        pass


# ---------------------------------------------------------------------------
# Chromeless window helpers
# ---------------------------------------------------------------------------
# `tk.Toplevel.overrideredirect(True)` removes the native Windows title
# bar entirely for callers that still need a custom surface.
# Normal dialogs now keep the native titlebar through the centralized
# `create_native_dialog` / `apply_native_dialog_frame` path.
#
# Caveats: snap layouts, maximise, and the system menu are gone. For
# fixed-size dialog windows that's fine; we wouldn't use this for the
# main app surface.

_DWMWA_WINDOW_CORNER_PREFERENCE = 33  # Win 11 22H2+
_DWMWCP_ROUND = 2  # full rounded corners; 3 = small radius


def _chromeless_log(msg: str) -> None:
    """Opt-in diagnostic logger. Append a one-line debug message to
    `%TEMP%/pippal-chromeless.log` only when `PIPPAL_DEBUG_CHROMELESS`
    is set in the environment — pythonw.exe sends stderr to nowhere,
    so a file is the only useful diagnostic channel for the windowed
    build, but we don't want a stray file growing every session."""
    try:
        import os
        if not os.environ.get("PIPPAL_DEBUG_CHROMELESS"):
            return
        import tempfile
        import time
        log_path = os.path.join(tempfile.gettempdir(), "pippal-chromeless.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def make_chromeless_keep_taskbar(window: tk.Toplevel) -> None:
    """Hide the native title bar while keeping the window in the
    taskbar and Alt+Tab list.

    Tk on Windows draws the title bar itself (the underlying HWND is
    a WS_POPUP without WS_CAPTION), so Win32 style strips have no
    visible effect. The only Tk-blessed way to hide the chrome is
    `overrideredirect(True)`, which by default also drops the window
    from the taskbar / Alt+Tab. We restore those by:

    1. Breaking the owner relationship to the Tk root (otherwise the
       Toplevel is an *owned* popup and Alt+Tab skips it).
    2. Flipping `WS_EX_APPWINDOW` on (and clearing `WS_EX_TOOLWINDOW`)
       so the WM treats it as a stand-alone application.
    3. Bouncing it through withdraw/deiconify so Explorer rebuilds
       the Alt+Tab cache with the new flags.
    """
    import sys
    _chromeless_log(f"called for window id={window.winfo_id()}")
    if sys.platform != "win32":
        _chromeless_log("not win32, skipping")
        return
    try:
        import ctypes
        from ctypes import wintypes

        GWL_EXSTYLE = -20
        GWLP_HWNDPARENT = -8
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000

        user32 = ctypes.windll.user32

        is_64bit = ctypes.sizeof(ctypes.c_void_p) == 8
        if is_64bit and hasattr(user32, "GetWindowLongPtrW"):
            get_long = user32.GetWindowLongPtrW
            set_long = user32.SetWindowLongPtrW
        else:
            get_long = user32.GetWindowLongW
            set_long = user32.SetWindowLongW
        get_long.restype = ctypes.c_ssize_t
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        set_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

        # Step 1 — let Tk hide its self-drawn title bar. Tk on Windows
        # uses WS_POPUP for the visible Toplevel and paints the chrome
        # itself; overrideredirect is the only Tk-blessed way to turn
        # that chrome off.
        window.overrideredirect(True)
        _chromeless_log("overrideredirect(True) applied")

        hwnd = window.winfo_id()
        if not hwnd:
            _chromeless_log("no HWND, giving up")
            return

        # Step 2 — break the owner relationship to the Tk root window.
        # An owned popup is excluded from Alt+Tab regardless of any
        # extended-style flag, so this clear is mandatory.
        prev_owner = set_long(hwnd, GWLP_HWNDPARENT, 0)
        _chromeless_log(f"cleared owner (was {prev_owner})")

        # Step 3 — flip WS_EX_APPWINDOW on, WS_EX_TOOLWINDOW off, so
        # the WM treats the window as a stand-alone application and
        # adds it back to the taskbar / Alt+Tab.
        ex_style = get_long(hwnd, GWL_EXSTYLE)
        new_ex = (ex_style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        set_long(hwnd, GWL_EXSTYLE, new_ex)
        _chromeless_log(
            f"ex_style 0x{ex_style & 0xFFFFFFFF:08x} -> 0x{new_ex & 0xFFFFFFFF:08x}"
        )

        # Step 4 — bounce the window so Explorer rebuilds its Alt+Tab
        # cache with the new flags. Preserve Tk's requested geometry
        # across the remap; otherwise some child dialogs can flash in
        # the requested position, then let the WM fall back to (0,0).
        geometry = window.geometry()
        window.withdraw()

        def _deiconify_with_geometry() -> None:
            try:
                window.deiconify()
                if geometry:
                    window.geometry(geometry)
                    _chromeless_log(f"geometry restored after remap: {geometry}")
            except Exception as exc:
                _chromeless_log(f"deiconify restore failed: {type(exc).__name__}: {exc}")

        window.after(30, _deiconify_with_geometry)
        _chromeless_log(f"withdraw + deiconify scheduled with geometry {geometry}")
    except Exception as e:
        _chromeless_log(f"FAILED: {type(e).__name__}: {e}")


def apply_rounded_corners(window: tk.Misc) -> None:
    """Ask DWM to use Win 11 rounded corners for a Toplevel."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            return
        v = ctypes.c_int(_DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(v), ctypes.sizeof(v),
        )
    except Exception:
        pass


def apply_native_dialog_frame(window: tk.Misc) -> None:
    """Apply native title-bar colour and frame polish to a dialog."""
    _apply_native_titlebar(window)
    apply_rounded_corners(window)

    def _refresh() -> None:
        try:
            if window.winfo_exists():
                _apply_native_titlebar(window)
                apply_rounded_corners(window)
        except Exception:
            pass

    try:
        window.after_idle(_refresh)
    except Exception:
        pass


def _parse_tk_geometry(value: str) -> tuple[int | None, int | None, int, int] | None:
    match = re.match(r"^(?:(\d+)x(\d+))?([+-]\d+)([+-]\d+)$", value.strip())
    if not match:
        return None
    width = int(match.group(1)) if match.group(1) is not None else None
    height = int(match.group(2)) if match.group(2) is not None else None
    return width, height, int(match.group(3)), int(match.group(4))


def dialog_screen_bounds(dialog: tk.Misc) -> tuple[int, int, int, int] | None:
    """Return virtual screen bounds as ``(left, top, width, height)``."""
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            left = int(user32.GetSystemMetrics(76))
            top = int(user32.GetSystemMetrics(77))
            width = int(user32.GetSystemMetrics(78))
            height = int(user32.GetSystemMetrics(79))
            if width > 0 and height > 0:
                return left, top, width, height
        except Exception:
            pass

    try:
        width = int(dialog.winfo_screenwidth())
        height = int(dialog.winfo_screenheight())
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return 0, 0, width, height


def _clamp_dialog_origin(
    dialog: tk.Misc,
    width: int,
    height: int,
    x: int,
    y: int,
) -> tuple[int, int]:
    screen_bounds = dialog_screen_bounds(dialog)
    if screen_bounds is None:
        return max(0, x), max(0, y)
    screen_x, screen_y, screen_w, screen_h = screen_bounds
    max_x = screen_x + max(0, screen_w - width)
    max_y = screen_y + max(0, screen_h - height)
    return max(screen_x, min(x, max_x)), max(screen_y, min(y, max_y))


def _settled_parent_geometry(parent: tk.Misc) -> tuple[int, int, int, int] | None:
    try:
        parent.update_idletasks()
    except Exception:
        pass

    geometry: tuple[int | None, int | None, int, int] | None = None
    try:
        geometry = _parse_tk_geometry(str(parent.geometry()))
    except Exception:
        geometry = None

    root_coords: tuple[int, int] | None = None
    try:
        root_coords = (int(parent.winfo_rootx()), int(parent.winfo_rooty()))
    except Exception:
        try:
            root_coords = (int(parent.winfo_x()), int(parent.winfo_y()))
        except Exception:
            root_coords = None

    if root_coords is None and geometry is None:
        return None

    if geometry is not None and (
        root_coords is None
        or (root_coords == (0, 0) and (geometry[2], geometry[3]) != (0, 0))
    ):
        px, py = geometry[2], geometry[3]
    else:
        assert root_coords is not None
        px, py = root_coords

    try:
        parent_w = int(parent.winfo_width())
        parent_h = int(parent.winfo_height())
    except Exception:
        parent_w, parent_h = 0, 0
    if geometry is not None:
        geo_w, geo_h, _geo_x, _geo_y = geometry
    else:
        geo_w, geo_h = None, None
    if parent_w <= 1:
        parent_w = geo_w or parent_w
    if parent_h <= 1:
        parent_h = geo_h or parent_h
    return px, py, parent_w, parent_h


def dialog_origin_near_parent(
    parent: tk.Misc,
    dialog: tk.Misc,
    width: int,
    height: int,
) -> tuple[int, int]:
    """Return a centered dialog origin after pending parent geometry settles."""
    parent_geometry = _settled_parent_geometry(parent)
    if parent_geometry is None:
        return dialog_origin_on_screen(dialog, width, height)
    px, py, parent_w, parent_h = parent_geometry
    if parent_w <= 1:
        parent_w = width
    if parent_h <= 1:
        parent_h = height
    x = px + max(0, (parent_w - width) // 2)
    y = py + max(0, (parent_h - height) // 2)
    return _clamp_dialog_origin(dialog, width, height, x, y)


def dialog_origin_at_parent(
    parent: tk.Misc,
    dialog: tk.Misc,
    width: int,
    height: int,
) -> tuple[int, int]:
    """Return a clamped dialog origin aligned to the parent top-left."""
    parent_geometry = _settled_parent_geometry(parent)
    if parent_geometry is None:
        return dialog_origin_on_screen(dialog, width, height)
    px, py, _parent_w, _parent_h = parent_geometry
    return _clamp_dialog_origin(dialog, width, height, px, py)


def dialog_origin_on_screen(
    dialog: tk.Misc,
    width: int,
    height: int,
    *,
    y_divisor: int = 2,
) -> tuple[int, int]:
    """Return a centered screen origin, clamped to the virtual desktop."""
    bounds = dialog_screen_bounds(dialog)
    if bounds is None:
        return 100, 100
    screen_x, screen_y, screen_w, screen_h = bounds
    y_divisor = max(1, y_divisor)
    x = screen_x + max(0, (screen_w - width) // 2)
    y = screen_y + max(0, (screen_h - height) // y_divisor)
    return _clamp_dialog_origin(dialog, width, height, x, y)


def create_native_dialog(
    parent: tk.Misc,
    *,
    title: str,
    width: int,
    height: int,
    minsize: tuple[int, int] | None = None,
    resizable: tuple[bool, bool] | None = None,
    placement: str = "screen-center",
    origin: tuple[int, int] | None = None,
) -> tk.Toplevel:
    """Create a hidden, themed dialog with stable geometry before first paint."""
    window = tk.Toplevel(parent)
    try:
        window.withdraw()
    except Exception:
        pass
    window.title(title)
    if minsize is not None:
        window.minsize(*minsize)
    if resizable is not None:
        window.resizable(*resizable)
    apply_dark_theme(window)
    apply_native_dialog_frame(window)

    if origin is not None:
        x, y = _clamp_dialog_origin(window, width, height, origin[0], origin[1])
    elif placement == "parent-center":
        x, y = dialog_origin_near_parent(parent, window, width, height)
    elif placement == "parent-origin":
        x, y = dialog_origin_at_parent(parent, window, width, height)
    elif placement == "screen-upper":
        x, y = dialog_origin_on_screen(window, width, height, y_divisor=3)
    else:
        x, y = dialog_origin_on_screen(window, width, height)
    window.geometry(f"{width}x{height}+{x}+{y}")
    return window


def show_native_dialog(
    window: tk.Toplevel,
    parent: tk.Misc | None = None,
    *,
    focus: bool = True,
    grab: bool = False,
) -> None:
    """Reveal a prepared dialog after layout and native-frame refresh."""
    try:
        window.update_idletasks()
    except Exception:
        pass
    apply_native_dialog_frame(window)

    def _raise() -> None:
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return
        apply_native_dialog_frame(window)
        try:
            if parent is not None:
                window.lift(parent)
            else:
                window.lift()
        except Exception:
            try:
                window.lift()
            except Exception:
                pass
        if focus:
            try:
                window.focus_force()
            except Exception:
                pass
        if grab:
            try:
                window.grab_set()
            except Exception:
                pass

    try:
        window.deiconify()
    except Exception:
        pass
    _raise()
    try:
        window.after(30, _raise)
    except Exception:
        pass


def enable_drag_to_move(window: tk.Toplevel, drag_handle: tk.Misc) -> None:
    """Bind `<Button-1>` / `<B1-Motion>` on `drag_handle` so dragging
    it moves the (chromeless) `window`. Works recursively across the
    handle's children except interactive controls (buttons / entries
    / comboboxes), so clicking a button on the header doesn't drag."""
    state: dict[str, int] = {
        "dx": 0,
        "dy": 0,
        "start_x": 0,
        "start_y": 0,
        "win_x": 0,
        "win_y": 0,
        "active": 0,
        "polling": 0,
    }

    def _start_pointer_poll_drag() -> bool:
        """Poll the global pointer while Windows holds the left button.

        Tk geometry fallback works for normal Settings windows, but modal
        chromeless dialogs can miss `<B1-Motion>` during real mouse
        automation. Polling keeps those custom headers draggable too.
        """
        import sys
        if sys.platform != "win32" or state["polling"]:
            return False
        try:
            import ctypes

            user32 = ctypes.windll.user32

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            def _poll() -> None:
                if not state["polling"]:
                    return
                if not (user32.GetAsyncKeyState(0x01) & 0x8000):
                    state["polling"] = 0
                    return

                point = POINT()
                if user32.GetCursorPos(ctypes.byref(point)):
                    x = state["win_x"] + (int(point.x) - state["start_x"])
                    y = state["win_y"] + (int(point.y) - state["start_y"])
                    window.geometry(f"+{x}+{y}")
                window.after(15, _poll)
        except Exception:
            return False

        state["polling"] = 1
        window.after(1, _poll)
        return True

    def _press(event: tk.Event) -> None:
        win_x = window.winfo_rootx()
        win_y = window.winfo_rooty()
        state["dx"] = event.x_root - win_x
        state["dy"] = event.y_root - win_y
        state["start_x"] = event.x_root
        state["start_y"] = event.y_root
        state["win_x"] = win_x
        state["win_y"] = win_y
        state["active"] = 1
        _start_pointer_poll_drag()

    def _drag(event: tk.Event) -> None:
        if not state["active"]:
            return
        x = event.x_root - state["dx"]
        y = event.y_root - state["dy"]
        window.geometry(f"+{x}+{y}")

    def _release(_event: tk.Event) -> None:
        state["active"] = 0
        state["polling"] = 0

    def _press_if_header(event: tk.Event) -> None:
        try:
            x = event.x_root
            y = event.y_root
            header_x = drag_handle.winfo_rootx()
            header_y = drag_handle.winfo_rooty()
            header_w = drag_handle.winfo_width()
            header_h = drag_handle.winfo_height()
        except Exception:
            return

        if not (header_x <= x < header_x + header_w):
            return
        if not (header_y <= y < header_y + header_h):
            return
        # Reserve the right edge for custom title-bar buttons.
        if x >= header_x + header_w - 72:
            return
        _press(event)

    def _bind_recursive(widget: tk.Misc) -> None:
        # Don't capture clicks on interactive widgets — let them work
        # normally. The header's labels and frames carry the drag.
        cls = widget.winfo_class()
        if cls in ("TButton", "TEntry", "TCombobox", "Button",
                    "Entry", "Combobox"):
            return
        widget.bind("<Button-1>", _press)
        widget.bind("<B1-Motion>", _drag)
        widget.bind("<ButtonRelease-1>", _release)
        for child in widget.winfo_children():
            _bind_recursive(child)

    _bind_recursive(drag_handle)
    window.bind("<Button-1>", _press_if_header, add="+")
    window.bind("<B1-Motion>", _drag, add="+")
    window.bind("<ButtonRelease-1>", _release, add="+")


def make_card(parent: tk.Misc, title: str | None = None) -> tuple[ttk.Frame, ttk.Frame]:
    """Create a card frame with an optional section title.

    Returns ``(outer, card)``: pack ``outer`` into the parent layout, put
    your widgets inside ``card`` with ``Card.*`` ttk styles."""
    outer = ttk.Frame(parent, style="TFrame")
    card = ttk.Frame(outer, style="Card.TFrame", padding=(20, 16, 20, 16))
    card.pack(fill="x")
    if title:
        ttk.Label(card, text=title.upper(), style="Section.TLabel").pack(
            anchor="w", pady=(0, 12)
        )
    return outer, card
