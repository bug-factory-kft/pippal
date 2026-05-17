"""Dark Qt theme for the PySide6 frontend.

Mirrors the Tk/ttk palette in ``pippal.ui.theme`` so the migrated UI
reads as the same product: same colours, same Segoe UI typeface, same
card-based dark surface, same rounded chromeless window feel.

The single source of truth for colours is the existing
``pippal.ui.theme.UI`` dict — we import it here so the two frontends
never drift apart. Everything else is a Qt Style Sheet (QSS) plus a few
Win32/DWM calls reused conceptually from the Tk side (dark title bar,
rounded corners)."""

from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

# Reuse the exact palette the Tk UI ships so the two frontends match.
from ..ui.theme import UI

__all__ = [
    "BASE_FONT",
    "SECTION_FONT",
    "TITLE_FONT",
    "UI",
    "apply_app_theme",
    "apply_native_dark_titlebar",
    "apply_rounded_corners",
    "build_stylesheet",
]


BASE_FONT = ("Segoe UI", 10)
TITLE_FONT = ("Segoe UI Semibold", 16)
SECTION_FONT = ("Segoe UI Semibold", 9)


def build_stylesheet() -> str:
    """Return the QSS that recreates the Tk dark theme.

    Selectors are scoped by objectName / dynamic property where the
    look diverges (cards, primary/danger buttons, hint labels) so the
    same defaults the ttk styles used carry over."""
    u = UI
    return f"""
    QWidget {{
        background-color: {u['bg']};
        color: {u['text']};
        font-family: "Segoe UI";
        font-size: 10pt;
    }}
    QToolTip {{
        background-color: {u['bg_input']};
        color: {u['text']};
        border: 1px solid {u['border_lt']};
    }}

    /* ---- Cards ---- */
    QFrame#Card {{
        background-color: {u['bg_card']};
        border: 1px solid {u['border']};
        border-radius: 10px;
    }}
    QFrame#Card QLabel {{
        background-color: transparent;
    }}
    QLabel#SectionTitle {{
        color: {u['text_dim']};
        font-family: "Segoe UI Semibold";
        font-size: 9pt;
        font-weight: 600;
    }}
    QLabel#TitleLabel {{
        color: {u['text']};
        font-family: "Segoe UI Semibold";
        font-size: 16pt;
        font-weight: 600;
    }}
    QLabel#SubLabel {{
        color: {u['text_dim']};
        font-size: 9pt;
    }}
    QLabel#CardHint {{
        color: {u['text_mute']};
        font-size: 8pt;
    }}
    QLabel#LinkLabel {{
        color: {u['accent']};
    }}

    /* ---- Buttons ---- */
    QPushButton {{
        background-color: {u['bg_input']};
        color: {u['text']};
        border: 1px solid {u['border_lt']};
        border-radius: 6px;
        padding: 7px 14px;
        font-size: 9pt;
    }}
    QPushButton:hover {{
        background-color: {u['bg_hover']};
        border: 1px solid {u['accent']};
    }}
    QPushButton:pressed {{
        background-color: {u['bg_hover']};
    }}
    QPushButton:disabled {{
        color: {u['text_mute']};
        border: 1px solid {u['border']};
    }}
    QPushButton#Primary {{
        background-color: {u['accent']};
        color: {u['accent_dk']};
        border: 1px solid {u['accent']};
        font-family: "Segoe UI Semibold";
        font-weight: 600;
        padding: 7px 16px;
    }}
    QPushButton#Primary:hover {{
        background-color: {u['accent_lt']};
        border: 1px solid {u['accent_lt']};
    }}
    QPushButton#Primary:pressed {{
        background-color: {u['accent_lt']};
    }}
    QPushButton#Danger {{
        color: #e8b0b0;
        border: 1px solid #5a2a2a;
    }}
    QPushButton#Danger:hover {{
        background-color: #3a2030;
        border: 1px solid {u['danger']};
    }}

    /* ---- Inputs ---- */
    QLineEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {u['bg_input']};
        color: {u['text']};
        border: 1px solid {u['border_lt']};
        border-radius: 4px;
        padding: 6px;
        selection-background-color: {u['accent']};
        selection-color: {u['accent_dk']};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {u['accent']};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background-color: {u['bg_input']};
        border: none;
        width: 16px;
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: none; border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-bottom: 5px solid {u['text_dim']};
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: none; border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {u['text_dim']};
    }}

    /* ---- ComboBox ---- */
    QComboBox {{
        background-color: {u['bg_input']};
        color: {u['text']};
        border: 1px solid {u['border_lt']};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QComboBox:focus {{ border: 1px solid {u['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox::down-arrow {{
        image: none; border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {u['text_dim']};
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {u['bg_input']};
        color: {u['text']};
        border: 1px solid {u['border_lt']};
        selection-background-color: {u['accent']};
        selection-color: {u['accent_dk']};
        outline: 0;
    }}

    /* ---- Checkbox ---- */
    QCheckBox {{ background-color: transparent; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {u['border_lt']};
        border-radius: 3px;
        background-color: {u['bg_input']};
    }}
    QCheckBox::indicator:checked {{
        background-color: {u['accent']};
        border: 1px solid {u['accent']};
    }}

    /* ---- Slider ---- */
    QSlider::groove:horizontal {{
        height: 4px;
        background: {u['bg_input']};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {u['accent']};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {u['accent']};
        width: 14px; height: 14px;
        margin: -6px 0;
        border-radius: 7px;
    }}

    /* ---- Scrollbar ---- */
    QScrollArea {{ border: none; background: {u['bg']}; }}
    QScrollBar:vertical {{
        background: {u['bg']};
        width: 12px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {u['bg_input']};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {u['bg_hover']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    /* ---- Text edit (notices viewer / sample box) ---- */
    QPlainTextEdit, QTextEdit {{
        background-color: {u['bg_input']};
        color: {u['text']};
        border: 1px solid {u['border_lt']};
        border-radius: 4px;
        selection-background-color: {u['accent']};
        selection-color: {u['accent_dk']};
    }}

    QFrame#Separator {{ background-color: {u['border']}; }}
    """


