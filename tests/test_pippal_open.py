import os
import subprocess
import sys
from pathlib import Path


def test_source_helper_imports_package_under_isolated_python() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "pippal_open.py"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "ModuleNotFoundError" not in result.stderr


def test_package_script_entry_points_at_packaged_module() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'pippal-open = "pippal.open_file:main"' in pyproject


def test_packaged_module_runs_helper_main() -> None:
    env = os.environ.copy()
    src_path = str(Path("src").resolve())
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (src_path, env.get("PYTHONPATH", "")) if part
    )
    result = subprocess.run(
        [sys.executable, "-m", "pippal.open_file"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert "ModuleNotFoundError" not in result.stderr
