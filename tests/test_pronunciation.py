"""Unit tests for the local pronunciation dictionary.

Pins the regression examples called out in issue #46: acronyms, names,
URLs, mixed punctuation, plus determinism and the integration hook
inside :mod:`pippal.playback`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pippal import playback, pronunciation
from pippal.engine import TTSEngine
from pippal.pronunciation import (
    SCHEMA_VERSION,
    ApplyResult,
    PronunciationDictionary,
    PronunciationRule,
)


@pytest.fixture()
def empty_dict(tmp_path: Path) -> PronunciationDictionary:
    d = PronunciationDictionary(tmp_path / "pronunciation.json")
    d.load()
    return d


# ---------------------------------------------------------------------------
# Rule shape
# ---------------------------------------------------------------------------


def test_rule_round_trips_through_dict() -> None:
    r = PronunciationRule(
        match="NASA", replacement="en ay es ay",
        kind="exact_word", case_sensitive=None, priority=50,
    )
    assert PronunciationRule.from_dict(r.to_dict()) == r


def test_rule_rejects_empty_match() -> None:
    with pytest.raises(ValueError):
        PronunciationRule(match="", replacement="x")


def test_rule_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        PronunciationRule(match="x", replacement="y",
                          kind="regex")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Regression examples called out in #46
# ---------------------------------------------------------------------------


def test_acronym_NASA_survives_sentence_start_and_midsentence(
    empty_dict: PronunciationDictionary,
) -> None:
    empty_dict.add_rule(PronunciationRule(
        match="NASA", replacement="en ay es ay", kind="exact_word",
    ))
    result = empty_dict.apply("NASA launched it. Then NASA waited.")
    assert result.text == "en ay es ay launched it. Then en ay es ay waited."
    assert result.audit[0].occurrences == 2


def test_name_Istvan_matches_with_locale_boundaries(
    empty_dict: PronunciationDictionary,
) -> None:
    empty_dict.add_rule(PronunciationRule(
        match="István", replacement="Ishtvan", kind="exact_word",
    ))
    result = empty_dict.apply("István arrived. The other István waited.")
    assert result.text == "Ishtvan arrived. The other Ishtvan waited."
    # Diacritic must not eat the leading letter of an unrelated longer
    # word that happens to start with the same prefix.
    result2 = empty_dict.apply("Istvánffy is a different surname.")
    assert result2.text == "Istvánffy is a different surname."


def test_url_github_com_matches_substring_but_not_when_glued(
    empty_dict: PronunciationDictionary,
) -> None:
    empty_dict.add_rule(PronunciationRule(
        match="github.com", replacement="github dot com",
        kind="substring",
    ))
    assert empty_dict.apply("Visit github.com today").text == (
        "Visit github dot com today"
    )
    # Substring fires on `mygithub.commerce` too — that's expected
    # behaviour for `substring`. Users who want the strict form use
    # `phrase`, which IS boundary-aware:
    empty_dict.replace_all([
        PronunciationRule(match="github.com", replacement="github dot com",
                          kind="phrase"),
    ])
    assert empty_dict.apply("Visit github.com today").text == (
        "Visit github dot com today"
    )
    assert empty_dict.apply("Goto mygithub.commerce site").text == (
        "Goto mygithub.commerce site"
    )


def test_mixed_punctuation_Dr_Smith_matches(
    empty_dict: PronunciationDictionary,
) -> None:
    empty_dict.add_rule(PronunciationRule(
        match="Dr. Smith", replacement="Doctor Smith", kind="phrase",
    ))
    assert empty_dict.apply("Met Dr. Smith yesterday.").text == (
        "Met Doctor Smith yesterday."
    )


def test_word_boundary_USB_does_not_match_inside_bus(
    empty_dict: PronunciationDictionary,
) -> None:
    empty_dict.add_rule(PronunciationRule(
        match="USB", replacement="you ess bee", kind="exact_word",
    ))
    assert empty_dict.apply("the bus stopped").text == "the bus stopped"
    assert empty_dict.apply("plug in the USB cable").text == (
        "plug in the you ess bee cable"
    )


# ---------------------------------------------------------------------------
# Determinism, ordering, priority
# ---------------------------------------------------------------------------


def test_apply_is_deterministic_byte_identical(
    empty_dict: PronunciationDictionary,
) -> None:
    empty_dict.add_rule(PronunciationRule(
        match="NASA", replacement="en ay es ay", kind="exact_word",
    ))
    empty_dict.add_rule(PronunciationRule(
        match="USB", replacement="you ess bee", kind="exact_word",
    ))
    text = "NASA sent a USB to NASA again."
    first = empty_dict.apply(text).text
    second = empty_dict.apply(text).text
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


def test_priority_ordering_runs_lower_priority_first(
    empty_dict: PronunciationDictionary,
) -> None:
    # If both rules ran in insertion order, "AAA" would stay; with
    # priority 10 running first, "AAA" → "BBB" → "CCC".
    empty_dict.add_rule(PronunciationRule(
        match="BBB", replacement="CCC", kind="substring", priority=100,
    ))
    empty_dict.add_rule(PronunciationRule(
        match="AAA", replacement="BBB", kind="substring", priority=10,
    ))
    assert empty_dict.apply("AAA").text == "CCC"


def test_empty_dictionary_is_noop(empty_dict: PronunciationDictionary) -> None:
    out = empty_dict.apply("Hello world.")
    assert out.text == "Hello world."
    assert out.audit == ()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_add_update_delete_round_trip(empty_dict: PronunciationDictionary) -> None:
    r1 = PronunciationRule(match="NASA", replacement="en ay es ay")
    r2 = PronunciationRule(match="USB", replacement="you ess bee")
    empty_dict.add_rule(r1)
    empty_dict.add_rule(r2)
    assert empty_dict.list_rules() == [r1, r2]

    r1b = PronunciationRule(match="NASA", replacement="NASA the space agency")
    empty_dict.update_rule(0, r1b)
    assert empty_dict.list_rules()[0] == r1b

    removed = empty_dict.delete_rule(0)
    assert removed == r1b
    assert empty_dict.list_rules() == [r2]


def test_update_out_of_range_raises(empty_dict: PronunciationDictionary) -> None:
    with pytest.raises(IndexError):
        empty_dict.update_rule(7, PronunciationRule(match="x", replacement="y"))


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "pronunciation.json"
    d = PronunciationDictionary(path).load()
    d.add_rule(PronunciationRule(match="NASA", replacement="en ay es ay"))
    d.add_rule(PronunciationRule(
        match="github.com", replacement="github dot com",
        kind="substring", case_sensitive=True, priority=5,
    ))
    d.save()

    payload = json.loads(path.read_text("utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert len(payload["rules"]) == 2

    d2 = PronunciationDictionary(path).load()
    assert d2.list_rules() == d.list_rules()


def test_corrupt_file_is_quarantined(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "pronunciation.json"
    path.write_text("{not valid json", encoding="utf-8")
    d = PronunciationDictionary(path).load()
    assert d.list_rules() == []
    assert path.with_suffix(path.suffix + ".bak").exists()


def test_legacy_bare_list_shape_loads(tmp_path: Path) -> None:
    path = tmp_path / "pronunciation.json"
    path.write_text(
        json.dumps([
            {"match": "NASA", "replacement": "en ay es ay",
             "kind": "exact_word", "priority": 100,
             "case_sensitive": None},
        ]),
        encoding="utf-8",
    )
    d = PronunciationDictionary(path).load()
    assert len(d.list_rules()) == 1
    assert d.list_rules()[0].match == "NASA"


# ---------------------------------------------------------------------------
# Import / export
# ---------------------------------------------------------------------------


def test_export_import_round_trip(tmp_path: Path) -> None:
    src = PronunciationDictionary(tmp_path / "src.json").load()
    src.add_rule(PronunciationRule(match="NASA", replacement="en ay es ay"))
    src.add_rule(PronunciationRule(match="USB", replacement="you ess bee"))
    exported = tmp_path / "export.json"
    src.export_to_file(exported)

    dst = PronunciationDictionary(tmp_path / "dst.json").load()
    n = dst.import_from_file(exported, replace=True)
    assert n == 2
    assert dst.list_rules() == src.list_rules()


def test_import_append_keeps_existing(tmp_path: Path) -> None:
    src = PronunciationDictionary(tmp_path / "src.json").load()
    src.add_rule(PronunciationRule(match="NASA", replacement="en ay es ay"))
    exported = tmp_path / "export.json"
    src.export_to_file(exported)

    dst = PronunciationDictionary(tmp_path / "dst.json").load()
    dst.add_rule(PronunciationRule(match="USB", replacement="you ess bee"))
    dst.import_from_file(exported, replace=False)
    matches = [r.match for r in dst.list_rules()]
    assert matches == ["USB", "NASA"]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_audit_records_each_rule_that_fired(empty_dict: PronunciationDictionary) -> None:
    empty_dict.add_rule(PronunciationRule(
        match="NASA", replacement="en ay es ay", kind="exact_word",
    ))
    empty_dict.add_rule(PronunciationRule(
        match="USB", replacement="you ess bee", kind="exact_word",
    ))
    result = empty_dict.apply("NASA shipped a USB. Then NASA shipped two more.")
    assert isinstance(result, ApplyResult)
    matches = {(e.rule.match, e.occurrences) for e in result.audit}
    assert ("NASA", 2) in matches
    assert ("USB", 1) in matches


def test_audit_empty_when_no_rule_fires(empty_dict: PronunciationDictionary) -> None:
    empty_dict.add_rule(PronunciationRule(
        match="NASA", replacement="en ay es ay", kind="exact_word",
    ))
    assert empty_dict.apply("nothing to see here").audit == ()


# ---------------------------------------------------------------------------
# Synthesis-hook integration: playback.play_one must call apply()
# ---------------------------------------------------------------------------


def test_playback_play_one_applies_pronunciation_before_synthesis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins that the synthesis hook actually fires. We redirect the
    module-level singleton at a fresh tmp_path-backed dictionary that
    contains a single rewrite rule, then assert the fake engine
    receives the transformed text, not the original."""
    custom = PronunciationDictionary(tmp_path / "pronunciation.json").load()
    custom.add_rule(PronunciationRule(
        match="NASA", replacement="en ay es ay", kind="exact_word",
    ))
    monkeypatch.setattr(pronunciation, "_singleton", custom)

    engine = TTSEngine(MagicMock(), {"engine": "piper"}, overlay_ref=lambda: None)
    seen: list[str] = []

    def fake_synth(text: str, out_path: Path, backend: Any = None) -> bool:
        seen.append(text)
        out_path.write_bytes(b"x")
        return True

    monkeypatch.setattr(playback, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(playback, "wav_duration", lambda _p: 0.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_synthesize", fake_synth)

    engine.token = 1
    playback.play_one(engine, "NASA shipped it.", my_token=1, backend=object())

    # split_sentences may split, so collapse and check the rewrite happened.
    joined = " ".join(seen)
    assert "en ay es ay" in joined
    assert "NASA" not in joined


def test_playback_play_one_is_noop_with_empty_dictionary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = PronunciationDictionary(tmp_path / "pronunciation.json").load()
    monkeypatch.setattr(pronunciation, "_singleton", empty)

    engine = TTSEngine(MagicMock(), {"engine": "piper"}, overlay_ref=lambda: None)
    seen: list[str] = []

    def fake_synth(text: str, out_path: Path, backend: Any = None) -> bool:
        seen.append(text)
        out_path.write_bytes(b"x")
        return True

    monkeypatch.setattr(playback, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(playback, "wav_duration", lambda _p: 0.0)
    monkeypatch.setattr(playback.winsound, "PlaySound", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_synthesize", fake_synth)

    engine.token = 1
    playback.play_one(engine, "Hello world.", my_token=1, backend=object())

    assert " ".join(seen).strip() == "Hello world."


# ---------------------------------------------------------------------------
# DATA_ROOT location convention
# ---------------------------------------------------------------------------


def test_default_path_lives_under_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPPAL_DATA_DIR", str(tmp_path))
    # Re-import paths so DATA_ROOT picks up the override.
    import importlib

    from pippal import paths as paths_mod
    from pippal import pronunciation as p
    importlib.reload(paths_mod)
    importlib.reload(p)
    assert p._default_path() == tmp_path / "pronunciation.json"
