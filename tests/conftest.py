"""tests/ conftest — unit-suite bootstrap for Windows CI safety.

This module is auto-discovered by pytest at collection time for all tests
under the ``tests/`` directory.

Safety fixture
--------------
On a headless Windows CI runner that has NO audio device (the most common
cause of unit-test hangs: ``winsound.PlaySound`` blocking indefinitely when
no audio driver is initialised), a function-scoped *autouse* fixture
pre-patches ``winsound.PlaySound`` to a no-op before every test runs.

Key properties:
- **Only active on Windows** (non-Windows runners already get a no-op stub
  module in the root ``conftest.py``).
- **Function-scoped**, so any test that needs specific winsound behaviour
  (raise, assert-called, etc.) simply calls ``monkeypatch.setattr`` in its
  own body and the override takes effect — the two ``monkeypatch`` calls
  share the same undo stack for the same test and the per-test override
  wins while that test runs.
- **Uses the same ``monkeypatch`` fixture instance** that the test function
  receives, so teardown restores the original automatically when the test
  ends.
- **Checked against ``sys.platform``** at fixture execution time, not at
  collection time, so the conftest file itself remains portable.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _winsound_noop_on_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard against accidental real winsound calls on headless Windows CI.

    On a Windows runner with no audio device, ``winsound.PlaySound`` can
    hang indefinitely (the OS audio-driver initialisation path blocks).
    This fixture makes the call a no-op for all unit tests; individual
    tests that need specific behaviour (raises, side-effects, call counts)
    override it with their own ``monkeypatch.setattr`` in the test body —
    that override applies on top of this fixture and takes precedence while
    the test runs.
    """
    if sys.platform != "win32":
        return  # Non-Windows: the root conftest already installed a stub.
    try:
        import winsound  # noqa: F401 — Windows-only, always available here
    except ImportError:
        return  # Defensive: shouldn't happen on win32, but be safe.
    monkeypatch.setattr(winsound, "PlaySound", lambda *_a, **_k: None)
