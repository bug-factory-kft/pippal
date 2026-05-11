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
