"""Backend selection — driven by `pippal.plugins`.

The factory has zero name-awareness of specific engines: it just looks
up the requested engine name in the plugin registry. The core
distribution always registers `piper` (in `pippal/_register.py`),
so the always-available fallback is `plugins.get_engine("piper")`.
The optional `pippal_pro` package registers e.g. `kokoro`. A
hypothetical third-party plugin could register `elevenlabs`,
`edge_tts`, etc. — none of which require touching this file."""

from __future__ import annotations

import sys
from typing import Any

from .. import plugins
from .base import TTSBackend
from .piper import PiperBackend


def make_backend(config: dict[str, Any]) -> TTSBackend:
    """Return a fresh backend matching `config['engine']`. Falls back
    to Piper if the requested engine is unknown, or if it loads but
    its `is_available()` says no (assets missing, deps not installed)."""
    name = (config.get("engine") or "piper").lower()
    cls = plugins.get_engine(name)
    if cls is not None:
        b = cls(config)
        if b.is_available():
            return b
        print(
            f"[engine] {name} registered but unavailable; falling back to piper",
            file=sys.stderr,
        )
    elif name != "piper":
        # User picked an engine we've never heard of — only worth
        # warning when it isn't 'piper' (the always-present fallback).
        print(
            f"[engine] {name!r} is not a registered engine; falling back to piper",
            file=sys.stderr,
        )
    # Always-available fallback. The core package guarantees this is
    # registered; if it isn't, something has gone seriously wrong with
    # the plugin host, so let the import error surface naturally.
    piper_cls = plugins.get_engine("piper") or PiperBackend
    return piper_cls(config)
