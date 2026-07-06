"""Minimal local Ollama HTTP client for model generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request


class OllamaClientError(RuntimeError):
    """Raised when Ollama API communication or payload parsing fails."""


@dataclass(slots=True)
class OllamaClient:
    """HTTP client for local Ollama model generation."""

    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: int = 60

    def _normalized_base_url(self) -> str:
        cleaned = self.base_url.strip().rstrip("/")
        if not cleaned:
            raise OllamaClientError("Ollama base URL is empty")
        return cleaned

    def generate(self, *, model: str, prompt: str) -> str:
        """Generate a response from a local Ollama model."""
        base_url = self._normalized_base_url()
        body = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8")
        req = request.Request(
            f"{base_url}/api/generate",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            msg = detail.strip() or str(exc.reason)
            raise OllamaClientError(f"Ollama HTTP {exc.code}: {msg}") from exc
        except error.URLError as exc:
            raise OllamaClientError(f"Could not reach Ollama: {exc.reason}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaClientError("Ollama returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise OllamaClientError("Ollama JSON payload is not an object")

        text = payload.get("response")
        if not isinstance(text, str):
            raise OllamaClientError("Ollama response missing string field: response")

        return text.strip()
