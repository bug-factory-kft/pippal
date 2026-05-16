"""Local pronunciation / substitution dictionary.

A small, JSON-backed list of text-rewrite rules that runs immediately
before a chunk is handed to the synthesis backend. Aimed at the daily
pain points users hit with Piper: acronyms (``NASA`` → ``en ay es ay``),
imported names (``Müller`` → ``Myuler``), URLs (``github.com`` →
``github dot com``) and mixed-punctuation prefixes like ``Dr.``.

Design notes:

- Storage lives at ``<DATA_ROOT>/pronunciation.json`` so it follows the
  same writable-data convention as ``config.json`` and ``history.json``
  (and gets redirected by the ``PIPPAL_DATA_DIR`` env var for tests).
- The JSON document carries a ``schema_version`` so we can evolve the
  rule shape without losing the user's data.
- Writes are atomic (temp file + ``os.replace``) — same pattern as
  history / config.
- ``apply()`` returns an :class:`ApplyResult` carrying the transformed
  text plus a small audit trail so the Settings "Test" button can show
  which rules fired and the synthesis hook can be inspected without
  threading a second return value through every call.
- Determinism: rules are applied in a fixed order — ``priority`` ascending,
  then insertion order — and ``apply()`` never depends on dict iteration
  order or environment state. The same dictionary + input always
  produces the same output.

Scope boundary with the Pro distribution:

    Core's pronunciation dictionary is independent of any Pro features.
    If both Core and Pro engines exist on the same machine, they operate
    on their own respective rule stores and never share data. The Core
    module deliberately does not import, reference or react to the Pro
    pronunciation engine.

The hook in :mod:`pippal.playback` always calls :func:`apply` — an empty
dictionary is a no-op, so Core users with no rules pay only a JSON load
on first use and an empty-list scan per chunk thereafter.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from .paths import DATA_ROOT

SCHEMA_VERSION: int = 1

RuleKind = Literal["exact_word", "phrase", "substring"]
_VALID_KINDS: frozenset[str] = frozenset(("exact_word", "phrase", "substring"))


def _default_path() -> Path:
    return DATA_ROOT / "pronunciation.json"


@dataclass(frozen=True)
class PronunciationRule:
    """A single text-rewrite rule.

    - ``match``: literal source string. Never a regex — we never want a
      user to accidentally drop a runaway pattern into the synthesis
      hot path.
    - ``replacement``: literal output string.
    - ``kind``:
        - ``"exact_word"`` matches only when ``match`` stands as a whole
          token (word boundaries via :data:`_WORD_BOUNDARY`). Locale-
          aware enough for Hungarian / German letters with diacritics
          (``Müller``, ``István``) by treating any letter, digit or
          underscore as part of the same token.
        - ``"phrase"`` matches a multi-word literal, anchored on the
          outer boundaries. Handy for things like ``"Dr. Smith"`` where
          the inner punctuation makes ``exact_word`` brittle.
        - ``"substring"`` matches anywhere — used sparingly for things
          like ``"github.com"`` where the user knows they want
          punctuation captured.
    - ``case_sensitive``: ``None`` = sensible default per kind
      (``exact_word`` → case-insensitive, others → case-sensitive).
      Set explicitly to override.
    - ``priority``: smaller numbers run first. Stable tie-break on
      insertion order.
    """

    match: str
    replacement: str
    kind: RuleKind = "exact_word"
    case_sensitive: bool | None = None
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.match:
            raise ValueError("PronunciationRule.match must be non-empty")
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"PronunciationRule.kind must be one of {sorted(_VALID_KINDS)},"
                f" got {self.kind!r}"
            )

    def effective_case_sensitive(self) -> bool:
        if self.case_sensitive is not None:
            return self.case_sensitive
        # Acronyms / words: case-insensitive by default so "NASA" and
        # "nasa" both fire. Phrases / substrings: respect the user's
        # casing — they typed it for a reason (e.g. URLs).
        return self.kind != "exact_word"

    def to_dict(self) -> dict[str, Any]:
        return {
            "match": self.match,
            "replacement": self.replacement,
            "kind": self.kind,
            "case_sensitive": self.case_sensitive,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PronunciationRule:
        return cls(
            match=str(data["match"]),
            replacement=str(data.get("replacement", "")),
            kind=str(data.get("kind", "exact_word")),  # type: ignore[arg-type]
            case_sensitive=(
                None
                if data.get("case_sensitive") is None
                else bool(data["case_sensitive"])
            ),
            priority=int(data.get("priority", 100)),
        )


@dataclass(frozen=True)
class AuditEntry:
    """One firing of a rule against the input.

    The Settings "Test" button shows these so the user can tell which
    rule was responsible for a given substitution; tests assert on
    them to pin behaviour."""

    rule: PronunciationRule
    occurrences: int


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of :meth:`PronunciationDictionary.apply`.

    ``text`` is the transformed string. ``audit`` lists every rule that
    fired at least once, in the same order rules were applied."""

    text: str
    audit: tuple[AuditEntry, ...] = field(default_factory=tuple)


