"""Core diagnostics session-start tests.

Moved from pippal-pro; imports repointed to pippal.diagnostics.
Tests that emit_session_start writes a visible log file (app.start) on configure.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest


def _purge_diag_handlers() -> None:
    from pippal.diagnostics import _HANDLER_MARKER

    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, _HANDLER_MARKER, False):
            root.removeHandler(h)
            h.close()


def _all_diag_bytes(diag_dir: Path) -> bytes:
    data = b""
    for p in sorted(diag_dir.rglob("*")):
        if p.is_file():
            data += p.read_bytes()
    return data


def _log_files(diag_dir: Path) -> list[Path]:
    # Core: pippal-YYYY-MM-DD.log
    return sorted(diag_dir.glob("pippal-*.log"))


@pytest.fixture(autouse=True)
def _isolated_diag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import pippal.diagnostics as diag_mod

    diag_dir = tmp_path / "diagnostics"
    diag_dir.mkdir()
    monkeypatch.setattr(diag_mod, "DIAG_DIR", diag_dir)
    diag_mod._current_level = "off"
    _purge_diag_handlers()
    yield diag_dir
    diag_mod._current_level = "off"
    _purge_diag_handlers()


def test_enabling_trace_creates_visible_log_file_without_a_read(_isolated_diag: Path) -> None:
    """Enabling trace must create a visible daily log file immediately via app.start."""
    from pippal.diagnostics import (
        EVT_APP_START,
        configure_diagnostics,
        emit_session_start,
    )

    configure_diagnostics("trace")
    emit_session_start()

    files = _log_files(_isolated_diag)
    assert files, (
        "Enabling trace must create a visible daily log file immediately "
        "(via app.start), even before any synth/import/AI op."
    )
    content = _all_diag_bytes(_isolated_diag).decode("utf-8", errors="replace")
    assert EVT_APP_START in content


def test_emit_session_start_is_noop_when_off(_isolated_diag: Path) -> None:
    """With level=off, emit_session_start must write NOTHING."""
    from pippal.diagnostics import configure_diagnostics, emit_session_start

    configure_diagnostics("off")
    emit_session_start()

    assert _all_diag_bytes(_isolated_diag) == b"", (
        "emit_session_start must be a no-op at level=off."
    )


def test_emit_session_start_carries_no_free_text(_isolated_diag: Path) -> None:
    """The app.start event must contain only whitelisted metadata."""
    import json

    from pippal.diagnostics import (
        ALLOWED_META_KEYS,
        EVT_APP_START,
        configure_diagnostics,
        emit_session_start,
    )

    configure_diagnostics("trace")
    emit_session_start()

    content = _all_diag_bytes(_isolated_diag).decode("utf-8", errors="replace")
    lines = [json.loads(ln) for ln in content.splitlines() if ln.strip()]
    start_lines = [o for o in lines if o.get("evt") == EVT_APP_START]
    assert start_lines, f"No app.start line found in: {content[:300]!r}"

    evt = start_lines[0]
    allowed_structural = {"ts", "lvl", "evt", "logger", "_dropped"}
    for key in evt:
        assert key in allowed_structural or key in ALLOWED_META_KEYS, (
            f"Unexpected key {key!r} in app.start event: {evt!r}"
        )


def test_emit_session_start_includes_system_metadata(_isolated_diag: Path) -> None:
    """The app.start event must include os_platform and python_version."""
    import json

    from pippal.diagnostics import (
        ALLOWED_META_KEYS,
        EVT_APP_START,
        configure_diagnostics,
        emit_session_start,
    )

    configure_diagnostics("trace")
    emit_session_start()

    content = _all_diag_bytes(_isolated_diag).decode("utf-8", errors="replace")
    lines = [json.loads(ln) for ln in content.splitlines() if ln.strip()]
    start_lines = [o for o in lines if o.get("evt") == EVT_APP_START]
    assert start_lines, "No app.start event found"

    evt = start_lines[0]
    assert "os_platform" in evt
    assert "python_version" in evt
    assert isinstance(evt["os_platform"], str) and evt["os_platform"]
    assert isinstance(evt["python_version"], str) and evt["python_version"]

    allowed_structural = {"ts", "lvl", "evt", "logger", "_dropped"}
    for key in evt:
        assert key in allowed_structural or key in ALLOWED_META_KEYS

    for meta_key in ("os_platform", "python_version", "pippal_version",
                     "pippal_pro_version", "pywebview_version"):
        assert meta_key in ALLOWED_META_KEYS


def test_emit_session_start_metadata_values_are_not_user_text(_isolated_diag: Path) -> None:
    """Metadata string values must not contain spaces (the privacy guard)."""
    import json

    from pippal.diagnostics import (
        _IDENTIFIER_VALUE_RE,
        EVT_APP_START,
        configure_diagnostics,
        emit_session_start,
    )

    configure_diagnostics("trace")
    emit_session_start()

    content = _all_diag_bytes(_isolated_diag).decode("utf-8", errors="replace")
    lines = [json.loads(ln) for ln in content.splitlines() if ln.strip()]
    start_lines = [o for o in lines if o.get("evt") == EVT_APP_START]
    assert start_lines

    evt = start_lines[0]
    meta_keys = ("os_platform", "python_version", "pippal_version",
                 "pippal_pro_version", "pywebview_version")
    for k in meta_keys:
        if k not in evt:
            continue
        val = evt[k]
        assert isinstance(val, str)
        assert _IDENTIFIER_VALUE_RE.match(val), (
            f"{k!r} value {val!r} fails the identifier-charset guard"
        )
