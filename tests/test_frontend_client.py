from __future__ import annotations

from urllib import error

import pytest

from google_okf_arxiv_assistant import frontend_client


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_query_backend_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse('{"answer":"ok","citations":["concept-lora.md"]}')

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    result = frontend_client.query_backend("http://127.0.0.1:8000/", "What is LoRA?", 5)
    assert result.answer == "ok"
    assert result.citations == ["concept-lora.md"]
    assert result.mode == "deterministic"


def test_query_backend_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse("not-json")

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    with pytest.raises(frontend_client.FrontendClientError, match="invalid JSON"):
        frontend_client.query_backend("http://127.0.0.1:8000", "What is LoRA?", 5)


def test_check_backend_health_true(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse('{"status":"ok"}')

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    assert frontend_client.check_backend_health("http://127.0.0.1:8000") is True


def test_check_backend_health_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        raise error.URLError("connection refused")

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    with pytest.raises(frontend_client.FrontendClientError, match="Could not reach backend"):
        frontend_client.check_backend_health("http://127.0.0.1:8000")


def test_normalize_api_base_url_rejects_empty() -> None:
    with pytest.raises(frontend_client.FrontendClientError, match="empty"):
        frontend_client.normalize_api_base_url("   ")


def test_search_backend_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse(
            '{"results":[{"doc_name":"concept-lora.md","title":"LoRA","doc_type":"concept",'
            '"paper_id":"2106.09685","tags":["nlp"],"score":0.8,'
            '"snippet":"Low-rank adaptation","highlights":["lora"]}]}'
        )

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    results = frontend_client.search_backend(
        api_base_url="http://127.0.0.1:8000",
        query="LoRA adaptation",
        top_k=10,
        doc_type="concept",
        tags_any=["nlp"],
        paper_id_contains="2106",
        sort_by="score_desc",
    )
    assert len(results) == 1
    assert results[0].doc_name == "concept-lora.md"
    assert results[0].score == pytest.approx(0.8)


def test_fetch_document_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse(
            '{"doc_name":"concept-lora.md","frontmatter":{"type":"concept","title":"LoRA"},'
            '"body":"# LoRA\\n\\nLow-rank adaptation."}'
        )

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    result = frontend_client.fetch_document("http://127.0.0.1:8000", "concept-lora.md")
    assert result.doc_name == "concept-lora.md"
    assert result.frontmatter["type"] == "concept"
    assert "Low-rank adaptation" in result.body


def test_fetch_stats_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse(
            '{"total_docs":3,"types_count":{"index":1,"concept":2},'
            '"tags_count_top":[{"tag":"nlp","count":2}],"has_index":true}'
        )

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    stats = frontend_client.fetch_stats("http://127.0.0.1:8000")
    assert stats.total_docs == 3
    assert stats.types_count == {"index": 1, "concept": 2}
    assert len(stats.tags_count_top) == 1
    assert stats.tags_count_top[0].tag == "nlp"
    assert stats.has_index is True


def test_query_model_backend_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse(
            '{"answer":"model answer","citations":["concept-lora.md"],'
            '"mode":"model","model_used":"granite4.1:3b","warning":null}'
        )

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    result = frontend_client.query_model_backend(
        "http://127.0.0.1:8000/",
        "What is LoRA?",
        5,
        "granite4.1:3b",
    )
    assert result.answer == "model answer"
    assert result.citations == ["concept-lora.md"]
    assert result.mode == "model"
    assert result.model_used == "granite4.1:3b"
    assert result.warning is None


def test_query_model_backend_rejects_invalid_mode_type(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _FakeResponse(
            '{"answer":"model answer","citations":["concept-lora.md"],'
            '"mode":123,"model_used":"granite4.1:3b","warning":null}'
        )

    monkeypatch.setattr(frontend_client.request, "urlopen", fake_urlopen)

    with pytest.raises(frontend_client.FrontendClientError, match="mode"):
        frontend_client.query_model_backend(
            "http://127.0.0.1:8000/",
            "What is LoRA?",
            5,
            "granite4.1:3b",
        )
