"""PipPal PySide6 frontend (migration spike).

A parallel Qt frontend wired to the existing PipPal backend (engine,
config, voices, history, playback, pronunciation, command_server,
onboarding). The legacy Tk frontend in ``pippal.ui`` is left fully
intact; this package never imports from it except to reuse pure
backend-ish helpers (the colour palette, the notices-path resolver,
the voice download function) so the two frontends cannot visually
drift apart.

Entry point: ``pippal.app_qt.main`` (see ``reader_app_qt.py``)."""

from .activation_panel_qt import QtActivationPanel
from .overlay_qt import QtOverlay
from .settings_window_qt import QtSettingsWindow
from .theme_qt import UI, apply_app_theme
from .tray_qt import QtTray
from .voice_manager_qt import QtVoiceManagerDialog

__all__ = [
    "UI",
    "QtActivationPanel",
    "QtOverlay",
    "QtSettingsWindow",
    "QtTray",
    "QtVoiceManagerDialog",
    "apply_app_theme",
]
