from __future__ import annotations

from pathlib import Path

import pytest

from pippal.ui import theme, voice_manager
from pippal.voices import KNOWN_VOICES, voice_filename, voice_url_base


class _Response:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def read(self, _size: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""


def _portuguese_voice():
    return next(v for v in KNOWN_VOICES if v["id"] == "pt_PT-tugão-medium")


def test_dialog_origin_waits_for_parent_geometry_before_positioning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        theme,
        "dialog_screen_bounds",
        lambda _dialog: (0, 0, 3440, 1440),
    )

    class Parent:
        updated = False

        def update_idletasks(self) -> None:
            self.updated = True

        def winfo_rootx(self) -> int:
            return 1420 if self.updated else 0

        def winfo_rooty(self) -> int:
            return 370 if self.updated else 0

        def winfo_width(self) -> int:
            return 560

        def winfo_height(self) -> int:
            return 600

    class Dialog:
        def winfo_screenwidth(self) -> int:
            return 3440

        def winfo_screenheight(self) -> int:
            return 1440

    parent = Parent()
    dialog = Dialog()

    x, y = theme.dialog_origin_near_parent(parent, dialog, 680, 600)

    assert parent.updated is True
    assert (x, y) == (1420, 370)


def test_dialog_origin_uses_geometry_when_root_coords_are_temporarily_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        theme,
        "dialog_screen_bounds",
        lambda _dialog: (0, 0, 3440, 1440),
    )

    class Parent:
        def update_idletasks(self) -> None:
            return None

        def geometry(self) -> str:
            return "600x700+1420+370"

        def winfo_rootx(self) -> int:
            return 0

        def winfo_rooty(self) -> int:
            return 0

        def winfo_width(self) -> int:
            return 1

        def winfo_height(self) -> int:
            return 1

    class Dialog:
        def winfo_screenwidth(self) -> int:
            return 3440

        def winfo_screenheight(self) -> int:
            return 1440

    x, y = theme.dialog_origin_near_parent(Parent(), Dialog(), 680, 600)

    assert (x, y) == (1420, 420)


def test_dialog_origin_uses_virtual_screen_bounds_when_tk_reports_tiny_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        theme,
        "dialog_screen_bounds",
        lambda _dialog: (0, 0, 3440, 1440),
    )

    class Parent:
        def update_idletasks(self) -> None:
            return None

        def geometry(self) -> str:
            return "560x600+1420+370"

        def winfo_rootx(self) -> int:
            return 1420

        def winfo_rooty(self) -> int:
            return 370

        def winfo_width(self) -> int:
            return 560

        def winfo_height(self) -> int:
            return 600

    class Dialog:
        def winfo_screenwidth(self) -> int:
            return 680

        def winfo_screenheight(self) -> int:
            return 600

    x, y = theme.dialog_origin_near_parent(Parent(), Dialog(), 680, 600)

    assert (x, y) == (1420, 370)


def test_encode_download_url_percent_encodes_non_ascii_path() -> None:
    voice = _portuguese_voice()
    raw_url = voice_url_base(voice) + voice_filename(voice)

    encoded = voice_manager._encode_download_url(raw_url)

    encoded.encode("ascii")
    assert "tug%C3%A3o" in encoded
    assert "tugão" not in encoded


def test_streaming_download_passes_encoded_url_to_urlopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    voice = _portuguese_voice()
    raw_url = voice_url_base(voice) + voice_filename(voice)
    seen: dict[str, str] = {}

    def fake_urlopen(url: str, timeout: float):
        seen["url"] = url
        seen["timeout"] = str(timeout)
        return _Response([b"voice-bytes"])

    monkeypatch.setattr(voice_manager.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "voice.onnx"

    voice_manager.VoiceManagerDialog._streaming_download(raw_url, dest)

    assert "tug%C3%A3o" in seen["url"]
    assert "tugão" not in seen["url"]
    assert dest.read_bytes() == b"voice-bytes"


def test_install_piper_voice_downloads_model_and_metadata(tmp_path: Path) -> None:
    voice = _portuguese_voice()
    filename = voice_filename(voice)
    calls: list[str] = []

    def fake_download(url: str, dest: Path) -> None:
        calls.append(url)
        dest.write_bytes(f"downloaded:{dest.name}".encode())

    installed = voice_manager.install_piper_voice(
        voice,
        voices_dir=tmp_path,
        streaming_download=fake_download,
    )

    assert installed == filename
    assert calls == [
        voice_url_base(voice) + filename,
        voice_url_base(voice) + f"{filename}.json",
    ]
    assert (tmp_path / filename).read_bytes() == f"downloaded:{filename}.part".encode()
    assert (tmp_path / f"{filename}.json").read_bytes() == (
        f"downloaded:{filename}.json.part".encode()
    )
    assert list(tmp_path.glob("*.part")) == []


def test_install_piper_voice_removes_partial_files_on_failure(tmp_path: Path) -> None:
    voice = _portuguese_voice()
    filename = voice_filename(voice)

    def fake_download(url: str, dest: Path) -> None:
        dest.write_bytes(b"partial")
        if url.endswith(".json"):
            raise RuntimeError("network dropped")

    with pytest.raises(RuntimeError, match="network dropped"):
        voice_manager.install_piper_voice(
            voice,
            voices_dir=tmp_path,
            streaming_download=fake_download,
        )

    assert (tmp_path / filename).exists() is False
    assert (tmp_path / f"{filename}.json").exists() is False
    assert list(tmp_path.glob("*.part")) == []


def test_voice_manager_wheel_binding_reaches_row_descendants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWidget:
        def __init__(self, *children: object) -> None:
            self.children = list(children)
            self.bound: list[tuple[str, object]] = []

        def winfo_children(self) -> list[object]:
            return self.children

        def bind(self, event: str, handler: object) -> None:
            self.bound.append((event, handler))

    class FakeButton(FakeWidget):
        pass

    class FakeCombobox(FakeWidget):
        pass

    class FakeEntry(FakeWidget):
        pass

    monkeypatch.setattr(voice_manager.ttk, "Button", FakeButton)
    monkeypatch.setattr(voice_manager.ttk, "Combobox", FakeCombobox)
    monkeypatch.setattr(voice_manager.ttk, "Entry", FakeEntry)

    label = FakeWidget()
    button = FakeButton()
    entry = FakeEntry()
    card = FakeWidget(label, button, entry)
    root = FakeWidget(card)

    dialog = object.__new__(voice_manager.VoiceManagerDialog)
    handler = object()
    dialog._wheel_handler = handler

    dialog._bind_wheel_recursive(root)

    assert root.bound == []
    assert card.bound == [("<MouseWheel>", handler)]
    assert label.bound == [("<MouseWheel>", handler)]
    assert button.bound == []
    assert entry.bound == []
