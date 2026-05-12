from __future__ import annotations

import os
import platform
from pathlib import Path

import pytest
from pippal_e2e import (
    assert_port_free,
    launch_public_app,
    terminate_process_tree,
    wait_for_port_or_process_exit,
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live_ui: launches and drives the real Windows UI")
    config.addinivalue_line("markers", "public: public source app E2E coverage")


@pytest.fixture(scope="session", autouse=True)
def require_live_windows() -> None:
    if platform.system() != "Windows":
        pytest.skip("PipPal live UI E2E tests require Windows")
    if os.environ.get("PIPPAL_E2E_LIVE") != "1":
        pytest.skip("set PIPPAL_E2E_LIVE=1 or run e2e/run-local.ps1")


@pytest.fixture(scope="session")
def public_root() -> Path:
    raw = os.environ.get("PIPPAL_E2E_PUBLIC_ROOT")
    if not raw:
        pytest.skip("PIPPAL_E2E_PUBLIC_ROOT is required")
    root = Path(raw).resolve()
    if not (root / "reader_app.py").is_file():
        pytest.fail(f"public checkout is missing reader_app.py: {root}")
    return root


@pytest.fixture(scope="session")
def data_root() -> Path:
    raw = os.environ.get("PIPPAL_E2E_DATA_ROOT")
    if not raw:
        pytest.skip("PIPPAL_E2E_DATA_ROOT is required")
    root = Path(raw).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def running_public_app(public_root: Path, data_root: Path):
    assert_port_free()
    process = launch_public_app(public_root, data_root)
    try:
        wait_for_port_or_process_exit(process)
        yield process
    finally:
        terminate_process_tree(process)
