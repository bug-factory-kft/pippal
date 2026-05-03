from __future__ import annotations

import json
from pathlib import Path

from pippal import history


class TestAddHistory:
    def test_prepends_new_text(self):
        h = history.add_history(["b", "c"], "a")
        assert h == ["a", "b", "c"]

    def test_dedupes(self):
        h = history.add_history(["b", "a", "c"], "a")
        assert h == ["a", "b", "c"]

    def test_caps_at_max(self):
        items = [f"t{i}" for i in range(20)]
        h = history.add_history(items, "new")
        assert len(h) == history.MAX_HISTORY
        assert h[0] == "new"

    def test_empty_text_is_noop(self):
        h = history.add_history(["a", "b"], "")
        assert h == ["a", "b"]

    def test_whitespace_only_is_noop(self):
        h = history.add_history(["a"], "   ")
        assert h == ["a"]

    def test_does_not_mutate_input(self):
        original = ["a", "b"]
        history.add_history(original, "c")
        assert original == ["a", "b"]


class TestLoadSaveRoundTrip:
    def test_save_then_load(self, tmp_path: Path):
        p = tmp_path / "history.json"
        history.save_history(["one", "two", "three"], path=p)
        assert history.load_history(path=p) == ["one", "two", "three"]

    def test_load_missing_file(self, tmp_path: Path):
        assert history.load_history(path=tmp_path / "nope.json") == []

    def test_load_invalid_json(self, tmp_path: Path):
        p = tmp_path / "history.json"
        p.write_text("{not valid json", encoding="utf-8")
        assert history.load_history(path=p) == []

    def test_load_wrong_shape_returns_empty(self, tmp_path: Path):
        p = tmp_path / "history.json"
        p.write_text(json.dumps({"oops": "object"}), encoding="utf-8")
        assert history.load_history(path=p) == []

    def test_load_caps_to_max(self, tmp_path: Path):
        p = tmp_path / "history.json"
        items = [f"t{i}" for i in range(50)]
        p.write_text(json.dumps(items), encoding="utf-8")
        loaded = history.load_history(path=p)
        assert len(loaded) == history.MAX_HISTORY

    def test_save_caps_to_max(self, tmp_path: Path):
        p = tmp_path / "history.json"
        history.save_history([f"t{i}" for i in range(50)], path=p)
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == history.MAX_HISTORY

    def test_save_handles_unicode(self, tmp_path: Path):
        p = tmp_path / "history.json"
        history.save_history(["árvíztűrő tükörfúrógép"], path=p)
        loaded = history.load_history(path=p)
        assert loaded == ["árvíztűrő tükörfúrógép"]
