from __future__ import annotations

import json
from pathlib import Path

from pippal import config


class TestDefaultConfig:
    def test_has_required_keys(self):
        for key in (
            "engine", "voice", "kokoro_voice",
            "length_scale", "noise_scale",
            "hotkey_speak", "hotkey_stop",
            "ollama_endpoint", "ollama_model",
        ):
            assert key in config.DEFAULT_CONFIG, f"missing default for {key}"

    def test_engine_is_piper_by_default(self):
        assert config.DEFAULT_CONFIG["engine"] == "piper"

    def test_brand_name_is_pippal(self):
        assert config.DEFAULT_CONFIG["brand_name"] == "PipPal"


class TestLoadConfig:
    def test_returns_defaults_when_file_missing(self, tmp_path: Path):
        cfg = config.load_config(path=tmp_path / "nope.json")
        assert cfg == config.DEFAULT_CONFIG
        # Result is a fresh dict, not the same object.
        assert cfg is not config.DEFAULT_CONFIG

    def test_overlays_user_values_on_defaults(self, tmp_path: Path):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"voice": "custom.onnx"}), encoding="utf-8")
        cfg = config.load_config(path=p)
        assert cfg["voice"] == "custom.onnx"
        # Other keys still default
        assert cfg["engine"] == config.DEFAULT_CONFIG["engine"]

    def test_invalid_json_falls_back_to_defaults(self, tmp_path: Path):
        p = tmp_path / "config.json"
        p.write_text("{not valid", encoding="utf-8")
        cfg = config.load_config(path=p)
        assert cfg == config.DEFAULT_CONFIG

    def test_non_dict_payload_falls_back(self, tmp_path: Path):
        p = tmp_path / "config.json"
        p.write_text(json.dumps(["a", "b"]), encoding="utf-8")
        cfg = config.load_config(path=p)
        assert cfg == config.DEFAULT_CONFIG


class TestSaveConfig:
    def test_round_trip(self, tmp_path: Path):
        p = tmp_path / "config.json"
        cfg = dict(config.DEFAULT_CONFIG)
        cfg["voice"] = "new.onnx"
        config.save_config(cfg, path=p)
        loaded = config.load_config(path=p)
        assert loaded["voice"] == "new.onnx"

    def test_writes_unicode(self, tmp_path: Path):
        p = tmp_path / "config.json"
        cfg = dict(config.DEFAULT_CONFIG)
        cfg["brand_name"] = "Pípal árvíztűrő"
        config.save_config(cfg, path=p)
        loaded = config.load_config(path=p)
        assert loaded["brand_name"] == "Pípal árvíztűrő"

    def test_atomic_replace_failure_keeps_original(self, tmp_path: Path,
                                                    monkeypatch):
        # If os.replace raises after the temp write, the original file
        # must still be intact (atomicity invariant). Pre-create a known
        # config, monkey-patch os.replace to raise, attempt to save a
        # new one, and verify the old contents survive.
        import os as _os

        p = tmp_path / "config.json"
        config.save_config({**config.DEFAULT_CONFIG, "voice": "v1.onnx"}, path=p)

        def boom(*_a, **_kw):
            raise OSError("disk full")

        monkeypatch.setattr(_os, "replace", boom)
        try:
            config.save_config({**config.DEFAULT_CONFIG, "voice": "v2.onnx"},
                                path=p)
        except OSError:
            pass  # fine — atomic write surfaces the error
        loaded = config.load_config(path=p)
        assert loaded["voice"] == "v1.onnx"

    def test_mood_id_survives_round_trip(self, tmp_path: Path):
        # Regression for the missing-DEFAULT_CONFIG-key bug: mood_id
        # was being filtered out by load_config because it wasn't in
        # DEFAULT_CONFIG. Adding it as a default key fixes that.
        p = tmp_path / "config.json"
        cfg = dict(config.DEFAULT_CONFIG)
        cfg["mood_id"] = "warm"
        config.save_config(cfg, path=p)
        loaded = config.load_config(path=p)
        assert loaded["mood_id"] == "warm"


class TestLayeredSave:
    """Stage 1.G: save_config writes only the keys whose value differs
    from the current layered defaults. Defaults that round-trip
    unchanged stay out of config.json so the file stays small and a
    plugin uninstall doesn't strand its defaults on disk."""

    def test_unchanged_default_is_not_persisted(self, tmp_path: Path):
        p = tmp_path / "config.json"
        cfg = dict(config.DEFAULT_CONFIG)  # identical to defaults
        config.save_config(cfg, path=p)
        # File contains an empty object — no overrides to record.
        assert json.loads(p.read_text("utf-8")) == {}
        # But load still returns the full effective config.
        loaded = config.load_config(path=p)
        assert loaded["engine"] == config.DEFAULT_CONFIG["engine"]

    def test_only_modified_keys_are_persisted(self, tmp_path: Path):
        p = tmp_path / "config.json"
        cfg = dict(config.DEFAULT_CONFIG)
        cfg["voice"] = "custom.onnx"
        cfg["mood_id"] = "warm"
        config.save_config(cfg, path=p)
        on_disk = json.loads(p.read_text("utf-8"))
        assert on_disk == {"voice": "custom.onnx", "mood_id": "warm"}

    def test_unknown_keys_preserved_through_save(self, tmp_path: Path):
        # If a Pro plugin once wrote a key we don't recognise (because
        # Pro is currently uninstalled), save_config must keep it so a
        # later Pro reinstall finds the value still there. Without
        # this protection, a Free Settings save would silently delete
        # Pro state.
        p = tmp_path / "config.json"
        cfg = dict(config.DEFAULT_CONFIG)
        cfg["custom_pro_key"] = "user-set value"
        config.save_config(cfg, path=p)
        on_disk = json.loads(p.read_text("utf-8"))
        assert on_disk["custom_pro_key"] == "user-set value"
