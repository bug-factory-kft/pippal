"""PipPal — core structured-record bridge (CORE-NO-PRO-LEAK seam).

Recognises stdlib logging records on allowlisted core loggers
(``pippal.playback``) carrying a ``diag_evt`` marker and routes them
through the diagnostics privacy guard. Third-party loggers setting
``diag_evt`` are not honoured (not in allowlist) and fall through to
the redacted legacy path.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from typing import Any

# The record attribute the core emit sets (via ``logging`` ``extra=``).
CORE_DIAG_EVT_ATTR = "diag_evt"

# Only these core logger names are trusted to carry a structured ``diag_evt``.
CORE_DIAG_LOGGER_ALLOWLIST: frozenset[str] = frozenset({"pippal.playback"})


def core_record_payload(
    record: logging.LogRecord,
    *,
    allowed_keys: Iterable[str],
    event_name_re: re.Pattern[str],
    build_payload: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any] | None:
    """Return a whitelisted payload for a recognised core record, or None.

    Recognised iff ``record.name`` is in ``CORE_DIAG_LOGGER_ALLOWLIST`` and
    carries a valid ``diag_evt`` name. Validates fields via ``build_payload``.
    Never reads the record message body.
    """
    if record.name not in CORE_DIAG_LOGGER_ALLOWLIST:
        return None
    evt_name = getattr(record, CORE_DIAG_EVT_ATTR, None)
    if not isinstance(evt_name, str) or not event_name_re.match(evt_name):
        return None
    fields: dict[str, Any] = {}
    for key in allowed_keys:
        if hasattr(record, key):
            fields[key] = getattr(record, key)
    return build_payload(evt_name, fields)
