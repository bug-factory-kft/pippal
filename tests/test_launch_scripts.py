from pathlib import Path

ABSOLUTE_USER_PATH_MARKERS = (
    ":\\Users\\",
    "\\piper-reader",
    "Python314",
)


def _script_text(name: str) -> str:
    return Path(name).read_text(encoding="utf-8")


def test_start_console_uses_script_directory_and_path_python() -> None:
    script = _script_text("start_console.bat")

    assert "%~dp0" in script
    assert "python reader_app.py" in script
    for marker in ABSOLUTE_USER_PATH_MARKERS:
        assert marker not in script


def test_start_server_vbs_uses_its_own_directory() -> None:
    script = _script_text("start_server.vbs")

    assert "WScript.ScriptFullName" in script
    assert 'fso.BuildPath(scriptDir, "reader_app.py")' in script
    assert "pythonw.exe" in script
    for marker in ABSOLUTE_USER_PATH_MARKERS:
        assert marker not in script


def test_readme_autostart_uses_shortcut_not_copied_vbs() -> None:
    readme = _script_text("README.md")

    assert "PipPal.lnk" in readme
    assert "CreateShortcut" in readme
    assert "copy start_server.vbs" not in readme


def test_live_ui_e2e_runner_captures_release_evidence() -> None:
    script = _script_text("e2e/run-local.ps1")

    assert "[string] $EvidenceDir" in script
    assert "[switch] $AllowUnavailable" in script
    assert "pytest-live-ui.log" in script
    assert "pytest-live-ui.junit.xml" in script
    assert "release-gate-summary.json" in script
    assert "release-gate-command.txt" in script
    assert "--junitxml" in script
    assert "PIPPAL_E2E_LIVE" in script
    assert "PIPPAL_E2E_PUBLIC_ROOT" in script
    assert "PIPPAL_E2E_DATA_ROOT" in script
    assert "PIPPAL_E2E_COMMAND_SERVER=1" in script
    assert "tests -eq 0 -or $counts.skipped -gt 0" in script
    assert "'blocked'" in script


def test_live_ui_e2e_release_gate_docs_name_command_and_artifacts() -> None:
    docs = _script_text("docs/LIVE_UI_E2E_RELEASE_GATE.md")
    e2e_readme = _script_text("e2e/README.md")
    root_readme = _script_text("README.md")

    assert ".\\e2e\\run-local.ps1 -SkipSetup" in docs
    assert "-EvidenceDir" in docs
    assert "release-gate-summary.json" in docs
    assert "pytest-live-ui.log" in docs
    assert "pytest-live-ui.junit.xml" in docs
    assert "release-gate-command.txt" in docs
    assert '"status": "pass"' in docs
    assert "skipped = 0" in docs
    assert "PIPPAL_E2E_COMMAND_SERVER=1" in docs
    assert "docs/LIVE_UI_E2E_RELEASE_GATE.md" in e2e_readme
    assert "docs/LIVE_UI_E2E_RELEASE_GATE.md" in root_readme
