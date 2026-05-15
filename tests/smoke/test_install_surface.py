from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
import venv
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _copy_build_source(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    source_root.mkdir()
    for filename in ("pyproject.toml", "README.md", "LICENSE.md"):
        shutil.copy2(ROOT / filename, source_root / filename)
    shutil.copytree(
        ROOT / "src",
        source_root / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    return source_root


def test_setup_and_launcher_contracts_are_shippable() -> None:
    setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")
    console = (ROOT / "start_console.bat").read_text(encoding="utf-8")
    server = (ROOT / "start_server.vbs").read_text(encoding="utf-8")

    assert "PIPPAL_DATA_DIR" in setup
    assert "$voicesDir = Join-Path $dataRoot 'voices'" in setup
    assert "pythonw reader_app.py" in setup
    assert "copy start_server.vbs" not in setup
    assert "Startup shortcut to start_server.vbs" in setup

    assert "%~dp0" in console
    assert "python reader_app.py" in console

    assert "WScript.ScriptFullName" in server
    assert 'fso.BuildPath(scriptDir, "reader_app.py")' in server
    assert "pythonw.exe" in server


def test_setup_script_is_valid_powershell() -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is required for the setup script smoke")

    _run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            "$null = [scriptblock]::Create((Get-Content -Raw setup.ps1))",
        ]
    )


def test_source_explorer_helper_runs_without_editable_install() -> None:
    result = _run([sys.executable, "-I", "pippal_open.py"], check=False)

    assert result.returncode == 1
    assert "ModuleNotFoundError" not in result.stderr


def test_non_editable_wheel_exposes_runtime_assets_and_helper(tmp_path: Path) -> None:
    source_root = _copy_build_source(tmp_path)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    _run(
        [sys.executable, "-m", "pip", "wheel", str(source_root), "--no-deps", "-w", str(wheelhouse)],
        cwd=tmp_path,
    )

    wheels = list(wheelhouse.glob("pippal-*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]

    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        entry_points = next(
            zf.read(name).decode("utf-8")
            for name in names
            if name.endswith(".dist-info/entry_points.txt")
        )

    assert "pippal/assets/pippal_icon.png" in names
    assert "pippal/assets/onboarding/pippal-no-installed-language.wav" in names
    assert "pippal/open_file.py" in names
    assert "pippal-open = pippal.open_file:main" in entry_points

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    venv_python = _venv_python(venv_dir)
    _run([str(venv_python), "-m", "pip", "install", str(wheel)])

    check = textwrap.dedent(
        """
        from pippal import paths

        assert paths.INSTALL_ROOT == paths.PACKAGE_ROOT
        assert paths.ASSET_ICON_PATH.is_file(), paths.ASSET_ICON_PATH
        assert paths.ASSET_NO_VOICE_WAV.is_file(), paths.ASSET_NO_VOICE_WAV
        """
    )
    _run([str(venv_python), "-c", check])

    helper = _run([str(venv_python), "-m", "pippal.open_file"], check=False)
    assert helper.returncode == 1
    assert "ModuleNotFoundError" not in helper.stderr
