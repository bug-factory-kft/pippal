"""Launch the existing Tk app, drive it via the command server, and
grab before-screenshots so the PR can show Tk-vs-Qt parity.

Run with the real (non-Store) python:
  py -3.11 docs/migration-qt/_capture_tk.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PORT = 51677


def _post(path: str, body: dict | None = None) -> None:
    data = b"" if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"} if body else {})
    try:
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        print(f"  ({path} -> {e})")


def _window_rect(title_substr: str) -> tuple[int, int, int, int] | None:
    try:
        raw = urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/state", timeout=4).read()
        state = json.loads(raw)
    except Exception:
        return None
    for win in state.get("windows", []):
        if title_substr.lower() in str(win.get("title", "")).lower():
            rect = win.get("rect")
            if rect and len(rect) == 4 and rect[2] > rect[0]:
                return tuple(rect)  # type: ignore[return-value]
    return None


def _grab(name: str, title_substr: str = "PipPal") -> None:
    from PIL import ImageGrab
    img = ImageGrab.grab()
    rect = _window_rect(title_substr)
    if rect is not None:
        pad = 8
        x1, y1, x2, y2 = rect
        img = img.crop((max(0, x1 - pad), max(0, y1 - pad),
                        x2 + pad, y2 + pad))
    out = os.path.join(HERE, f"tk-{name}.png")
    img.save(out)
    print(f"saved {out} ({img.size[0]}x{img.size[1]})")


def main() -> None:
    env = os.environ.copy()
    env["PIPPAL_DATA_DIR"] = os.path.join(ROOT, ".e2e-data", "tk")
    env["PIPPAL_E2E_COMMAND_SERVER"] = "1"
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "reader_app.py")],
        cwd=ROOT, env=env)
    try:
        # wait for command server
        for _ in range(80):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/ping", timeout=1).read()
                break
            except Exception:
                time.sleep(0.25)

        time.sleep(1.0)
        _post("/first-run-check")
        time.sleep(2.5)
        _grab("activation-panel")

        _post("/settings")
        time.sleep(2.5)
        _grab("settings")

        _post("/voice-manager")
        time.sleep(2.5)
        _grab("voice-manager", "Voices")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
