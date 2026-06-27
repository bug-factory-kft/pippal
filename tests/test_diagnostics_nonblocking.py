"""Non-blocking diagnostics transport tests for PipPal core.

Proves the QueueHandler/QueueListener decoupling: emit() on the hot path
must NOT block on file I/O; records still reach disk asynchronously.

Moved from pippal-pro; imports repointed to pippal.diagnostics / pippal.diag_async.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import pytest

import pippal.diag_async as diag_async
import pippal.diagnostics as diag


@pytest.fixture(autouse=True)
def _isolated_diag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect DIAG_DIR to a temp dir and ensure a clean transport per test."""
    diag_dir = tmp_path / "diagnostics"
    diag_dir.mkdir()
    monkeypatch.setattr(diag, "DIAG_DIR", diag_dir)
    diag.configure_diagnostics("off")
    diag._current_level = "off"
    yield diag_dir
    diag.configure_diagnostics("off")
    diag._current_level = "off"


_WRITE_LATENCY_S = 0.005
_BURST = 200


def _install_slow_write(monkeypatch: pytest.MonkeyPatch) -> None:
    real_emit = diag_async.DailyFileHandler.emit

    def slow_emit(self, record):  # type: ignore[no-untyped-def]
        time.sleep(_WRITE_LATENCY_S)
        return real_emit(self, record)

    monkeypatch.setattr(diag_async.DailyFileHandler, "emit", slow_emit)


def _emit_core_playback_burst(n: int) -> None:
    core_logger = logging.getLogger("pippal.playback")
    for i in range(n):
        core_logger.debug(
            "",
            extra={"diag_evt": "playback.chunk", "chunk_index": i, "chunk_total": n},
        )


def test_emit_is_decoupled_from_slow_disk_io(
    _isolated_diag: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Producer-side emit time must NOT scale with file-write latency."""
    _install_slow_write(monkeypatch)
    diag.configure_diagnostics("trace")

    elapsed_holder: dict[str, float] = {}

    def worker() -> None:
        t0 = time.perf_counter()
        _emit_core_playback_burst(_BURST)
        elapsed_holder["producer"] = time.perf_counter() - t0

    th = threading.Thread(target=worker, name="playback-sim")
    th.start()
    th.join(timeout=10.0)

    assert not th.is_alive(), "Playback thread hung — emit() blocked on file I/O."

    producer_time = elapsed_holder["producer"]
    synchronous_floor = _BURST * _WRITE_LATENCY_S  # ~1.0 s if I/O were on-thread

    assert producer_time < synchronous_floor * 0.5, (
        f"Producer-side emit took {producer_time:.3f}s — expected << "
        f"{synchronous_floor:.3f}s (the synchronous-write floor). "
        "emit() is still blocked by file I/O on the hot path."
    )

    # The background listener must have written every record to disk.
    diag.flush()
    # Core uses pippal-YYYY-MM-DD.log (no 'pro')
    files = list(_isolated_diag.glob("pippal-*.log"))
    assert files, "No daily log file written by the background listener."
    content = "\n".join(p.read_text(encoding="utf-8") for p in files)
    count = content.count('"evt": "playback.chunk"')
    assert count == _BURST, (
        f"Expected {_BURST} playback.chunk records; found {count}."
    )


def test_no_third_party_debug_flood_reaches_the_queue(
    _isolated_diag: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Noise reduction: unrelated third-party DEBUG records must NOT be written."""
    diag.configure_diagnostics("trace")

    logging.getLogger("PIL").debug("noisy third party debug line")
    logging.getLogger("urllib3.connectionpool").debug("another noisy debug line")
    logging.getLogger("pippal.playback").debug(
        "", extra={"diag_evt": "playback.chunk", "chunk_index": 0}
    )

    diag.flush()
    files = list(_isolated_diag.glob("pippal-*.log"))
    content = "\n".join(p.read_text(encoding="utf-8") for p in files) if files else ""

    assert '"evt": "playback.chunk"' in content, "Core record should be captured."
    assert "noisy" not in content, "Third-party DEBUG noise leaked into diag log."
    assert '"logger": "PIL"' not in content
    assert '"logger": "urllib3' not in content
