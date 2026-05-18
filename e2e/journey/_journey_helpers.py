"""Shared helpers for the Tier-2 journey tests.

These talk to the **real running app** — its live ``POST /bridge``
server (the same JSON endpoint the desktop UI uses) and its on-disk
profile — so a journey can assert a *real effect* (engine state,
config.json, installed voice files, history.json) on the actually
launched process, not a mock.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any


def bridge_call(base: str, method: str, *args: Any, timeout: float = 30.0) -> Any:
    """Invoke a method on the REAL running app's bridge server.

    This is the exact JSON transport the live desktop UI uses
    (``POST /bridge``) — calling it here reads/acts on the genuine
    in-process engine/config/voices of the launched app, not a copy.
    """
    body = json.dumps({"method": method, "args": list(args)}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/bridge",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("__error__"):
        raise RuntimeError(f"bridge {method} error: {payload['__error__']}")
    return payload


def deadline_poll(
    predicate: Callable[[], Any],
    *,
    timeout: float = 30.0,
    interval: float = 0.25,
    what: str = "condition",
) -> Any:
    """Poll ``predicate`` until it returns a truthy value or the
    deadline passes. Returns the truthy value; raises AssertionError on
    timeout. No fixed sleeps — this is a real wait-for-effect loop.
    """
    deadline = time.time() + timeout
    last: Any = None
    while time.time() < deadline:
        try:
            last = predicate()
        except Exception as exc:  # treat transient errors as "not yet"
            last = f"<error: {exc}>"
        else:
            if last:
                return last
        time.sleep(interval)
    raise AssertionError(
        f"deadline-poll timed out after {timeout}s waiting for {what} "
        f"(last={last!r})"
    )


def is_riff_wave(path: Path) -> bool:
    """True iff ``path`` is a genuine RIFF/WAVE PCM file with frames."""
    try:
        with path.open("rb") as f:
            head = f.read(12)
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return False
        import wave

        with wave.open(str(path), "rb") as w:
            return w.getnframes() > 0
    except Exception:
        return False


def config_on_disk(profile: Path) -> dict:
    """Parse the real ``config.json`` the running app persisted."""
    cfg = profile / "config.json"
    if not cfg.exists():
        return {}
    try:
        return json.loads(cfg.read_text("utf-8"))
    except Exception:
        return {}


def history_on_disk(profile: Path) -> list:
    h = profile / "history.json"
    if not h.exists():
        return []
    try:
        data = json.loads(h.read_text("utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        return data.get("history", []) or []
    return data if isinstance(data, list) else []


def installed_voice_files(profile: Path) -> list[str]:
    """Filenames of voices that have BOTH .onnx and .onnx.json on disk
    in the running app's real profile."""
    vdir = profile / "voices"
    if not vdir.exists():
        return []
    out = []
    for p in sorted(vdir.glob("*.onnx")):
        if (vdir / f"{p.name}.json").exists():
            out.append(p.name)
    return out