def apply_app_theme(app: QApplication) -> None:
    """Apply the dark palette + global stylesheet to the whole app.

    Called once after ``QApplication`` is created. The QPalette is set
    too so native popups (combo dropdowns, tooltips) inherit dark even
    before the stylesheet cascades."""
    u = UI
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(u["bg"]))
    pal.setColor(QPalette.WindowText, QColor(u["text"]))
    pal.setColor(QPalette.Base, QColor(u["bg_input"]))
    pal.setColor(QPalette.AlternateBase, QColor(u["bg_card"]))
    pal.setColor(QPalette.Text, QColor(u["text"]))
    pal.setColor(QPalette.Button, QColor(u["bg_input"]))
    pal.setColor(QPalette.ButtonText, QColor(u["text"]))
    pal.setColor(QPalette.Highlight, QColor(u["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(u["accent_dk"]))
    pal.setColor(QPalette.ToolTipBase, QColor(u["bg_input"]))
    pal.setColor(QPalette.ToolTipText, QColor(u["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(u["text_mute"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(u["text_mute"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(u["text_mute"]))
    app.setPalette(pal)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(build_stylesheet())


# ---------------------------------------------------------------------------
# Native title-bar styling via DWM (Windows only) — same intent as the
# Tk side's ``_apply_native_titlebar`` / ``apply_rounded_corners``.
# ---------------------------------------------------------------------------

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
_DWMWA_CAPTION_COLOR = 35
_DWMWA_BORDER_COLOR = 34
_DWMWA_TEXT_COLOR = 36
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


def _hex_to_dwm_colorref(hex_str: str) -> int:
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_native_dark_titlebar(widget: QWidget) -> None:
    """Paint the native Windows title bar in PipPal's dark palette so a
    framed Qt window header reads as part of the app, mirroring the Tk
    ``_apply_native_titlebar`` behaviour. Best-effort; silent on
    non-Windows or older Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        if not hwnd:
            return
        dwmapi = ctypes.windll.dwmapi

        def _set(attr: int, value: int) -> bool:
            v = ctypes.c_int(value)
            return dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(v), ctypes.sizeof(v),
            ) == 0

        if not _set(_DWMWA_USE_IMMERSIVE_DARK_MODE, 1):
            _set(_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
        _set(_DWMWA_CAPTION_COLOR, _hex_to_dwm_colorref(UI["bg"]))
        _set(_DWMWA_BORDER_COLOR, _hex_to_dwm_colorref(UI["border"]))
        _set(_DWMWA_TEXT_COLOR, _hex_to_dwm_colorref(UI["text"]))
    except Exception:
        pass


def apply_rounded_corners(widget: QWidget) -> None:
    """Ask DWM for Win 11 rounded corners, same as the Tk helper."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        if not hwnd:
            return
        v = ctypes.c_int(_DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(v), ctypes.sizeof(v),
        )
    except Exception:
        pass


def apply_native_frame(widget: QWidget) -> None:
    """Convenience: dark title bar + rounded corners for a dialog/window."""
    apply_native_dark_titlebar(widget)
    apply_rounded_corners(widget)
