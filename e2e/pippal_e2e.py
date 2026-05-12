from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

try:
    import psutil
except ModuleNotFoundError:  # pragma: no cover - setup error path
    psutil = None  # type: ignore[assignment]

CMD_SERVER_PORT = 51677


class CommandEndpointUnavailable(AssertionError):
    """Raised when the running app does not expose an E2E command endpoint."""


def wait_for_port_or_process_exit(
    process: subprocess.Popen[str],
    *,
    port: int = CMD_SERVER_PORT,
    timeout: float = 20.0,
) -> None:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                f"PipPal exited before opening 127.0.0.1:{port}.\n"
                f"exit code: {process.returncode}\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(
        f"127.0.0.1:{port} did not open in time: {last_error}. "
        f"Process is still running with pid {process.pid}."
    )


def assert_port_free(port: int = CMD_SERVER_PORT) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise AssertionError(
                f"127.0.0.1:{port} is already in use. Close running PipPal instances first."
            )


def launch_public_app(public_root: Path, data_root: Path) -> subprocess.Popen[str]:
    piper_exe = public_root / "piper" / "piper.exe"
    if not piper_exe.is_file():
        raise AssertionError(
            f"Public checkout is missing {piper_exe}. Run e2e/run-local.ps1 without -SkipSetup."
        )
    voice = data_root / "voices" / "en_US-ryan-high.onnx"
    if not voice.is_file():
        raise AssertionError(
            f"Data root is missing default voice {voice}. Run e2e/run-local.ps1 without -SkipSetup."
        )

    env = os.environ.copy()
    env["PIPPAL_DATA_DIR"] = str(data_root)
    return subprocess.Popen(
        [sys.executable, str(public_root / "reader_app.py")],
        cwd=public_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def terminate_process_tree(process: subprocess.Popen[str], timeout: float = 6.0) -> None:
    if psutil is None:
        raise AssertionError("Install e2e/requirements.txt before running live E2E tests")
    try:
        parent = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        return

    children = parent.children(recursive=True)
    for child in children:
        child.terminate()
    parent.terminate()
    _gone, alive = psutil.wait_procs([parent, *children], timeout=timeout)
    for proc in alive:
        proc.kill()


def open_settings_window(timeout: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: AssertionError | None = None
    while time.monotonic() < deadline:
        try:
            post_empty("/settings")
            return wait_for_runtime_settings_open()
        except AssertionError as exc:
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"/settings command did not succeed: {last_error}")


def open_voice_manager_via_command(timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: AssertionError | None = None
    while time.monotonic() < deadline:
        try:
            post_empty("/voice-manager")
            return
        except AssertionError as exc:
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"/voice-manager command did not succeed: {last_error}")


def wait_for_runtime_settings_open(timeout: float = 10.0) -> dict[str, Any]:
    return wait_for_state(
        lambda current: current.get("settings_open") is True,
        timeout=timeout,
        description="Settings window",
    )


def post_empty(path: str, timeout: float = 3.0) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{CMD_SERVER_PORT}{path}",
        data=b"",
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise AssertionError(f"{path} returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        message = f"{path} returned HTTP {exc.code}: {body.strip()}"
        if exc.code == 404:
            raise CommandEndpointUnavailable(message) from exc
        raise AssertionError(message) from exc
    except OSError as exc:
        raise AssertionError(f"{path} request failed: {exc}") from exc


def post_json(path: str, body: dict[str, Any], *, expected_status: int = 200) -> Any:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{CMD_SERVER_PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", "replace")
    except OSError as exc:
        raise AssertionError(f"{path} request failed: {exc}") from exc

    if status != expected_status:
        raise AssertionError(
            f"{path} returned HTTP {status}, expected {expected_status}: {raw.strip()}"
        )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def get_runtime_state(timeout: float = 3.0) -> dict[str, Any]:
    request = urllib.request.Request(f"http://127.0.0.1:{CMD_SERVER_PORT}/state")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise CommandEndpointUnavailable("/state returned HTTP 404") from exc
        body = exc.read().decode("utf-8", "replace")
        raise AssertionError(f"/state returned HTTP {exc.code}: {body.strip()}") from exc
    except OSError as exc:
        raise AssertionError(f"/state request failed: {exc}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"/state returned non-JSON body: {body[:300]}") from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"/state returned non-object payload: {payload!r}")
    return payload


def wait_for_state(
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: float = 10.0,
    description: str = "state predicate",
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        state = get_runtime_state()
        last_state = state
        if predicate(state):
            return state
        time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for {description}. Last state: {last_state}")


def apply_settings(values: dict[str, Any], *, close: bool = False) -> dict[str, Any]:
    payload = post_json("/settings/apply", {"values": values, "close": close})
    if not isinstance(payload, dict):
        raise AssertionError(f"/settings/apply returned non-object payload: {payload!r}")
    return payload


def ui_click(target: dict[str, Any], *, confirm: bool = True) -> dict[str, Any]:
    payload = post_json("/ui/click", {"target": target, "confirm": confirm})
    if not isinstance(payload, dict):
        raise AssertionError(f"/ui/click returned non-object payload: {payload!r}")
    return payload


def ui_type(target: dict[str, Any], text: str, *, clear: bool = True) -> dict[str, Any]:
    payload = post_json("/ui/type", {"target": target, "text": text, "clear": clear})
    if not isinstance(payload, dict):
        raise AssertionError(f"/ui/type returned non-object payload: {payload!r}")
    return payload


def ui_set(var_key: str, value: Any) -> dict[str, Any]:
    payload = post_json("/ui/set", {"var_key": var_key, "value": value})
    if not isinstance(payload, dict):
        raise AssertionError(f"/ui/set returned non-object payload: {payload!r}")
    return payload


def ui_select(target: dict[str, Any], value: str) -> dict[str, Any]:
    payload = post_json("/ui/select", {"target": target, "value": value})
    if not isinstance(payload, dict):
        raise AssertionError(f"/ui/select returned non-object payload: {payload!r}")
    return payload


def ui_overlay_click(tag: str) -> dict[str, Any]:
    payload = post_json("/ui/overlay-click", {"tag": tag})
    if not isinstance(payload, dict):
        raise AssertionError(f"/ui/overlay-click returned non-object payload: {payload!r}")
    return payload


def controls(state: dict[str, Any], *, title: str | None = None) -> list[dict[str, Any]]:
    if title is None:
        raw = state.get("controls", [])
    else:
        raw = []
        for window in state.get("windows", []):
            if title.lower() in str(window.get("title", "")).lower():
                raw.extend(window.get("controls", []))
    if not isinstance(raw, list):
        raise AssertionError(f"Runtime state did not include controls: {state}")
    return [control for control in raw if isinstance(control, dict)]


def assert_controls_cover(
    state: dict[str, Any],
    *,
    variables: Iterable[str] = (),
    buttons: Iterable[str] = (),
    labels: Iterable[str] = (),
    title: str | None = None,
) -> None:
    items = controls(state, title=title)
    missing_vars = [
        key for key in variables
        if not any(control.get("variable") == key for control in items)
    ]
    missing_buttons = [
        text for text in buttons
        if not any(control.get("role") == "button" and control.get("text") == text
                   for control in items)
    ]
    missing_labels = [
        label for label in labels
        if not any(control.get("label") == label or control.get("text") == label
                   for control in items)
    ]
    if missing_vars or missing_buttons or missing_labels:
        sample = [
            {
                "role": control.get("role"),
                "text": control.get("text"),
                "label": control.get("label"),
                "variable": control.get("variable"),
                "class": control.get("class"),
            }
            for control in items
        ]
        raise AssertionError(
            "UI coverage inventory missing "
            f"vars={missing_vars}, buttons={missing_buttons}, labels={missing_labels}. "
            f"Controls: {sample}"
        )


def assert_actionable_controls_accounted_for(
    state: dict[str, Any],
    *,
    title: str,
    variables: Iterable[str],
    buttons: Iterable[str],
    labels: Iterable[str],
) -> None:
    allowed_variables = set(variables)
    allowed_buttons = set(buttons)
    allowed_labels = set(labels)
    missing: list[dict[str, Any]] = []
    for control in controls(state, title=title):
        role = str(control.get("role") or "")
        if role not in {"button", "input", "select", "checkbox", "slider", "text"}:
            continue
        variable = str(control.get("variable") or "")
        text = str(control.get("text") or "")
        label = str(control.get("label") or "")
        if variable and variable in allowed_variables:
            continue
        if role == "button" and text in allowed_buttons:
            continue
        if label and label in allowed_labels:
            continue
        missing.append({
            "role": role,
            "text": text,
            "label": label,
            "variable": variable,
            "class": control.get("class"),
        })
    if missing:
        raise AssertionError(f"Actionable controls are not covered by manifest: {missing}")


def find_control(
    state: dict[str, Any],
    *,
    label: str | None = None,
    text: str | None = None,
    role: str | None = None,
    variable: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    for control in controls(state, title=title):
        if label is not None and control.get("label") != label:
            continue
        if text is not None and control.get("text") != text:
            continue
        if role is not None and control.get("role") != role:
            continue
        if variable is not None and control.get("variable") != variable:
            continue
        return control
    raise AssertionError(
        f"Control not found: label={label!r}, text={text!r}, "
        f"role={role!r}, variable={variable!r}, title={title!r}"
    )


def assert_window_texts_contain(state: dict[str, Any], expected: Iterable[str]) -> None:
    texts = [str(text) for text in state.get("settings_texts", [])]
    haystack = "\n".join(texts).lower()
    missing = [needle for needle in expected if needle.lower() not in haystack]
    if missing:
        raise AssertionError(f"Settings window missing {missing}. Visible text:\n{haystack}")


def assert_backend_class(state: dict[str, Any], expected: str) -> None:
    actual = state.get("backend_class")
    if actual != expected:
        raise AssertionError(f"Expected backend_class={expected!r}, got {actual!r}: {state}")


def assert_audio_chunk_ready(state: dict[str, Any], *, min_size: int = 1000) -> None:
    chunks = state.get("audio_chunks")
    if not isinstance(chunks, list):
        raise AssertionError(f"Runtime state did not include audio_chunks: {state}")
    ready = [
        chunk for chunk in chunks
        if isinstance(chunk, dict)
        and chunk.get("exists") is True
        and int(chunk.get("size") or 0) >= min_size
        and chunk.get("riff_wave") is True
    ]
    if not ready:
        raise AssertionError(
            f"No generated RIFF/WAVE chunk >= {min_size} bytes was visible. "
            f"audio_chunks={chunks!r}"
        )


def wait_for_audio_chunk(
    *,
    backend_class: str,
    min_size: int = 1000,
    timeout: float = 35.0,
) -> dict[str, Any]:
    def has_audio(current: dict[str, Any]) -> bool:
        if current.get("backend_class") != backend_class:
            return False
        if current.get("is_speaking") is not True:
            return False
        try:
            assert_audio_chunk_ready(current, min_size=min_size)
        except AssertionError:
            return False
        return True

    return wait_for_state(
        has_audio,
        timeout=timeout,
        description=f"{backend_class} generated playback WAV",
    )


def run_source_open_file_helper(public_root: Path, path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pippal.open_file", str(path)],
        cwd=public_root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"source open_file helper failed with {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
