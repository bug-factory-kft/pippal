"""Tests for `context_menu_status` partial-state branch.

`context_menu_installed` used to return True if any extension was
registered; round-1 fixed it to require all. The new
`context_menu_status` returns 'all' / 'partial' / 'none' so the
Settings UI can warn about drift. These tests pin the three-way
behaviour by mocking `subprocess.run`."""

from __future__ import annotations

from unittest.mock import patch

from pippal.context_menu import (
    context_menu_installed,
    context_menu_status,
)


class _Result:
    """Tiny stand-in for `subprocess.CompletedProcess`."""
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


class TestContextMenuStatus:
    def test_all_extensions_present(self):
        with patch("pippal.context_menu.subprocess.run",
                   return_value=_Result(0)):
            assert context_menu_status() == "all"
            assert context_menu_installed() is True

    def test_no_extensions_present(self):
        with patch("pippal.context_menu.subprocess.run",
                   return_value=_Result(1)):
            assert context_menu_status() == "none"
            assert context_menu_installed() is False

    def test_partial_extensions_present(self):
        # First reg query succeeds, second fails — i.e. .txt has the
        # entry but .md doesn't. The Settings UI should show ⚠.
        results = iter([_Result(0), _Result(1)])
        with patch("pippal.context_menu.subprocess.run",
                   side_effect=lambda *a, **kw: next(results)):
            assert context_menu_status() == "partial"
            # The boolean view treats partial as "not installed" so
            # the user gets prompted to re-run Install.
        results = iter([_Result(0), _Result(1)])
        with patch("pippal.context_menu.subprocess.run",
                   side_effect=lambda *a, **kw: next(results)):
            assert context_menu_installed() is False
