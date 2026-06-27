"""Core diagnostics trace regression tests.

Adapted from pippal-pro/tests/test_diagnostics_trace.py.
Tests that use the Pro bridge are repointed to core's PipPalBridge + DiagSettingsBridgeMixin.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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


def _make_bridge(config: dict[str, Any]) -> Any:
    """Create a core PipPalBridge (which includes DiagSettingsBridgeMixin)."""
    from pippal.web_ui.bridge import PipPalBridge

    return PipPalBridge(MagicMock(), config)


# ---------------------------------------------------------------------------
# 1. Baseline: configure("trace") + event() writes to disk
# ---------------------------------------------------------------------------


def test_trace_event_written_to_daily_log(_isolated_diag: Path) -> None:
    from pippal.diagnostics import EVT_SYNTH_START, configure_diagnostics, event

    configure_diagnostics("trace")
    event(EVT_SYNTH_START, engine="kokoro", char_count=12, voice_lang="en-us")

    all_bytes = _all_diag_bytes(_isolated_diag)
    assert all_bytes, "Expected daily log file to be written after event()."
    content = all_bytes.decode("utf-8", errors="replace")
    assert "synth.start" in content


# ---------------------------------------------------------------------------
# 2. set_diag_level must configure process even when save_config fails
# ---------------------------------------------------------------------------


def test_set_diag_level_configures_process_even_when_save_fails(
    _isolated_diag: Path,
    tmp_path: Path,
) -> None:
    """Core bridge: configure_diagnostics must be called BEFORE save_config."""
    import pippal.config as cfg_mod

    import pippal.diagnostics as diag

    config: dict[str, Any] = {"diag_log_level": "off"}
    bridge = _make_bridge(config)

    with patch.object(
        cfg_mod,
        "save_config",
        side_effect=OSError("Simulated: DATA_ROOT not writable"),
    ):
        result = bridge.set_diag_level("trace")

    assert result.get("ok") is False

    # CRITICAL: live-process level must be "trace" regardless of save failure.
    assert diag.current_level() == "trace", (
        f"_current_level must be 'trace' even when save_config fails; "
        f"got {diag.current_level()!r}."
    )

    from pippal.diagnostics import EVT_SYNTH_START, event

    event(EVT_SYNTH_START, engine="kokoro", char_count=7, voice_lang="en-us")
    all_bytes = _all_diag_bytes(_isolated_diag)
    assert all_bytes, "Expected trace event to be written after set_diag_level('trace')."


# ---------------------------------------------------------------------------
# 3. Round-trip: set → save → reload config → reconfigure → event writes
# ---------------------------------------------------------------------------


def test_set_diag_level_round_trip_reload(
    _isolated_diag: Path,
    tmp_path: Path,
) -> None:
    import os

    data_root = tmp_path / "data"
    data_root.mkdir()
    config_path = data_root / "config.json"

    import pippal.config as cfg_mod

    import pippal.diagnostics as diag

    def _save(cfg: dict[str, Any], path: Path = config_path) -> None:
        defaults = cfg_mod._layered_defaults()
        overrides = {k: v for k, v in cfg.items() if k not in defaults or v != defaults[k]}
        tmp_f = path.with_suffix(path.suffix + ".part")
        tmp_f.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
        os.replace(str(tmp_f), str(path))

    def _load(path: Path = config_path) -> dict[str, Any]:
        defaults = cfg_mod._layered_defaults()
        if not path.exists():
            return dict(defaults)
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception:
            return dict(defaults)
        effective = dict(defaults)
        effective.update(data)
        return effective

    with (
        patch.object(cfg_mod, "save_config", side_effect=_save),
        patch.object(cfg_mod, "load_config", side_effect=_load),
    ):
        config: dict[str, Any] = {"diag_log_level": "off"}
        bridge = _make_bridge(config)

        result = bridge.set_diag_level("trace")
        assert result.get("ok") is True, f"set_diag_level failed: {result}"

        assert config_path.exists()
        saved = json.loads(config_path.read_text("utf-8"))
        assert saved.get("diag_log_level") == "trace"

        diag._current_level = "off"
        _purge_diag_handlers()

        reloaded = _load(config_path)
        assert reloaded.get("diag_log_level") == "trace"

        from pippal.diagnostics import configure_diagnostics

        configure_diagnostics(reloaded["diag_log_level"])
        assert diag.current_level() == "trace"

        from pippal.diagnostics import EVT_SYNTH_START, event

        event(EVT_SYNTH_START, engine="kokoro", char_count=3, voice_lang="en-us")
        assert _all_diag_bytes(_isolated_diag), "Expected trace event after reload."


# ---------------------------------------------------------------------------
# 4. Latent defect: _ENUM_VALUE_RE excludes underscore
# ---------------------------------------------------------------------------


def test_enum_value_with_underscore_documents_latent_defect(_isolated_diag: Path) -> None:
    from pippal.diagnostics import EVT_SYNTH_START, _build_diag_payload

    payload = _build_diag_payload(EVT_SYNTH_START, {"engine": "kokoro_v2", "char_count": 5})
    assert "engine" not in payload or payload.get("_dropped", []) != []
    assert payload.get("char_count") == 5


# ---------------------------------------------------------------------------
# 5. Existing valid enum values must not regress
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,key",
    [
        ("en-us", "voice_lang"),
        ("en-gb", "voice_lang"),
        ("unknown", "voice_lang"),
        ("kokoro", "engine"),
        ("pdf", "src_format"),
        ("utf-8", "encoding"),
        ("summary", "action"),
        ("request", "stage"),
    ],
)
def test_enum_value_without_underscore_still_passes(
    _isolated_diag: Path, value: str, key: str
) -> None:
    from pippal.diagnostics import EVT_SYNTH_START, _build_diag_payload

    payload = _build_diag_payload(EVT_SYNTH_START, {key: value})
    assert key in payload, (
        f"'{key}={value}' was incorrectly dropped; payload: {payload!r}"
    )
    assert key not in payload.get("_dropped", [])
