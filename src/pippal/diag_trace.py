"""PipPal — bridge-call + lifecycle trace instrumentation.

When diagnostics trace is on, wraps every JS-callable bridge method to emit
``bridge.call`` START/END/ERROR events (method name, duration_ms, ok/error
type only — args/return values never touched). ``instrument_bridge_methods``
is a generic class decorator usable on any bridge class (core or Pro).
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from . import diagnostics as _diag

EVT_BRIDGE_CALL = "bridge.call"
EVT_LIFECYCLE = "lifecycle"

# Public method names to leave un-instrumented (high-frequency pollers).
_NO_WRAP_NAMES: frozenset[str] = frozenset(
    {
        "engine_state",
        # diag_js is the JS-side breadcrumb receiver; wrapping it would create a
        # recursive trace loop.
        "diag_js",
    }
)


def event_async(name: str, **fields: Any) -> None:
    """Emit a metadata-only structured event without a flush barrier.

    Like diagnostics.event but non-blocking: only enqueues on the background
    transport. No-op when off.
    """
    if _diag.current_level() == "off":
        return
    if not _diag._EVENT_NAME_RE.match(name):
        return

    payload = _diag._build_diag_payload(name, fields)

    record = _diag._DIAG_LOGGER.makeRecord(
        name=_diag._DIAG_LOGGER_NAME,
        level=logging.DEBUG,
        fn="",
        lno=0,
        msg="",
        args=(),
        exc_info=None,
    )
    setattr(record, _diag._DIAG_FIELDS_ATTR, payload)
    _diag._DIAG_LOGGER.handle(record)
    # NO flush — the listener drains asynchronously.


def lifecycle_event(phase: str, **fields: Any) -> None:
    """Emit a non-bridge lifecycle marker (window/notification/hotkey/engine).

    ``phase`` is an identifier (e.g. ``window_opened``, ``hotkey_triggered``).
    """
    event_async(EVT_LIFECYCLE, phase=phase, **fields)


def _should_wrap(name: str, attr: Any) -> bool:
    """True iff *name*/*attr* is a public JS-callable bridge method to wrap."""
    if name.startswith("_"):
        return False
    if name in _NO_WRAP_NAMES:
        return False
    return callable(attr)


def _make_traced(name: str, func: Callable[..., Any]) -> Callable[..., Any]:
    """Return a wrapper around *func* that emits bridge.call events."""

    @functools.wraps(func)
    def _traced(*args: Any, **kwargs: Any) -> Any:
        if _diag.current_level() == "off":
            return func(*args, **kwargs)

        event_async(EVT_BRIDGE_CALL, method=name, phase="start")
        start = time.monotonic()
        try:
            result = func(*args, **kwargs)
        except BaseException as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            event_async(
                EVT_BRIDGE_CALL,
                method=name,
                phase="error",
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                ok=False,
            )
            raise
        duration_ms = int((time.monotonic() - start) * 1000)
        event_async(
            EVT_BRIDGE_CALL,
            method=name,
            phase="end",
            duration_ms=duration_ms,
            ok=True,
        )
        return result

    _traced._pippal_traced = True  # type: ignore[attr-defined]
    return _traced


def instrument_bridge_methods(cls: type) -> type:
    """Class decorator: wrap every public method with bridge-call trace events.

    Walks the full MRO (covers every mixin). Idempotent: skips already-traced
    methods. Applicable to any bridge class (core or Pro).
    """
    seen: set[str] = set()
    for klass in cls.__mro__:
        if klass is object:
            continue
        for name in list(vars(klass)):
            if name in seen:
                continue
            try:
                resolved = getattr(cls, name)
            except Exception:
                continue
            if not _should_wrap(name, resolved):
                continue
            seen.add(name)
            if getattr(resolved, "_pippal_traced", False):
                continue
            func = vars(klass).get(name, resolved)
            if not callable(func):
                func = resolved
            setattr(cls, name, _make_traced(name, func))
    return cls
