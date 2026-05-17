"""Launch reader_app_qt.py with the E2E command server, ping it,
query /state, drive a couple of control routes, then quit. Proves the
full Qt app composition (engine + overlay + tray + hotkeys + command
server) wires up end-to-end."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PORT = 51677


def _get(path: str):
    return urllib.request.urlopen(
        f"http://127.0.0.1:{PORT}{path}", timeout=4).read()


def _post(path: str, body=None):
    data = b"" if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"} if body else {})
    return urllib.request.urlopen(req, timeout=6).read()


def main() -> None:
    env = os.environ.copy()
    env["PIPPAL_DATA_DIR"] = os.path.join(ROOT, ".e2e-data", "qt-smoke")
    env["PIPPAL_E2E_COMMAND_SERVER"] = "1"
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "reader_app_qt.py")],
        cwd=ROOT, env=env)
    try:
        for _ in range(80):
            try:
                _get("/ping")
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise SystemExit("command server never came up")
        print("ping OK")

        state = json.loads(_get("/state"))
        print("frontend:", state.get("frontend"))
        print("engines:", state.get("engines"))
        print("hotkey_actions:", state.get("hotkey_actions"))

        _post("/settings")
        time.sleep(1.0)
        state = json.loads(_get("/state"))
        print("settings_open:", state.get("settings_open"))
        print("settings_var keys:", sorted(state.get("settings_vars", {})))

        out = _post("/ui/set", {"var_key": "auto_hide_ms", "value": 2500})
        st = json.loads(out)
        print("ui.set auto_hide_ms ->",
              st.get("settings_vars", {}).get("auto_hide_ms"))

        out = _post("/settings/apply",
                    {"values": {"overlay_y_offset": 175}, "close": False})
        st = json.loads(out)
        print("apply overlay_y_offset ->", st.get("config", {}).get(
            "overlay_y_offset"))
        print("SMOKE OK")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
