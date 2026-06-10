from pippal import notices


def test_resolve_notices_prefers_packaged_notices_file(tmp_path):
    notices_file = tmp_path / "NOTICES.txt"
    notices_file.write_text("bundled notices", encoding="utf-8")

    assert notices.resolve_notices_path([tmp_path]) == notices_file


def test_resolve_notices_falls_back_to_source_third_party_doc(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    third_party = docs / "THIRD_PARTY.md"
    third_party.write_text("source notices", encoding="utf-8")

    assert notices.resolve_notices_path([tmp_path]) == third_party


def test_resolve_notices_returns_none_when_missing(tmp_path):
    assert notices.resolve_notices_path([tmp_path]) is None
