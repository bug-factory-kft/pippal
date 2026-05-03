"""Persisted recent-readings list."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from .paths import HISTORY_PATH

MAX_HISTORY: int = 12

# Serialise on-disk writes from multiple background threads.
_save_lock = threading.Lock()


def load_history(path: Path = HISTORY_PATH) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text("utf-8"))
    except Exception as e:
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            path.replace(backup)
        except Exception:
            pass
        print(f"[history] {path} unreadable ({e}); moved to {backup}",
              file=sys.stderr)
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data][:MAX_HISTORY]


def save_history(items: list[str], path: Path = HISTORY_PATH) -> None:
    """Atomic write — temp file then os.replace — with a module-level
    lock so concurrent _remember calls don't stomp each other."""
    capped = items[:MAX_HISTORY]
    with _save_lock:
        try:
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_text(
                json.dumps(capped, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(str(tmp), str(path))
        except Exception as e:
            print(f"[history] save failed: {e}", file=sys.stderr)


def add_history(items: list[str], text: str) -> list[str]:
    """Return a new list with `text` placed at the front, deduped, and
    capped at MAX_HISTORY items. Original list is not mutated."""
    text = (text or "").strip()
    if not text:
        return list(items)
    deduped = [text] + [t for t in items if t != text]
    return deduped[:MAX_HISTORY]
