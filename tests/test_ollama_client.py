from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import patch

from pippal.ollama_client import (
    AI_NUM_PREDICT,
    PROMPT_DEFINE,
    PROMPT_EXPLAIN,
    PROMPT_SUMMARY,
    OllamaClient,
    build_translate_prompt,
)


class _FakeResponse:
    """Minimal context-manager-compatible stand-in for urllib's HTTPResponse."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._buf = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._buf.read()


class TestOllamaClientChat:
    def test_chat_returns_message_content(self):
        client = OllamaClient("http://localhost:11434")
        with patch(
            "pippal.ollama_client.urllib.request.urlopen",
            return_value=_FakeResponse({"message": {"content": "hello world"}}),
        ):
            assert client.chat("dummy", "sys", "user") == "hello world"

    def test_chat_strips_whitespace(self):
        client = OllamaClient("http://localhost:11434")
        with patch(
            "pippal.ollama_client.urllib.request.urlopen",
            return_value=_FakeResponse({"message": {"content": "  trimmed  "}}),
        ):
            assert client.chat("dummy", "sys", "user") == "trimmed"

    def test_chat_handles_missing_message(self):
        client = OllamaClient("http://localhost:11434")
        with patch(
            "pippal.ollama_client.urllib.request.urlopen",
            return_value=_FakeResponse({}),
        ):
            assert client.chat("dummy", "sys", "user") == ""

    def test_chat_sends_expected_body(self):
        client = OllamaClient("http://localhost:11434")
        captured: dict[str, Any] = {}

        def _capture(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("pippal.ollama_client.urllib.request.urlopen", side_effect=_capture):
            client.chat("my-model", "system text", "user text", num_predict=99)

        assert captured["url"].endswith("/api/chat")
        assert captured["body"]["model"] == "my-model"
        assert captured["body"]["stream"] is False
        assert captured["body"]["messages"][0]["role"] == "system"
        assert captured["body"]["messages"][0]["content"] == "system text"
        assert captured["body"]["messages"][1]["content"] == "user text"
        assert captured["body"]["options"]["num_predict"] == 99


class TestOllamaClientListModels:
    def test_returns_model_names(self):
        client = OllamaClient()
        with patch(
            "pippal.ollama_client.urllib.request.urlopen",
            return_value=_FakeResponse({"models": [{"name": "a"}, {"name": "b"}]}),
        ):
            assert client.list_models() == ["a", "b"]

    def test_returns_empty_on_failure(self):
        client = OllamaClient()
        with patch(
            "pippal.ollama_client.urllib.request.urlopen",
            side_effect=ConnectionError("nope"),
        ):
            assert client.list_models() == []

    def test_skips_models_without_name(self):
        client = OllamaClient()
        with patch(
            "pippal.ollama_client.urllib.request.urlopen",
            return_value=_FakeResponse({"models": [{"name": "ok"}, {}]}),
        ):
            assert client.list_models() == ["ok"]


class TestEndpointNormalisation:
    def test_strips_trailing_slash(self):
        c = OllamaClient("http://localhost:11434/")
        assert c.endpoint == "http://localhost:11434"

    def test_falls_back_to_default(self):
        c = OllamaClient("")
        assert c.endpoint == "http://localhost:11434"


class TestPromptBuilders:
    def test_translate_includes_target(self):
        p = build_translate_prompt("Hungarian")
        assert "Hungarian" in p
        assert "translation" in p.lower()

    def test_static_prompts_present(self):
        assert PROMPT_SUMMARY and PROMPT_EXPLAIN and PROMPT_DEFINE

    def test_num_predict_keys_match_actions(self):
        assert set(AI_NUM_PREDICT) >= {"summary", "explain", "translate", "define"}
