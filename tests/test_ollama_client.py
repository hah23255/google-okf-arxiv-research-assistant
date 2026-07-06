from __future__ import annotations

from urllib import error

import pytest

from google_okf_arxiv_assistant.ollama_client import OllamaClient, OllamaClientError


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_generate_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse('{"response":"hello from model"}')

    from google_okf_arxiv_assistant import ollama_client as module

    monkeypatch.setattr(module.request, "urlopen", fake_urlopen)
    client = OllamaClient(base_url="http://127.0.0.1:11434", timeout_seconds=10)
    out = client.generate(model="granite4.1:3b", prompt="test prompt")
    assert out == "hello from model"


def test_generate_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse("not-json")

    from google_okf_arxiv_assistant import ollama_client as module

    monkeypatch.setattr(module.request, "urlopen", fake_urlopen)
    client = OllamaClient(base_url="http://127.0.0.1:11434", timeout_seconds=10)
    with pytest.raises(OllamaClientError, match="invalid JSON"):
        client.generate(model="granite4.1:3b", prompt="test prompt")


def test_generate_handles_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        raise error.URLError("connection refused")

    from google_okf_arxiv_assistant import ollama_client as module

    monkeypatch.setattr(module.request, "urlopen", fake_urlopen)
    client = OllamaClient(base_url="http://127.0.0.1:11434", timeout_seconds=10)
    with pytest.raises(OllamaClientError, match="Could not reach Ollama"):
        client.generate(model="granite4.1:3b", prompt="test prompt")
