from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from google_okf_arxiv_assistant.api import (
    QueryModelRequest,
    QueryRequest,
    SearchFiltersRequest,
    SearchRequest,
    document_endpoint,
    health,
    query_model_endpoint,
    query_endpoint,
    search_endpoint,
    stats_endpoint,
)
from google_okf_arxiv_assistant.ollama_client import OllamaClientError
from google_okf_arxiv_assistant.okf import dump_okf_markdown


def test_health() -> None:
    assert health() == {"status": "ok"}


def _write_bundle(tmp_path: Path) -> None:
    (tmp_path / "index.md").write_text(
        dump_okf_markdown(
            {"type": "index", "title": "Index"},
            "# Index\n\n- [LoRA](concept-lora.md)\n- [DiT](concept-dit.md)",
        ),
        encoding="utf-8",
    )
    (tmp_path / "concept-lora.md").write_text(
        dump_okf_markdown(
            {
                "type": "concept",
                "title": "LoRA",
                "paper_id": "2106.09685",
                "tags": ["nlp", "finetuning"],
                "updated_at": "2026-06-20",
            },
            "# LoRA\n\nLow-rank adaptation for LLM fine-tuning.",
        ),
        encoding="utf-8",
    )
    (tmp_path / "concept-dit.md").write_text(
        dump_okf_markdown(
            {
                "type": "concept",
                "title": "Diffusion Transformer",
                "paper_id": "2401.77777",
                "tags": ["vision", "diffusion"],
                "updated_at": "2026-07-01",
            },
            "# DiT\n\nDiffusion transformer for images.",
        ),
        encoding="utf-8",
    )


def test_query_endpoint_returns_citations(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path)
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(tmp_path))

    response = query_endpoint(QueryRequest(query="What is LoRA?", top_k=3))

    assert "concept-lora.md" in response.citations
    assert "Evidence summary" in response.answer


def test_search_endpoint_returns_filtered_results(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path)
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(tmp_path))

    response = search_endpoint(
        SearchRequest(
            query="diffusion transformer",
            top_k=5,
            sort_by="updated_at_desc",
            filters=SearchFiltersRequest(
                doc_type="concept",
                tags_any=["vision"],
                paper_id_contains="2401",
            ),
        )
    )

    assert len(response.results) == 1
    assert response.results[0].doc_name == "concept-dit.md"
    assert "diffusion" in response.results[0].highlights


def test_query_model_endpoint_success(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path)
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(tmp_path))

    def fake_generate(self, *, model: str, prompt: str) -> str:
        assert model == "granite4.1:3b"
        assert "Question:" in prompt
        assert "Evidence:" in prompt
        return "LoRA adapts models using low-rank updates."

    monkeypatch.setattr("google_okf_arxiv_assistant.api.OllamaClient.generate", fake_generate)

    response = query_model_endpoint(
        QueryModelRequest(query="What is LoRA?", top_k=3, model="granite4.1:3b")
    )
    assert response.mode == "model"
    assert response.model_used == "granite4.1:3b"
    assert response.warning is None
    assert "Citations:" in response.answer
    assert "concept-lora.md" in response.citations


def test_query_model_endpoint_fallback_on_model_error(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path)
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(tmp_path))

    def fake_generate(self, *, model: str, prompt: str) -> str:
        raise OllamaClientError("simulated failure")

    monkeypatch.setattr("google_okf_arxiv_assistant.api.OllamaClient.generate", fake_generate)

    response = query_model_endpoint(
        QueryModelRequest(query="What is LoRA?", top_k=3, model="granite4.1:3b")
    )
    assert response.mode == "fallback"
    assert response.model_used == "granite4.1:3b"
    assert isinstance(response.warning, str)
    assert "Evidence summary" in response.answer
    assert "concept-lora.md" in response.citations


def test_query_model_endpoint_fallback_for_no_hits(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path)
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(tmp_path))

    response = query_model_endpoint(
        QueryModelRequest(query="zzz-unseen-topic", top_k=3, model="granite4.1:3b")
    )
    assert response.mode == "fallback"
    assert response.citations == []
    assert isinstance(response.warning, str)


def test_document_endpoint_returns_document_payload(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path)
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(tmp_path))

    response = document_endpoint("concept-lora.md")
    assert response.doc_name == "concept-lora.md"
    assert response.frontmatter["type"] == "concept"
    assert "Low-rank adaptation" in response.body


def test_document_endpoint_rejects_invalid_doc_name(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path)
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(tmp_path))

    with pytest.raises(HTTPException) as exc_info:
        document_endpoint("../concept-lora.md")

    assert exc_info.value.status_code == 400
    assert "plain filename" in str(exc_info.value.detail)


def test_stats_endpoint_returns_bundle_counts(tmp_path: Path, monkeypatch) -> None:
    _write_bundle(tmp_path)
    monkeypatch.setenv("OKF_BUNDLE_DIR", str(tmp_path))

    response = stats_endpoint()
    assert response.total_docs == 3
    assert response.types_count["index"] == 1
    assert response.types_count["concept"] == 2
    assert response.has_index is True
    assert any(row.tag == "vision" and row.count == 1 for row in response.tags_count_top)
