"""PipPal — your little offline reading buddy.

Tray-resident Windows app that reads selected text aloud using local
neural TTS, with an animated reader panel and right-click integration.

Public API:
- `main()`     — entry point used by `python -m pippal` and reader_app.py
- `TTSEngine`  — orchestration class
"""
# ruff: noqa: E402
# Import order is intentional: registries must be populated by the
# self-register module + extension discovery BEFORE the app/engine
# modules are imported, in case a future change has them read the
# registry at import time. Letting ruff re-sort would re-introduce
# the bug.

from . import _register  # noqa: F401  (side-effect: built-in registration)
from . import plugins as _plugins

# Load any optional extension packages installed alongside `pippal`.
# find_spec first so a broken-but-installed extension is logged
# rather than silently swallowed.
_plugins.load_extensions()

from .app import main
from .engine import TTSEngine

__all__ = ["TTSEngine", "main"]
__version__ = "0.2.0"
