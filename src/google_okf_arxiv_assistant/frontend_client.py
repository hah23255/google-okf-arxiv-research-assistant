"""HTTP client helpers for Streamlit frontend -> FastAPI backend calls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, parse, request


class FrontendClientError(RuntimeError):
    """Raised when frontend-backend communication fails."""


@dataclass(slots=True)
class QueryResult:
    """Query result payload returned from backend."""

    answer: str
    citations: list[str]
    mode: str = "deterministic"
    model_used: str = ""
    warning: str | None = None


@dataclass(slots=True)
class SearchResultItem:
    """Structured search result from backend."""

    doc_name: str
    title: str
    doc_type: str
    paper_id: str
    tags: list[str]
    score: float
    snippet: str
    highlights: list[str]


@dataclass(slots=True)
class DocumentResult:
    """Document preview payload from backend."""

    doc_name: str
    frontmatter: dict[str, object]
    body: str


@dataclass(slots=True)
class TagCount:
    """Tag histogram row from /stats endpoint."""

    tag: str
    count: int


@dataclass(slots=True)
class StatsResult:
    """Bundle stats payload from backend."""

    total_docs: int
    types_count: dict[str, int]
    tags_count_top: list[TagCount]
    has_index: bool


def normalize_api_base_url(api_base_url: str) -> str:
    """Normalize API base URL and reject empty values."""
    cleaned = api_base_url.strip().rstrip("/")
    if not cleaned:
        raise FrontendClientError("API base URL is empty")
    return cleaned


def _parse_json_payload(raw: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FrontendClientError("Backend returned invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise FrontendClientError("Backend JSON payload is not an object")

    return parsed


def _read_http_response(req: request.Request, timeout: int) -> dict[str, object]:
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        msg = detail.strip() or str(exc.reason)
        raise FrontendClientError(f"HTTP {exc.code} from backend: {msg}") from exc
    except error.URLError as exc:
        raise FrontendClientError(f"Could not reach backend: {exc.reason}") from exc

    return _parse_json_payload(raw)


def check_backend_health(api_base_url: str, timeout: int = 5) -> bool:
    """Call backend health endpoint and return True when status is ok."""
    base_url = normalize_api_base_url(api_base_url)
    req = request.Request(f"{base_url}/health", method="GET")
    payload = _read_http_response(req=req, timeout=timeout)
    return str(payload.get("status", "")).lower() == "ok"


def query_backend(api_base_url: str, query: str, top_k: int, timeout: int = 20) -> QueryResult:
    """Call backend /query endpoint and validate response shape."""
    question = query.strip()
    if len(question) < 3:
        raise FrontendClientError("Query must be at least 3 characters long")

    base_url = normalize_api_base_url(api_base_url)
    body = json.dumps({"query": question, "top_k": int(top_k)}).encode("utf-8")
    req = request.Request(f"{base_url}/query", data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    payload = _read_http_response(req=req, timeout=timeout)

    answer = payload.get("answer")
    citations = payload.get("citations")

    if not isinstance(answer, str):
        raise FrontendClientError("Backend response is missing string field: answer")
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        raise FrontendClientError("Backend response has invalid field: citations")

    return QueryResult(
        answer=answer,
        citations=citations,
        mode="deterministic",
        model_used="",
        warning=None,
    )


def query_model_backend(
    api_base_url: str,
    query: str,
    top_k: int,
    model: str,
    timeout: int = 60,
) -> QueryResult:
    """Call backend /query-model endpoint and validate response shape."""
    question = query.strip()
    if len(question) < 3:
        raise FrontendClientError("Query must be at least 3 characters long")

    chosen_model = model.strip()
    if not chosen_model:
        raise FrontendClientError("Model must be a non-empty value")

    base_url = normalize_api_base_url(api_base_url)
    body = json.dumps(
        {
            "query": question,
            "top_k": int(top_k),
            "model": chosen_model,
        }
    ).encode("utf-8")
    req = request.Request(f"{base_url}/query-model", data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    payload = _read_http_response(req=req, timeout=timeout)

    answer = payload.get("answer")
    citations = payload.get("citations")
    mode = payload.get("mode")
    model_used = payload.get("model_used")
    warning = payload.get("warning")

    if not isinstance(answer, str):
        raise FrontendClientError("Backend response is missing string field: answer")
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        raise FrontendClientError("Backend response has invalid field: citations")
    if not isinstance(mode, str):
        raise FrontendClientError("Backend response has invalid field: mode")
    if not isinstance(model_used, str):
        raise FrontendClientError("Backend response has invalid field: model_used")
    if warning is not None and not isinstance(warning, str):
        raise FrontendClientError("Backend response has invalid field: warning")

    return QueryResult(
        answer=answer,
        citations=citations,
        mode=mode,
        model_used=model_used,
        warning=warning,
    )


def search_backend(
    api_base_url: str,
    query: str,
    top_k: int,
    doc_type: str | None = None,
    tags_any: list[str] | None = None,
    paper_id_contains: str | None = None,
    sort_by: str = "score_desc",
    timeout: int = 20,
) -> list[SearchResultItem]:
    """Call backend /search endpoint and parse structured search results."""
    question = query.strip()
    if len(question) < 3:
        raise FrontendClientError("Query must be at least 3 characters long")

    filters: dict[str, object] = {}
    if doc_type and doc_type.strip():
        filters["doc_type"] = doc_type.strip()
    clean_tags = [tag.strip() for tag in (tags_any or []) if tag.strip()]
    if clean_tags:
        filters["tags_any"] = clean_tags
    if paper_id_contains and paper_id_contains.strip():
        filters["paper_id_contains"] = paper_id_contains.strip()

    payload_in: dict[str, object] = {
        "query": question,
        "top_k": int(top_k),
        "sort_by": sort_by,
    }
    if filters:
        payload_in["filters"] = filters

    base_url = normalize_api_base_url(api_base_url)
    body = json.dumps(payload_in).encode("utf-8")
    req = request.Request(f"{base_url}/search", data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    payload = _read_http_response(req=req, timeout=timeout)
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise FrontendClientError("Backend response has invalid field: results")

    parsed: list[SearchResultItem] = []
    for item in raw_results:
        if not isinstance(item, dict):
            raise FrontendClientError("Search result row is not an object")

        doc_name = item.get("doc_name")
        title = item.get("title")
        doc_type_value = item.get("doc_type")
        paper_id = item.get("paper_id")
        tags = item.get("tags")
        score = item.get("score")
        snippet = item.get("snippet")
        highlights = item.get("highlights")

        if not isinstance(doc_name, str) or not isinstance(title, str):
            raise FrontendClientError("Search row missing required string fields")
        if not isinstance(doc_type_value, str) or not isinstance(paper_id, str):
            raise FrontendClientError("Search row has invalid metadata fields")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise FrontendClientError("Search row has invalid tags")
        if not isinstance(score, (int, float)):
            raise FrontendClientError("Search row has invalid score")
        if not isinstance(snippet, str):
            raise FrontendClientError("Search row has invalid snippet")
        if not isinstance(highlights, list) or any(not isinstance(h, str) for h in highlights):
            raise FrontendClientError("Search row has invalid highlights")

        parsed.append(
            SearchResultItem(
                doc_name=doc_name,
                title=title,
                doc_type=doc_type_value,
                paper_id=paper_id,
                tags=tags,
                score=float(score),
                snippet=snippet,
                highlights=highlights,
            )
        )

    return parsed


def fetch_document(api_base_url: str, doc_name: str, timeout: int = 20) -> DocumentResult:
    """Fetch full document payload from backend for preview."""
    clean_name = doc_name.strip()
    if not clean_name:
        raise FrontendClientError("Document name is empty")

    base_url = normalize_api_base_url(api_base_url)
    encoded_name = parse.quote(clean_name, safe="")
    req = request.Request(f"{base_url}/documents/{encoded_name}", method="GET")
    payload = _read_http_response(req=req, timeout=timeout)

    out_name = payload.get("doc_name")
    frontmatter = payload.get("frontmatter")
    body = payload.get("body")

    if not isinstance(out_name, str):
        raise FrontendClientError("Backend response is missing string field: doc_name")
    if not isinstance(frontmatter, dict):
        raise FrontendClientError("Backend response has invalid field: frontmatter")
    if not isinstance(body, str):
        raise FrontendClientError("Backend response has invalid field: body")

    return DocumentResult(doc_name=out_name, frontmatter=frontmatter, body=body)


def fetch_stats(api_base_url: str, timeout: int = 20) -> StatsResult:
    """Fetch bundle-level stats from backend."""
    base_url = normalize_api_base_url(api_base_url)
    req = request.Request(f"{base_url}/stats", method="GET")
    payload = _read_http_response(req=req, timeout=timeout)

    total_docs = payload.get("total_docs")
    types_count = payload.get("types_count")
    tags_count_top = payload.get("tags_count_top")
    has_index = payload.get("has_index")

    if not isinstance(total_docs, int):
        raise FrontendClientError("Backend response has invalid field: total_docs")
    if not isinstance(types_count, dict):
        raise FrontendClientError("Backend response has invalid field: types_count")
    if not isinstance(tags_count_top, list):
        raise FrontendClientError("Backend response has invalid field: tags_count_top")
    if not isinstance(has_index, bool):
        raise FrontendClientError("Backend response has invalid field: has_index")

    parsed_tag_counts: list[TagCount] = []
    for row in tags_count_top:
        if not isinstance(row, dict):
            raise FrontendClientError("Backend stats tag row is not an object")
        tag = row.get("tag")
        count = row.get("count")
        if not isinstance(tag, str) or not isinstance(count, int):
            raise FrontendClientError("Backend stats tag row has invalid fields")
        parsed_tag_counts.append(TagCount(tag=tag, count=count))

    parsed_types: dict[str, int] = {}
    for key, value in types_count.items():
        if not isinstance(key, str) or not isinstance(value, int):
            raise FrontendClientError("Backend response has invalid types_count rows")
        parsed_types[key] = value

    return StatsResult(
        total_docs=total_docs,
        types_count=parsed_types,
        tags_count_top=parsed_tag_counts,
        has_index=has_index,
    )
