from pathlib import Path

from pippal.ui import notices_card


def test_resolve_notices_prefers_packaged_notices_file(tmp_path):
    notices = tmp_path / "NOTICES.txt"
    notices.write_text("bundled notices", encoding="utf-8")

    assert notices_card._resolve_notices_path([tmp_path]) == notices


def test_resolve_notices_falls_back_to_source_third_party_doc(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    third_party = docs / "THIRD_PARTY.md"
    third_party.write_text("source notices", encoding="utf-8")

    assert notices_card._resolve_notices_path([tmp_path]) == third_party


def test_resolve_notices_returns_none_when_missing(tmp_path):
    assert notices_card._resolve_notices_path([tmp_path]) is None


def test_notices_viewer_text_options_use_existing_theme_keys():
    options = notices_card._notices_text_options()

    assert options["bg"] == notices_card.UI["bg_card"]
    assert options["fg"] == notices_card.UI["text"]


def test_public_notices_card_uses_generic_core_wording():
    source = Path(notices_card.__file__).read_text(encoding="utf-8")

    assert "PipPal uses open-source libraries" in source
    assert "Open-source notices were not found" in source
