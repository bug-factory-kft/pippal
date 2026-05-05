"""TTS engine implementations bundled with the core package.

Pro-only engines (Kokoro etc.) live in `pippal_pro.engines` and
self-register into `pippal.plugins` on import — the core package
itself never imports them."""

from .base import TTSBackend
from .factory import make_backend
from .piper import PiperBackend

__all__ = ["PiperBackend", "TTSBackend", "make_backend"]
