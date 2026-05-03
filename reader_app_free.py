"""PipPal — Free build launcher.

Same code base as the paid build, but `pippal_pro` is blocked from
import. Useful for:

- Smoke-testing the Free distribution without uninstalling pippal_pro
- Running the open-source feature set on a dev machine that also has
  the proprietary package on disk

The block is the same shape that an MS Store paid-build launcher
won't need (paid builds bundle pippal_pro, so it just imports
normally).
"""

from __future__ import annotations

import importlib.util
import sys


def _install_pippal_pro_block() -> None:
    """Make `pippal_pro` and any submodule invisible to import-time
    discovery. We patch both `importlib.util.find_spec` (used by
    `pippal.plugins.load_pro_plugin`) and `sys.meta_path` (used by the
    standard `import` machinery) so neither path finds the package."""

    _orig_find_spec = importlib.util.find_spec

    def _hidden_find_spec(name, package=None):
        if name == "pippal_pro" or name.startswith("pippal_pro."):
            return None
        return _orig_find_spec(name, package)

    importlib.util.find_spec = _hidden_find_spec

    class _Block:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "pippal_pro" or fullname.startswith("pippal_pro."):
                return None
            return None

    sys.meta_path.insert(0, _Block())


_install_pippal_pro_block()

from pippal import main  # noqa: E402  (block must run BEFORE pippal imports)

if __name__ == "__main__":
    main()
