"""FastAPI application exposing retrieval-backed query and search endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from google_okf_arxiv_assistant.consumer import (
    OkfKnowledgeBase,
    SearchFilters,
    SearchSort,
    answer_from_hits,
)
from google_okf_arxiv_assistant.ollama_client import OllamaClient, OllamaClientError

AllowedChatModel = Literal["granite4.1:3b", "qwen3.5:2b", "nemotron-3-nano:4b"]
DEFAULT_CHAT_MODEL: AllowedChatModel = "granite4.1:3b"
MODELED_QUERY_WARNING_NO_HITS = "No supporting evidence found; returned deterministic fallback."


class QueryRequest(BaseModel):
    """Request payload for /query endpoint."""

    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class QueryResponse(BaseModel):
    """Response payload for /query endpoint."""

    answer: str
    citations: list[str]


class QueryModelRequest(BaseModel):
    """Request payload for /query-model endpoint."""

    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    model: AllowedChatModel = DEFAULT_CHAT_MODEL


class QueryModelResponse(BaseModel):
    """Response payload for /query-model endpoint."""

    answer: str
    citations: list[str]
    mode: Literal["model", "fallback"]
    model_used: str
    warning: str | None = None


class SearchFiltersRequest(BaseModel):
    """Optional filter payload for /search endpoint."""

    doc_type: str | None = None
    tags_any: list[str] | None = None
    paper_id_contains: str | None = None


class SearchRequest(BaseModel):
    """Request payload for /search endpoint."""

    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    filters: SearchFiltersRequest | None = None
    sort_by: Literal["score_desc", "title_asc", "updated_at_desc"] = "score_desc"


class SearchResultResponse(BaseModel):
    """Single search result item for /search endpoint."""

    doc_name: str
    title: str
    doc_type: str
    paper_id: str
    tags: list[str]
    score: float
    snippet: str
    highlights: list[str]


class SearchResponse(BaseModel):
    """Response payload for /search endpoint."""

    results: list[SearchResultResponse]


class DocumentResponse(BaseModel):
    """Response payload for /documents/{doc_name}."""

    doc_name: str
    frontmatter: dict[str, Any]
    body: str


class TagCountResponse(BaseModel):
    """Tag histogram row for /stats."""

    tag: str
    count: int


class StatsResponse(BaseModel):
    """Bundle-level stats response."""

    total_docs: int
    types_count: dict[str, int]
    tags_count_top: list[TagCountResponse]
    has_index: bool


app = FastAPI(title="Google OKF ArXiv Research Assistant", version="0.1.0")


def _bundle_path() -> Path:
    return Path(os.environ.get("OKF_BUNDLE_DIR", "okf"))


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def _ollama_timeout_seconds() -> int:
    raw = os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60").strip()
    try:
        timeout = int(raw)
    except ValueError:
        timeout = 60
    return max(1, timeout)


def _build_model_prompt(question: str, citations: list[str], snippets: list[str]) -> str:
    evidence_rows = []
    for idx, (citation, snippet) in enumerate(zip(citations, snippets, strict=True), start=1):
        evidence_rows.append(f"{idx}. [{citation}] {snippet}")

    evidence_block = "\n".join(evidence_rows)
    return (
        "You are an assistant grounded only in provided OKF evidence.\n"
        "Answer the question directly, do not invent facts, and prefer concise language.\n"
        "If evidence is insufficient, say so clearly.\n\n"
        f"Question:\n{question}\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        "Return a final answer and cite the document names in-line when relevant."
    )


def _deterministic_fallback_response(
    *,
    question: str,
    hits: list[Any],
    model: AllowedChatModel,
    warning: str,
) -> QueryModelResponse:
    answer = answer_from_hits(question, hits)
    citations = [hit.path.name for hit in hits]
    return QueryModelResponse(
        answer=answer,
        citations=citations,
        mode="fallback",
        model_used=model,
        warning=warning,
    )


def _load_kb_or_raise() -> OkfKnowledgeBase:
    bundle_path = _bundle_path()
    if not bundle_path.exists():
        raise HTTPException(status_code=400, detail=f"Bundle directory not found: {bundle_path}")

    kb = OkfKnowledgeBase(bundle_path)
    kb.load()
    return kb


@app.get("/health")
def health() -> dict[str, str]:
    """Readiness endpoint."""
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest) -> QueryResponse:
    """Answer a question from local OKF bundle documents."""
    kb = _load_kb_or_raise()
    hits = kb.search(query=request.query, top_k=request.top_k)
    answer = answer_from_hits(request.query, hits)

    return QueryResponse(answer=answer, citations=[hit.path.name for hit in hits])


@app.post("/query-model", response_model=QueryModelResponse)
def query_model_endpoint(request: QueryModelRequest) -> QueryModelResponse:
    """Answer a question using lexical retrieval + local Ollama synthesis."""
    kb = _load_kb_or_raise()
    hits = kb.search(query=request.query, top_k=request.top_k)

    if not hits:
        return _deterministic_fallback_response(
            question=request.query,
            hits=hits,
            model=request.model,
            warning=MODELED_QUERY_WARNING_NO_HITS,
        )

    citations = [hit.path.name for hit in hits]
    snippets = [hit.snippet for hit in hits]
    prompt = _build_model_prompt(
        question=request.query,
        citations=citations,
        snippets=snippets,
    )

    client = OllamaClient(
        base_url=_ollama_base_url(),
        timeout_seconds=_ollama_timeout_seconds(),
    )
    try:
        generated = client.generate(model=request.model, prompt=prompt)
    except OllamaClientError as exc:
        return _deterministic_fallback_response(
            question=request.query,
            hits=hits,
            model=request.model,
            warning=f"Model inference failed: {exc}",
        )
    except Exception as exc:  # pragma: no cover - defensive fallback guard
        return _deterministic_fallback_response(
            question=request.query,
            hits=hits,
            model=request.model,
            warning=f"Model inference failed: {exc}",
        )

    if not generated.strip():
        return _deterministic_fallback_response(
            question=request.query,
            hits=hits,
            model=request.model,
            warning="Model returned an empty response.",
        )

    answer = generated.strip()
    if citations:
        answer = f"{answer}\n\nCitations: {', '.join(citations)}"

    return QueryModelResponse(
        answer=answer,
        citations=citations,
        mode="model",
        model_used=request.model,
        warning=None,
    )


@app.post("/search", response_model=SearchResponse)
def search_endpoint(request: SearchRequest) -> SearchResponse:
    """Return structured lexical search results with filters and highlights."""
    kb = _load_kb_or_raise()

    filters = None
    if request.filters is not None:
        filters = SearchFilters(
            doc_type=request.filters.doc_type,
            tags_any=request.filters.tags_any,
            paper_id_contains=request.filters.paper_id_contains,
        )

    results = kb.search_structured(
        query=request.query,
        top_k=request.top_k,
        filters=filters,
        sort_by=request.sort_by,
    )

    payload = [
        SearchResultResponse(
            doc_name=item.path.name,
            title=item.title,
            doc_type=item.doc_type,
            paper_id=item.paper_id,
            tags=item.tags,
            score=round(float(item.score), 6),
            snippet=item.snippet,
            highlights=item.highlights,
        )
        for item in results
    ]
    return SearchResponse(results=payload)


@app.get("/documents/{doc_name}", response_model=DocumentResponse)
def document_endpoint(doc_name: str) -> DocumentResponse:
    """Fetch a single document by filename for citation preview."""
    kb = _load_kb_or_raise()
    try:
        doc = kb.get_document(doc_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_name}")

    return DocumentResponse(doc_name=doc.path.name, frontmatter=doc.frontmatter, body=doc.body)


@app.get("/stats", response_model=StatsResponse)
def stats_endpoint() -> StatsResponse:
    """Return bundle-level statistics for status dashboards."""
    kb = _load_kb_or_raise()
    stats = kb.get_stats()
    return StatsResponse(
        total_docs=int(stats["total_docs"]),
        types_count={str(k): int(v) for k, v in dict(stats["types_count"]).items()},
        tags_count_top=[TagCountResponse(tag=row["tag"], count=int(row["count"])) for row in stats["tags_count_top"]],
        has_index=bool(stats["has_index"]),
    )
