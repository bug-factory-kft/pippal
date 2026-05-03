"""PipPal Tk UI: theme + reader panel + settings + dialogs."""

from .overlay import Overlay
from .settings_window import SettingsWindow
from .theme import UI, apply_dark_theme, make_card
from .voice_manager import VoiceManagerDialog

__all__ = [
    "UI",
    "Overlay",
    "SettingsWindow",
    "VoiceManagerDialog",
    "apply_dark_theme",
    "make_card",
]
