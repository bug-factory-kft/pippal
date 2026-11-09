"""CI jobs install Python packages into a fresh per-job venv.

The self-hosted runner reuses one tool-cache interpreter for every job.
A ``pip install --upgrade`` into it leaks into every later job (the
install-surface smoke job's ``--upgrade pytest`` pulled in pytest 9.2 and
broke the Benchmarks job on main, 2026-11-09). Each job therefore runs
``python -m venv --clear .venv-ci-<job>`` from the setup-python
interpreter and calls only that venv's python afterwards.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# A bare interpreter or Python tool in command position (line start,
# after `run:` or `xvfb-run -a`), i.e. the setup-python tool-cache one.
_BARE_CALL = re.compile(
    r"^(?:-\s+)?(?:run:\s*['\"]?)?(?:xvfb-run(?:\s+-\S+)*\s+)?"
    r"(?:python3?|pip3?|pytest|ruff|pyinstaller)(?:\.exe)?(?=\s|$)"
)
_VENV_CREATE = re.compile(r"^python -m venv --clear \.venv-ci-[\w-]+$")


def _code_lines(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        (number, line.strip())
        for number, line in enumerate(lines, 1)
        if line.strip() and not line.strip().startswith("#")
    ]


def test_workflows_found() -> None:
    assert WORKFLOWS, "no workflow files found"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_no_bare_tool_cache_python_calls(workflow: Path) -> None:
    offenders = [
        f"{workflow.name}:{number}: {line}"
        for number, line in _code_lines(workflow)
        if _BARE_CALL.match(line) and not _VENV_CREATE.match(line)
    ]
    assert not offenders, "call the job venv's python instead:\n" + "\n".join(offenders)


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_setup_python_job_creates_its_own_venv(workflow: Path) -> None:
    lines = [line for _, line in _code_lines(workflow)]
    setups = sum("uses: actions/setup-python@" in line for line in lines)
    venvs = [line for line in lines if _VENV_CREATE.match(line)]
    assert len(venvs) == setups
    assert len(set(venvs)) == len(venvs), "venv names must be unique per job"
    # The managed setup-python cache would be a GitHub Actions cache.
    assert not any(line.startswith("cache:") for line in lines)
