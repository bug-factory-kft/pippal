"""Web-based frontend for PipPal (migration spike).

A parallel frontend that hosts the static UI under ``webui/`` in a
pywebview window and bridges it to the EXISTING backend. The Tkinter UI
(``pippal.ui``) is left fully intact — this package adds windows, it
does not replace them.

Nothing here changes backend behaviour: the bridge only reads/writes
config through ``pippal.config``, lists/installs voices through
``pippal.voices`` / ``pippal.ui.voice_manager``, and drives playback
through an injected ``TTSEngine``.
"""

from .bridge import PipPalBridge

__all__ = ["PipPalBridge"]
