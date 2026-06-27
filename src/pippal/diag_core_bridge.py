"""PipPal — core structured-record bridge (CORE-NO-PRO-LEAK seam).

The public core (``pippal``) can emit plain stdlib ``logging`` records on
a DEDICATED logger name (``pippal.playback``) carrying a ``diag_evt`` marker
plus metadata-only ``extra`` fields (NEVER user text).

This module recognises such a record — but ONLY when its logger name is in
``CORE_DIAG_LOGGER_ALLOWLIST`` — and hands the event name + candidate fields
back to ``diagnostics``' own ``_build_diag_payload`` privacy guard.  A
third-party logger that happens to set ``diag_evt`` is NOT honoured (its name
is not in the allowlist) and falls through to the redacted ``legacy`` path.
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
    """Return a whitelisted payload for a recognised core record, else None.

    Recognised iff ``record.name`` is in ``CORE_DIAG_LOGGER_ALLOWLIST`` AND it
    carries a valid ``diag_evt`` event name.  Candidate metadata fields are
    read from the record attributes named in ``allowed_keys`` and re-validated
    by ``build_payload`` (the diagnostics privacy guard).  The record message
    body is never read.
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
