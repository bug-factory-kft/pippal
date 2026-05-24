"""Web-based frontend for PipPal.

The only PipPal frontend: it hosts the static UI under ``webui/`` in a
pywebview (WebView2) window and bridges it to the backend.

Nothing here changes backend behaviour: the bridge only reads/writes
config through ``pippal.config``, lists/installs voices through
``pippal.voices`` / ``pippal.voice_install``, and drives playback
through an injected ``TTSEngine``.
"""

from .bridge import PipPalBridge

__all__ = ["PipPalBridge"]
