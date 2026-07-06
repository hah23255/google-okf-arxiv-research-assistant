"""Consumer and retrieval primitives over an OKF bundle."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from google_okf_arxiv_assistant.okf import OkfDocument, parse_okf_markdown

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
SearchSort = Literal["score_desc", "title_asc", "updated_at_desc"]


@dataclass(slots=True)
class SearchHit:
    """A ranked search hit from OKF knowledge bundle."""

    score: float
    path: Path
    title: str
    snippet: str


@dataclass(slots=True)
class SearchFilters:
    """Optional metadata filters for structured search."""

    doc_type: str | None = None
    tags_any: list[str] | None = None
    paper_id_contains: str | None = None


@dataclass(slots=True)
class SearchResult:
    """Structured search result with metadata and highlights."""

    score: float
    path: Path
    title: str
    snippet: str
    highlights: list[str]
    doc_type: str
    paper_id: str
    tags: list[str]
    updated_at: str


class OkfKnowledgeBase:
    """In-memory lexical retriever for OKF markdown bundle."""

    def __init__(self, bundle_dir: Path) -> None:
        self.bundle_dir = bundle_dir
        self._docs: list[OkfDocument] = []
        self._tokens: list[set[str]] = []
        self._by_name: dict[str, OkfDocument] = {}

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {tok.lower() for tok in TOKEN_RE.findall(text)}

    @staticmethod
    def _normalize_tags(raw: object) -> list[str]:
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str):
            return [raw.strip()] if raw.strip() else []
        return []

    @staticmethod
    def _build_snippet(text: str, max_len: int = 240) -> str:
        return text[:max_len].replace("\n", " ").strip()

    @staticmethod
    def _compute_highlights(query_tokens: set[str], snippet: str) -> list[str]:
        snippet_tokens = {tok.lower() for tok in TOKEN_RE.findall(snippet)}
        return sorted(query_tokens & snippet_tokens)

    def _ensure_loaded(self) -> None:
        if not self._docs:
            self.load()

    def load(self) -> None:
        """Load markdown docs from bundle directory and build lexical index."""
        docs: list[OkfDocument] = []
        tokens: list[set[str]] = []
        by_name: dict[str, OkfDocument] = {}

        for path in sorted(self.bundle_dir.glob("*.md")):
            doc = parse_okf_markdown(path)
            docs.append(doc)
            merged_text = f"{doc.title}\n{doc.body}"
            tokens.append(self._tokenize(merged_text))
            by_name[path.name] = doc

        self._docs = docs
        self._tokens = tokens
        self._by_name = by_name

    def _passes_filters(self, result: SearchResult, filters: SearchFilters | None) -> bool:
        if filters is None:
            return True

        if filters.doc_type and result.doc_type != filters.doc_type:
            return False

        if filters.tags_any:
            wanted = {tag.lower().strip() for tag in filters.tags_any if tag.strip()}
            actual = {tag.lower() for tag in result.tags}
            if wanted and wanted.isdisjoint(actual):
                return False

        if filters.paper_id_contains:
            needle = filters.paper_id_contains.lower().strip()
            if needle and needle not in result.paper_id.lower():
                return False

        return True

    def search_structured(
        self,
        query: str,
        top_k: int = 5,
        filters: SearchFilters | None = None,
        sort_by: SearchSort = "score_desc",
    ) -> list[SearchResult]:
        """Run structured lexical search with optional filters and sort modes."""
        self._ensure_loaded()

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored: list[SearchResult] = []
        for doc, doc_tokens in zip(self._docs, self._tokens, strict=True):
            doc_type = doc.doc_type
            if doc_type == "index":
                continue

            overlap = len(query_tokens & doc_tokens)
            if overlap == 0:
                continue

            denom = math.sqrt(len(query_tokens) * max(1, len(doc_tokens)))
            score = overlap / denom
            snippet = self._build_snippet(doc.body)
            tags = self._normalize_tags(doc.frontmatter.get("tags"))
            paper_id = str(doc.frontmatter.get("paper_id", "")).strip()
            updated_at = str(doc.frontmatter.get("updated_at", "")).strip()

            result = SearchResult(
                score=score,
                path=doc.path,
                title=doc.title,
                snippet=snippet,
                highlights=self._compute_highlights(query_tokens, snippet),
                doc_type=doc_type,
                paper_id=paper_id,
                tags=tags,
                updated_at=updated_at,
            )

            if self._passes_filters(result, filters):
                scored.append(result)

        if sort_by == "score_desc":
            scored.sort(key=lambda item: (-item.score, item.title.lower(), item.path.name))
        elif sort_by == "title_asc":
            scored.sort(key=lambda item: (item.title.lower(), -item.score, item.path.name))
        elif sort_by == "updated_at_desc":
            scored.sort(key=lambda item: (item.title.lower(), item.path.name))
            scored.sort(key=lambda item: item.updated_at or "", reverse=True)
        else:
            raise ValueError(f"Unsupported sort mode: {sort_by}")

        return scored[: max(1, int(top_k))]

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        """Run lexical search with legacy result shape for compatibility."""
        results = self.search_structured(query=query, top_k=top_k, filters=None, sort_by="score_desc")
        return [
            SearchHit(score=item.score, path=item.path, title=item.title, snippet=item.snippet)
            for item in results
        ]

    def get_document(self, doc_name: str) -> OkfDocument:
        """Return parsed document by filename from bundle."""
        self._ensure_loaded()

        clean_name = doc_name.strip()
        if not clean_name:
            raise ValueError("Document name is empty")
        if clean_name != Path(clean_name).name or "/" in clean_name or "\\" in clean_name:
            raise ValueError("Document name must be a plain filename")

        doc = self._by_name.get(clean_name)
        if doc is None:
            raise FileNotFoundError(clean_name)
        return doc

    def get_stats(self) -> dict[str, object]:
        """Compute bundle-level stats for UI/ops visibility."""
        self._ensure_loaded()

        type_counts: dict[str, int] = {}
        tag_counts: dict[str, int] = {}

        for doc in self._docs:
            doc_type = doc.doc_type or "unknown"
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
            for tag in self._normalize_tags(doc.frontmatter.get("tags")):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        tags_sorted = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))
        top_tags = [{"tag": tag, "count": count} for tag, count in tags_sorted[:20]]

        return {
            "total_docs": len(self._docs),
            "types_count": type_counts,
            "tags_count_top": top_tags,
            "has_index": "index.md" in self._by_name,
        }


def answer_from_hits(question: str, hits: list[SearchHit]) -> str:
    """Construct a deterministic, citation-forward answer from retrieval hits."""
    if not hits:
        return "I could not find supporting OKF concepts for this question."

    lines = [f"Question: {question}", "", "Evidence summary:"]
    for idx, hit in enumerate(hits, start=1):
        lines.append(f"{idx}. {hit.title} ({hit.path.name})")
        lines.append(f"   {hit.snippet}")

    lines.append("")
    lines.append("Citations: " + ", ".join(hit.path.name for hit in hits))
    return "\n".join(lines)
