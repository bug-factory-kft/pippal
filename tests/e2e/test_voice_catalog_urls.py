"""Voice catalogue URL liveness check.

The Voice Manager builds Hugging Face download URLs from
``KNOWN_VOICES`` entries. If Hugging Face renames a path, our
catalogue silently goes stale — the user clicks Install and gets a
404 mid-download. This test HEADs each URL and surfaces the breakage
immediately.

It only depends on outbound HTTPS, no piper.exe / voice-on-disk
needed, but we keep it under tests/e2e/ so it stays out of the fast
unit run by default."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

import pytest

from pippal.voices import KNOWN_VOICES, voice_filename, voice_url_base


def _voice_id(v) -> str:  # pytest test-id helper
    return v["id"]


@pytest.mark.e2e
@pytest.mark.parametrize("voice", KNOWN_VOICES, ids=_voice_id)
class TestVoiceCatalogURLs:

    def test_onnx_resolves(self, voice) -> None:
        """Each voice's main ``.onnx`` model URL must resolve. HEAD
        is enough — we only need the status code, not the bytes."""
        _head(voice_url_base(voice) + voice_filename(voice))

    def test_onnx_json_resolves(self, voice) -> None:
        """Sidecar metadata JSON must resolve too — Voice Manager
        downloads it next to the .onnx file."""
        _head(voice_url_base(voice) + voice_filename(voice) + ".json")


def _head(url: str) -> None:
    """HEAD ``url``; pass when the server returns 200 / 30x, fail with
    a short message on anything else (including unreachable host).

    Hugging Face redirects model-file URLs to a CDN, hence the
    ``allow_redirects=True`` semantics — urllib follows by default.

    Some catalogue paths contain non-ASCII characters (e.g. the
    Portuguese voice ``pt_PT-tug\xe3o-medium``), so percent-encode
    the path/query before handing it to ``http.client``, which
    refuses non-ASCII bytes on the request line.
    """
    parts = urllib.parse.urlsplit(url)
    safe_path = urllib.parse.quote(parts.path, safe="/")
    encoded = urllib.parse.urlunsplit(parts._replace(path=safe_path))
    req = urllib.request.Request(encoded, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            assert resp.status in (200, 301, 302, 303, 307, 308), (
                f"{url} → unexpected status {resp.status}"
            )
    except urllib.error.HTTPError as e:
        pytest.fail(f"{url} → HTTP {e.code}")
    except urllib.error.URLError as e:
        pytest.fail(f"{url} → {e.reason}")
