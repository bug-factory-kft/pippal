"""Tiny stdlib-only client for the local Ollama HTTP API."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from .timing import OLLAMA_CHAT_TIMEOUT_S, OLLAMA_LIST_TIMEOUT_S

PROMPT_SUMMARY = (
    "You are a concise summarizer. Summarize the user's text in one or two short "
    "sentences. Output ONLY the summary itself — no preface, no quotation marks, "
    "no formatting marks, no commentary."
)

PROMPT_EXPLAIN = (
    "You explain text in simple, plain language so anyone can understand. "
    "Output ONLY a short, clear explanation (2 to 4 sentences). No preface, "
    "no markdown, no quotation marks, no commentary."
)

PROMPT_DEFINE = (
    "You are a clear dictionary. Provide a brief definition (1 to 2 sentences) "
    "of the user's term, then one short usage example. Output plain prose only — "
    "no markdown, no headers, no bullet points."
)

# Per-action token caps (~75 tokens ≈ 1 sentence of TTS).
AI_NUM_PREDICT: dict[str, int] = {
    "summary":   140,
    "explain":   380,
    "translate": 700,
    "define":    180,
}


def build_translate_prompt(target_language: str) -> str:
    return (
        f"Translate the user's text into {target_language}. Preserve meaning and tone. "
        "Output ONLY the translation — no preface, no quotation marks, no commentary."
    )


class OllamaClient:
    """Talks to a locally-running Ollama daemon via /api/tags and /api/chat."""

    def __init__(self, endpoint: str = "http://localhost:11434") -> None:
        self.endpoint: str = (endpoint or "http://localhost:11434").rstrip("/")

    def is_available(self, timeout: float = 1.0) -> bool:
        """Quick liveness probe — does the daemon answer at all?
        Used to distinguish 'Ollama is not running' from 'Ollama is
        running but has no models pulled', which need different UX."""
        try:
            with urllib.request.urlopen(
                f"{self.endpoint}/api/tags", timeout=timeout,
            ) as _:
                return True
        except Exception:
            return False

    def list_models(self, timeout: float = OLLAMA_LIST_TIMEOUT_S) -> list[str]:
        try:
            with urllib.request.urlopen(
                f"{self.endpoint}/api/tags", timeout=timeout
            ) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"[ollama] list_models: {e}", file=sys.stderr)
            return []
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def chat(
        self,
        model: str,
        system: str,
        user: str,
        timeout: float = OLLAMA_CHAT_TIMEOUT_S,
        num_predict: int = 400,
        temperature: float = 0.3,
    ) -> str:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "num_predict": int(num_predict),
                "temperature": float(temperature),
            },
        }
        req = urllib.request.Request(
            f"{self.endpoint}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return ((data.get("message") or {}).get("content") or "").strip()
