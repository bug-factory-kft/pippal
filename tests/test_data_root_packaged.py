"""AC-1: _resolve_data_root() returns the container-redirected root under MSIX.

Tests monkeypatch ``_get_current_package_full_name`` so no real Windows API
is called.  All tests are Linux-CI-safe.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_with(
    monkeypatch: pytest.MonkeyPatch,
    full_name: str | None,
    localappdata: str,
) -> Path:
    """Call _resolve_data_root() with a controlled identity + env."""
    import pippal.paths as paths_mod

    monkeypatch.setenv("LOCALAPPDATA", localappdata)
    monkeypatch.delenv("PIPPAL_DATA_DIR", raising=False)

    with patch.object(paths_mod, "_get_current_package_full_name", return_value=full_name):
        return paths_mod._resolve_data_root()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# AC-1a: packaged identity → redirected path
# ---------------------------------------------------------------------------


def test_resolve_data_root_packaged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Packaged identity: _resolve_data_root() must point into Packages/<PFN>/LocalCache/Local/PipPal."""
    fake_localappdata = str(tmp_path / "AppData" / "Local")
    full_name = "BugFactory.pippal-pro_1.0.0.0_x64__km6tvv8cv49he"

    result = _resolve_with(monkeypatch, full_name, fake_localappdata)

    expected = (
        Path(fake_localappdata)
        / "Packages"
        / "BugFactory.pippal-pro_km6tvv8cv49he"
        / "LocalCache"
        / "Local"
        / "PipPal"
    )
    assert result == expected, f"Packaged resolver returned {result!r}; expected {expected!r}"


# ---------------------------------------------------------------------------
# AC-1b: unpackaged → plain %LOCALAPPDATA%\PipPal
# ---------------------------------------------------------------------------


def test_resolve_data_root_unpackaged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Unpackaged (probe returns None): _resolve_data_root() == %LOCALAPPDATA%\\PipPal."""
    fake_localappdata = str(tmp_path / "AppData" / "Local")

    result = _resolve_with(monkeypatch, None, fake_localappdata)

    expected = Path(fake_localappdata) / "PipPal"
    assert result == expected, f"Unpackaged resolver returned {result!r}; expected {expected!r}"


# ---------------------------------------------------------------------------
# AC-1c: PIPPAL_DATA_DIR env override wins over both identities
# ---------------------------------------------------------------------------


def test_resolve_data_root_override_wins_over_packaged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PIPPAL_DATA_DIR override must win even when running packaged."""
    import pippal.paths as paths_mod

    override_dir = str(tmp_path / "override")
    monkeypatch.setenv("PIPPAL_DATA_DIR", override_dir)
    full_name = "BugFactory.pippal-pro_1.0.0.0_x64__km6tvv8cv49he"

    with patch.object(paths_mod, "_get_current_package_full_name", return_value=full_name):
        result = paths_mod._resolve_data_root()

    assert result == Path(override_dir), f"Override should win; got {result!r}"


def test_resolve_data_root_override_wins_over_unpackaged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PIPPAL_DATA_DIR override must win when running unpackaged too."""
    import pippal.paths as paths_mod

    override_dir = str(tmp_path / "override")
    monkeypatch.setenv("PIPPAL_DATA_DIR", override_dir)

    with patch.object(paths_mod, "_get_current_package_full_name", return_value=None):
        result = paths_mod._resolve_data_root()

    assert result == Path(override_dir), f"Override should win; got {result!r}"


# ---------------------------------------------------------------------------
# AC-1d: _package_family_name parsing
# ---------------------------------------------------------------------------


def test_package_family_name_parses_well_formed() -> None:
    """Standard 5-part full name → <Name>_<Hash>."""
    from pippal.paths import _package_family_name

    assert _package_family_name("BugFactory.pippal-pro_1.0.0.0_x64__km6tvv8cv49he") == (
        "BugFactory.pippal-pro_km6tvv8cv49he"
    )
    # Real pippal-pro full name from the SPEC
    assert _package_family_name("pippal-pro_0.3.0.54275_x64__km6tvv8cv49he") == (
        "pippal-pro_km6tvv8cv49he"
    )


def test_package_family_name_returns_none_on_malformed() -> None:
    """Fewer than 5 underscore-delimited parts → None."""
    from pippal.paths import _package_family_name

    assert _package_family_name("") is None
    assert _package_family_name("NoUnderscores") is None
    assert _package_family_name("Only_Two") is None
    assert _package_family_name("A_B_C_D") is None  # 4 parts, not 5
