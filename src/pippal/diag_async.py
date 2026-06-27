"""PipPal — non-blocking diagnostics transport (queue handler/listener).

Pure stdlib. QueueHandler on root logger; background QueueListener owns
the DailyFileHandler and does all file I/O off the hot path.
_PipPalOnlyFilter passes only pippal/pippal_pro records into the queue.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import queue
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

# Loggers we care about — 'pippal' covers core; 'pippal_pro' covers Pro when present.
_PIPPAL_LOGGER_PREFIXES: tuple[str, ...] = ("pippal", "pippal_pro")

# Known-noisy third-party DEBUG emitters: raised to WARNING while active.
_NOISY_THIRD_PARTY: tuple[str, ...] = (
    "PIL",
    "urllib3",
    "comtypes",
    "asyncio",
    "httpx",
    "httpcore",
    "websockets",
    "markdown_it",
)

# Marker attached to the QueueHandler so configure_diagnostics can find/remove it.
QUEUE_HANDLER_MARKER = "_pippal_diag_queue_handler"

_NUMERIC_TYPES = (int, float, bool)


# ---------------------------------------------------------------------------
# JSONL formatter
# ---------------------------------------------------------------------------


class JSONLFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def __init__(self, fields_attr: str) -> None:
        super().__init__()
        self._fields_attr = fields_attr

    def format(self, record: logging.LogRecord) -> str:
        ts = (
            datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{int(record.msecs):03d}Z"
        )
        lvl = record.levelname

        diag_fields: dict[str, Any] | None = getattr(record, self._fields_attr, None)
        if diag_fields is not None:
            obj = {"ts": ts, "lvl": lvl, **diag_fields, "logger": record.name}
        else:
            obj = {
                "ts": ts,
                "lvl": lvl,
                "evt": "legacy",
                "_raw_dropped": True,
                "logger": record.name,
            }
            if isinstance(record.args, (tuple, list)):
                safe_args = [a for a in record.args if isinstance(a, _NUMERIC_TYPES)]
                if safe_args:
                    obj["_numeric_args"] = safe_args
        return json.dumps(obj, ensure_ascii=False)


def log_path_for(diag_dir: Path, day: date) -> Path:
    """Return the daily log file path for *day* under *diag_dir*.

    Core filename pattern: ``pippal-YYYY-MM-DD.log`` (no 'pro').
    """
    return diag_dir / f"pippal-{day.isoformat()}.log"


# ---------------------------------------------------------------------------
# Per-day file handler — runs ONLY on the listener thread
# ---------------------------------------------------------------------------


class DailyFileHandler(logging.Handler):
    """Per-day file handler; runs on the QueueListener thread (all I/O off the hot path)."""

    def __init__(
        self,
        *,
        diag_dir_getter: Callable[[], Path],
        redactor: Callable[[logging.LogRecord], logging.LogRecord],
        fields_attr: str,
        retention_days: int,
        max_total_bytes: int,
        level: int = logging.NOTSET,
    ) -> None:
        super().__init__(level)
        self._diag_dir_getter = diag_dir_getter
        self._redactor = redactor
        self._retention_days = retention_days
        self._max_total_bytes = max_total_bytes
        self._current_day: date | None = None
        self._formatter = JSONLFormatter(fields_attr)

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        try:
            diag_dir = self._diag_dir_getter()
            today = datetime.now(tz=UTC).date()
            if today != self._current_day:
                self._current_day = today
                self._prune(diag_dir)
            log_path = log_path_for(diag_dir, today)
            diag_dir.mkdir(parents=True, exist_ok=True)
            safe_record = self._redactor(record)
            line = self._formatter.format(safe_record) + "\n"
            with log_path.open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            self.handleError(record)

    def _prune(self, diag_dir: Path) -> None:
        """Remove files older than retention and enforce the total size cap."""
        if not diag_dir.exists():
            return
        # Core pattern: pippal-YYYY-MM-DD.log
        files = sorted(diag_dir.glob("pippal-*.log"), key=lambda p: p.name)
        today = datetime.now(tz=UTC).date()
        cutoff_date = today - timedelta(days=self._retention_days)
        to_delete: list[Path] = []
        to_keep: list[Path] = []
        for f in files:
            stem = f.stem  # e.g. pippal-2026-06-20
            parts = stem.split("-")
            # pippal-YYYY-MM-DD → ["pippal", "YYYY", "MM", "DD"] → 4 parts
            if len(parts) < 4:
                continue
            try:
                file_day = date(int(parts[1]), int(parts[2]), int(parts[3]))
            except ValueError:
                continue
            if file_day < cutoff_date:
                to_delete.append(f)
            else:
                to_keep.append(f)

        for f in to_delete:
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass

        total = sum(f.stat().st_size for f in to_keep if f.exists())
        for f in to_keep:
            if total <= self._max_total_bytes:
                break
            if f.exists():
                size = f.stat().st_size
                f.unlink(missing_ok=True)
                total -= size


class _PipPalOnlyFilter(logging.Filter):
    """Pass only records emitted by PipPal's own logger trees."""

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        return any(name == p or name.startswith(p + ".") for p in _PIPPAL_LOGGER_PREFIXES)


