from pathlib import Path


def test_setup_installs_default_voice_under_runtime_data_root() -> None:
    script = Path("setup.ps1").read_text(encoding="utf-8")

    assert "PIPPAL_DATA_DIR" in script
    assert "LOCALAPPDATA" in script
    assert "$dataRoot = Resolve-PipPalDataRoot" in script
    assert "$voicesDir = Join-Path $dataRoot 'voices'" in script
    assert "$voicesDir = Join-Path $root 'voices'" not in script