# Unicode-aware word boundary. ``\b`` in Python's ``re`` module is
# defined against ``\w`` which is Unicode-aware on ``str`` patterns
# by default, so "Müller" boundaries work; we just need to make sure
# we always pass ``str`` (which we do).
_WORD_BOUNDARY = r"\b"


def _compile_pattern(rule: PronunciationRule) -> re.Pattern[str]:
    flags = 0 if rule.effective_case_sensitive() else re.IGNORECASE
    escaped = re.escape(rule.match)
    if rule.kind == "exact_word":
        pattern = rf"{_WORD_BOUNDARY}{escaped}{_WORD_BOUNDARY}"
    elif rule.kind == "phrase":
        # Anchor on outer boundaries: a leading / trailing letter would
        # make the phrase a false fragment match, but inner whitespace
        # / punctuation inside the phrase is fine.
        left = _WORD_BOUNDARY if rule.match[:1].isalnum() else ""
        right = _WORD_BOUNDARY if rule.match[-1:].isalnum() else ""
        pattern = f"{left}{escaped}{right}"
    else:  # substring
        pattern = escaped
    return re.compile(pattern, flags)


class PronunciationDictionary:
    """Mutable container for :class:`PronunciationRule` plus persistence.

    Thread-safety: a single re-entrant lock guards both the in-memory
    list and the on-disk file. Reads (``apply``, ``list_rules``) take
    the lock briefly to copy out a snapshot; writes hold it for the
    duration of the atomic save.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path if path is not None else _default_path()
        self._rules: list[PronunciationRule] = []
        self._lock = threading.RLock()
        self._compiled: list[tuple[PronunciationRule, re.Pattern[str]]] = []

    # ---- persistence -----------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def load(self, path: Path | None = None) -> PronunciationDictionary:
        """Load rules from disk. Missing file = empty dictionary."""
        target = path if path is not None else self._path
        with self._lock:
            self._path = target
            self._rules = list(_read_rules_file(target))
            self._recompile_locked()
        return self

    def save(self) -> None:
        with self._lock:
            _write_rules_file(self._path, self._rules)

    # ---- CRUD ------------------------------------------------------------

    def list_rules(self) -> list[PronunciationRule]:
        with self._lock:
            return list(self._rules)

    def add_rule(self, rule: PronunciationRule) -> None:
        with self._lock:
            self._rules.append(rule)
            self._recompile_locked()

    def update_rule(self, index: int, rule: PronunciationRule) -> None:
        with self._lock:
            if not 0 <= index < len(self._rules):
                raise IndexError(f"no rule at index {index}")
            self._rules[index] = rule
            self._recompile_locked()

    def delete_rule(self, index: int) -> PronunciationRule:
        with self._lock:
            if not 0 <= index < len(self._rules):
                raise IndexError(f"no rule at index {index}")
            removed = self._rules.pop(index)
            self._recompile_locked()
            return removed

    def replace_all(self, rules: list[PronunciationRule]) -> None:
        with self._lock:
            self._rules = list(rules)
            self._recompile_locked()

    # ---- application -----------------------------------------------------

    def apply(self, text: str) -> ApplyResult:
        """Apply every rule to ``text``. Empty dictionary = no-op."""
        if not text:
            return ApplyResult(text=text, audit=())
        with self._lock:
            snapshot = list(self._compiled)
        if not snapshot:
            return ApplyResult(text=text, audit=())

        out = text
        audit: list[AuditEntry] = []
        for rule, pattern in snapshot:
            new_out, n = pattern.subn(rule.replacement, out)
            if n:
                audit.append(AuditEntry(rule=rule, occurrences=n))
                out = new_out
        return ApplyResult(text=out, audit=tuple(audit))

    # ---- import / export -------------------------------------------------

    def export_to_file(self, path: Path) -> None:
        with self._lock:
            _write_rules_file(path, self._rules)

    def import_from_file(
        self,
        path: Path,
        *,
        replace: bool = False,
    ) -> int:
        """Read rules from ``path``. With ``replace=True`` the existing
        rule set is discarded; otherwise the imported rules are appended.

        Returns the number of rules imported."""
        imported = list(_read_rules_file(path))
        with self._lock:
            if replace:
                self._rules = imported
            else:
                self._rules.extend(imported)
            self._recompile_locked()
        return len(imported)

    # ---- internals -------------------------------------------------------

    def _recompile_locked(self) -> None:
        # Stable sort: priority ascending, ties broken by insertion order
        # via enumerate-pair keying.
        ordered = sorted(
            enumerate(self._rules), key=lambda pair: (pair[1].priority, pair[0])
        )
        compiled: list[tuple[PronunciationRule, re.Pattern[str]]] = []
        for _idx, rule in ordered:
            try:
                compiled.append((rule, _compile_pattern(rule)))
            except re.error as exc:
                # Should be impossible because we re.escape every match,
                # but log loudly rather than crashing playback.
                print(
                    f"[pronunciation] skipped invalid rule {rule.match!r}: {exc}",
                    file=sys.stderr,
                )
        self._compiled = compiled


# ---- file IO ------------------------------------------------------------

_io_lock = threading.Lock()


def _read_rules_file(path: Path) -> list[PronunciationRule]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text("utf-8"))
    except Exception as exc:
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            path.replace(backup)
        except Exception:
            pass
        print(
            f"[pronunciation] {path} unreadable ({exc}); moved to {backup}",
            file=sys.stderr,
        )
        return []
    if isinstance(data, list):
        # Legacy / very-old shape: a bare list of rule dicts.
        raw_rules: list[Any] = data
    elif isinstance(data, dict):
        raw_rules = list(data.get("rules", []) or [])
    else:
        return []
    out: list[PronunciationRule] = []
    for entry in raw_rules:
        if not isinstance(entry, dict):
            continue
        try:
            out.append(PronunciationRule.from_dict(entry))
        except Exception as exc:
            print(
                f"[pronunciation] skipped malformed rule {entry!r}: {exc}",
                file=sys.stderr,
            )
    return out


def _write_rules_file(path: Path, rules: list[PronunciationRule]) -> None:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rules": [r.to_dict() for r in rules],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    with _io_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))


# ---- process-wide singleton --------------------------------------------

_singleton_lock = threading.Lock()
_singleton: PronunciationDictionary | None = None


def get_dictionary() -> PronunciationDictionary:
    """Return the process-wide dictionary, loading from disk on first
    access. Resolving DATA_ROOT lazily here (rather than at import time)
    lets tests redirect via ``PIPPAL_DATA_DIR`` without import-order
    games."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            d = PronunciationDictionary(_default_path())
            d.load()
            _singleton = d
        return _singleton


def reset_dictionary_for_tests() -> None:
    """Drop the cached singleton. Test-only — call from a fixture or
    monkeypatch that already redirects ``PIPPAL_DATA_DIR``."""
    global _singleton
    with _singleton_lock:
        _singleton = None


__all__ = [
    "SCHEMA_VERSION",
    "ApplyResult",
    "AuditEntry",
    "PronunciationDictionary",
    "PronunciationRule",
    "get_dictionary",
    "replace",
    "reset_dictionary_for_tests",
]