class AsyncDiagTransport:
    """Owns the queue + listener that decouple emit() from file I/O."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: queue.SimpleQueue[logging.LogRecord] | None = None
        self._queue_handler: logging.handlers.QueueHandler | None = None
        self._listener: logging.handlers.QueueListener | None = None
        self._target_handler: logging.Handler | None = None
        self._saved_levels: dict[str, int] = {}

    @property
    def running(self) -> bool:
        return self._listener is not None

    @property
    def root_handler(self) -> logging.handlers.QueueHandler | None:
        return self._queue_handler

    def flush(self) -> None:
        """Block until the listener has drained every queued record to disk."""
        with self._lock:
            listener = self._listener
            target = self._target_handler
            q = self._queue
            if listener is None or q is None:
                return
            listener.stop()
            new_listener = logging.handlers.QueueListener(q, target, respect_handler_level=True)
            self._listener = new_listener
            new_listener.start()

    def start(self, target_handler: logging.Handler, *, root: logging.Logger) -> None:
        with self._lock:
            if self._listener is not None:
                return

            self._queue = queue.SimpleQueue()
            qhandler = logging.handlers.QueueHandler(self._queue)
            qhandler.addFilter(_PipPalOnlyFilter())
            qhandler.setLevel(logging.NOTSET)
            setattr(qhandler, QUEUE_HANDLER_MARKER, True)

            listener = logging.handlers.QueueListener(
                self._queue, target_handler, respect_handler_level=True
            )

            self._target_handler = target_handler
            self._queue_handler = qhandler
            self._listener = listener

            self._quiet_noisy_loggers()
            root.addHandler(qhandler)
            listener.start()

    def stop(self, *, root: logging.Logger) -> None:
        with self._lock:
            qhandler = self._queue_handler
            listener = self._listener
            target = self._target_handler

            if qhandler is not None:
                root.removeHandler(qhandler)
            if listener is not None:
                listener.stop()
            if qhandler is not None:
                qhandler.close()
            if target is not None:
                target.close()

            self._restore_noisy_loggers()

            self._queue = None
            self._queue_handler = None
            self._listener = None
            self._target_handler = None

    def _quiet_noisy_loggers(self) -> None:
        self._saved_levels = {}
        for name in _NOISY_THIRD_PARTY:
            lg = logging.getLogger(name)
            self._saved_levels[name] = lg.level
            if lg.level == logging.NOTSET or lg.level < logging.WARNING:
                lg.setLevel(logging.WARNING)

    def _restore_noisy_loggers(self) -> None:
        for name, level in self._saved_levels.items():
            logging.getLogger(name).setLevel(level)
        self._saved_levels = {}
