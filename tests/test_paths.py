from pathlib import Path

from pippal import paths


def test_source_checkout_root_detects_src_layout(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    package_root = checkout / "src" / "pippal"
    package_root.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    assert paths._source_checkout_root(package_root) == checkout


def test_source_checkout_root_returns_none_for_package_layout(tmp_path: Path) -> None:
    package_root = tmp_path / "site-packages" / "pippal"
    package_root.mkdir(parents=True)

    assert paths._source_checkout_root(package_root) is None


def test_static_assets_resolve_in_current_layout() -> None:
    assert paths.ASSET_ICON_PATH.exists()
    assert paths.ASSET_NO_VOICE_WAV.exists()


def test_package_data_declares_static_assets() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'pippal = ["assets/*", "assets/onboarding/*"]' in pyproject
