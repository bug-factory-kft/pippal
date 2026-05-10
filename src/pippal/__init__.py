"""PipPal — your little offline reading buddy.

Tray-resident Windows app that reads selected text aloud using the
Piper neural TTS engine, with an animated reader panel and right-click
integration. Optional extension packages can self-register additional
engines and selection-driven actions through ``pippal.plugins``.

Public API:
- `main()`     — entry point used by `python -m pippal` and reader_app.py
- `TTSEngine`  — orchestration class
"""
# ruff: noqa: E402
# Import order is intentional: registries must be populated by
# _register + load_pro_plugin BEFORE the app/engine modules are
# imported, in case a future change has them read the registry at
# import time. Letting ruff re-sort would re-introduce the bug.

from . import _register  # noqa: F401  (side-effect: built-in registration)
from . import plugins as _plugins

# Discover an optional Pro plugin. find_spec first so a partial Pro
# install (broken dependency) is logged loudly rather than swallowed.
_plugins.load_pro_plugin()

from .app import main
from .engine import TTSEngine

__all__ = ["TTSEngine", "main"]
__version__ = "0.2.0"
