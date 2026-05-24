"""Curated Piper voice installation (download + atomic place).

Pure, UI-agnostic logic shared by the app's onboarding / voice flows.
No Tk, no pywebview — just urllib + the filesystem so any front-end can
install a voice the same way.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .paths import VOICES_DIR
from .timing import DOWNLOAD_TIMEOUT_S
from .voices import (
    PiperVoice,
    voice_filename,
    voice_url_base,
)


def _encode_download_url(url: str) -> str:
    """Percent-encode the request path for urllib/http.client.

    Hugging Face voice paths can contain non-ASCII speaker names. The
    catalogue keeps them readable, but the HTTP request line must be
    ASCII or urllib can raise before making the request.
    """
    parts = urllib.parse.urlsplit(url)
    safe_path = urllib.parse.quote(parts.path, safe="/")
    return urllib.parse.urlunsplit(parts._replace(path=safe_path))


def _streaming_download(
    url: str,
    dest: Path,
    timeout: float = DOWNLOAD_TIMEOUT_S,
    chunk: int = 1 << 16,
) -> None:
    """Download ``url`` to ``dest`` and fail if the response is empty."""
    encoded_url = _encode_download_url(url)
    with urllib.request.urlopen(encoded_url, timeout=timeout) as resp, dest.open("wb") as f:
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            f.write(buf)
    if dest.stat().st_size == 0:
        raise RuntimeError("empty response")


def install_piper_voice(
    v: PiperVoice,
    *,
    voices_dir: Path = VOICES_DIR,
    streaming_download: Callable[[str, Path], None] | None = None,
) -> str:
    """Install a curated Piper voice and return the installed model filename."""
    download = streaming_download or _streaming_download
    voices_dir.mkdir(parents=True, exist_ok=True)

    filename = voice_filename(v)
    onnx = voices_dir / filename
    meta = voices_dir / f"{filename}.json"
    part_onnx = onnx.with_suffix(onnx.suffix + ".part")
    part_meta = meta.with_suffix(meta.suffix + ".part")
    base = voice_url_base(v)

    try:
        download(base + filename, part_onnx)
        download(base + f"{filename}.json", part_meta)
        os.replace(str(part_onnx), str(onnx))
        os.replace(str(part_meta), str(meta))
    except Exception:
        for partial in (part_onnx, part_meta):
            try:
                if partial.exists():
                    partial.unlink(missing_ok=True)
            except Exception:
                pass
        raise
    return filename
