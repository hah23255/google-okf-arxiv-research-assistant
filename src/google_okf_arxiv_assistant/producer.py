"""Producer pipeline to create OKF bundle content from ArXiv metadata."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

from google_okf_arxiv_assistant.okf import dump_okf_markdown

logger = logging.getLogger(__name__)

DEFAULT_BULK_CATEGORIES: tuple[str, ...] = (
    "cs.AI",
    "cs.CL",
    "cs.LG",
    "cs.CV",
    "stat.ML",
    "cs.IR",
    "eess.SP",
)


@dataclass(slots=True)
class PaperRecord:
    """Canonical paper record used by bundle producer."""

    paper_id: str
    title: str
    abstract: str
    url: str
    categories: list[str]
    submitted_at: str = ""


@dataclass(slots=True)
class ArxivBulkConfig:
    """Configuration for large, multi-category ArXiv ingestion."""

    categories: list[str]
    per_category_limit: int = 5000
    max_total: int = 30000
    years_back: int = 5

    def __post_init__(self) -> None:
        self.categories = [category.strip() for category in self.categories if category.strip()]
        if not self.categories:
            raise ValueError("At least one ArXiv category is required")
        if self.per_category_limit < 1:
            raise ValueError("per_category_limit must be >= 1")
        if self.max_total < 1:
            raise ValueError("max_total must be >= 1")
        if self.years_back < 1:
            raise ValueError("years_back must be >= 1")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned[:120] or "untitled"


def _paper_frontmatter(record: PaperRecord, created_at: str) -> dict[str, object]:
    frontmatter: dict[str, object] = {
        "type": "concept",
        "title": record.title,
        "entity": "paper",
        "paper_id": record.paper_id,
        "source_url": record.url,
        "tags": sorted(set(record.categories)),
        "created_at": created_at,
        "updated_at": created_at,
    }
    if record.submitted_at:
        frontmatter["submitted_at"] = record.submitted_at
    return frontmatter


def _paper_body(record: PaperRecord) -> str:
    categories = ", ".join(record.categories) if record.categories else "unclassified"
    submitted_line = f"- Submitted At: `{record.submitted_at}`\n" if record.submitted_at else ""
    return (
        f"# {record.title}\n\n"
        f"## Summary\n\n"
        f"{record.abstract.strip()}\n\n"
        f"## Metadata\n\n"
        f"- Paper ID: `{record.paper_id}`\n"
        f"{submitted_line}"
        f"- Categories: {categories}\n\n"
        f"## Resources\n\n"
        f"- [arXiv]({record.url})\n"
    )


def write_okf_bundle(
    records: Iterable[PaperRecord],
    output_dir: Path,
    *,
    fail_if_non_empty: bool = False,
) -> list[Path]:
    """Write a full OKF bundle from paper records.

    Args:
        records: Iterable of paper records.
        output_dir: Bundle directory (contains index.md + concept docs).
        fail_if_non_empty: Whether to fail when output dir already contains files.

    Returns:
        List of created markdown file paths.
    """
    if output_dir.exists() and fail_if_non_empty and any(output_dir.iterdir()):
        raise ValueError(f"Output directory is not empty: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC).isoformat()
    created_files: list[Path] = []
    index_lines = [
        "# ArXiv Knowledge Index",
        "",
        "## Concepts",
        "",
    ]

    for record in records:
        slug = _slug(f"{record.paper_id}-{record.title}")
        doc_name = f"concept-{slug}.md"
        doc_path = output_dir / doc_name
        frontmatter = _paper_frontmatter(record, created_at)
        body = _paper_body(record)
        doc_path.write_text(dump_okf_markdown(frontmatter, body), encoding="utf-8")
        created_files.append(doc_path)
        index_lines.append(f"- [{record.title}]({doc_name})")

    index_frontmatter = {
        "type": "index",
        "title": "ArXiv Knowledge Index",
        "created_at": created_at,
        "updated_at": created_at,
    }
    index_body = "\n".join(index_lines) + "\n"
    index_path = output_dir / "index.md"
    index_path.write_text(dump_okf_markdown(index_frontmatter, index_body), encoding="utf-8")
    created_files.append(index_path)

    logger.info("Wrote %s OKF docs to %s", len(created_files), output_dir)
    return created_files


def write_build_manifest(
    output_dir: Path,
    payload: dict[str, object],
    *,
    filename: str = "build_manifest.json",
) -> Path:
    """Write JSON manifest describing a bulk build."""
    path = output_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_submitted_at(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _normalize_datetime(parsed)


def _bulk_cutoff(*, years_back: int, now: datetime | None = None) -> datetime:
    anchor = _normalize_datetime(now) or datetime.now(UTC)
    return anchor - timedelta(days=365 * years_back)


def select_bulk_records(
    *,
    category_records: dict[str, list[PaperRecord]],
    config: ArxivBulkConfig,
    now: datetime | None = None,
) -> tuple[list[PaperRecord], dict[str, object]]:
    """Select records using recency filter, dedupe, and global size cap."""
    cutoff = _bulk_cutoff(years_back=config.years_back, now=now)
    seen_paper_ids: set[str] = set()
    selected: list[PaperRecord] = []

    scanned_by_category: dict[str, int] = {category: 0 for category in config.categories}
    selected_by_category: dict[str, int] = {category: 0 for category in config.categories}

    recency_skipped = 0
    duplicate_skipped = 0

    for category in config.categories:
        ranked_for_category: list[tuple[datetime, PaperRecord]] = []
        for record in category_records.get(category, []):
            scanned_by_category[category] += 1
            submitted_dt = _parse_submitted_at(record.submitted_at)
            if submitted_dt is None or submitted_dt < cutoff:
                recency_skipped += 1
                continue
            ranked_for_category.append((submitted_dt, record))

        ranked_for_category.sort(key=lambda row: (-row[0].timestamp(), row[1].paper_id))

        for _, record in ranked_for_category:
            if record.paper_id in seen_paper_ids:
                duplicate_skipped += 1
                continue

            seen_paper_ids.add(record.paper_id)
            selected.append(record)
            selected_by_category[category] += 1
            if len(selected) >= config.max_total:
                stats = {
                    "cutoff_utc": cutoff.isoformat(),
                    "max_total": config.max_total,
                    "selected_total": len(selected),
                    "scanned_total": sum(scanned_by_category.values()),
                    "scanned_by_category": scanned_by_category,
                    "selected_by_category": selected_by_category,
                    "recency_skipped": recency_skipped,
                    "duplicate_skipped": duplicate_skipped,
                    "reached_max_total": True,
                }
                return selected, stats

    stats = {
        "cutoff_utc": cutoff.isoformat(),
        "max_total": config.max_total,
        "selected_total": len(selected),
        "scanned_total": sum(scanned_by_category.values()),
        "scanned_by_category": scanned_by_category,
        "selected_by_category": selected_by_category,
        "recency_skipped": recency_skipped,
        "duplicate_skipped": duplicate_skipped,
        "reached_max_total": False,
    }
    return selected, stats


def _record_from_arxiv_result(result: object) -> PaperRecord:
    published = _normalize_datetime(getattr(result, "published", None))
    return PaperRecord(
        paper_id=str(getattr(result, "entry_id").rsplit("/", maxsplit=1)[-1]),
        title=str(getattr(result, "title")).strip(),
        abstract=str(getattr(result, "summary")).strip(),
        url=str(getattr(result, "entry_id")),
        categories=[str(item) for item in getattr(result, "categories")],
        submitted_at=published.isoformat() if published is not None else "",
    )


def records_from_arxiv_bulk(
    config: ArxivBulkConfig,
    *,
    now: datetime | None = None,
) -> tuple[list[PaperRecord], dict[str, object]]:
    """Fetch and select records for a large multi-category ArXiv build."""
    import arxiv

    client = arxiv.Client()
    fetched: dict[str, list[PaperRecord]] = {}

    for category in config.categories:
        search = arxiv.Search(
            query=f"cat:{category}",
            max_results=config.per_category_limit,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        fetched[category] = [_record_from_arxiv_result(result) for result in client.results(search)]

    selected, stats = select_bulk_records(
        category_records=fetched,
        config=config,
        now=now,
    )
    return selected, stats


def bulk_build_manifest(
    *,
    config: ArxivBulkConfig,
    selection_stats: dict[str, object],
    output_dir: Path,
) -> dict[str, object]:
    """Assemble a canonical manifest payload for bulk builds."""
    return {
        "source": "arxiv",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "output_dir": str(output_dir),
        "config": {
            "categories": config.categories,
            "per_category_limit": config.per_category_limit,
            "max_total": config.max_total,
            "years_back": config.years_back,
        },
        "stats": selection_stats,
    }


def records_from_jsonl(path: Path) -> list[PaperRecord]:
    """Load PaperRecord rows from JSONL input."""
    rows: list[PaperRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows.append(
                PaperRecord(
                    paper_id=str(row["paper_id"]),
                    title=str(row["title"]),
                    abstract=str(row["abstract"]),
                    url=str(row.get("url") or f"https://arxiv.org/abs/{row['paper_id']}"),
                    categories=[str(x) for x in row.get("categories", [])],
                    submitted_at=str(row.get("submitted_at", "")),
                )
            )
            if not rows[-1].paper_id or not rows[-1].title:
                raise ValueError(f"Invalid record at line {line_no}: {row}")
    return rows


def records_from_arxiv_query(query: str, limit: int = 100) -> list[PaperRecord]:
    """Fetch paper records directly from ArXiv.

    Requires `arxiv` package at runtime.
    """
    import arxiv

    client = arxiv.Client()
    search = arxiv.Search(query=query, max_results=limit, sort_by=arxiv.SortCriterion.SubmittedDate)

    rows: list[PaperRecord] = []
    for result in client.results(search):
        paper_id = result.entry_id.rsplit("/", maxsplit=1)[-1]
        rows.append(
            PaperRecord(
                paper_id=paper_id,
                title=result.title.strip(),
                abstract=result.summary.strip(),
                url=result.entry_id,
                categories=list(result.categories),
                submitted_at=_normalize_datetime(result.published).isoformat()
                if _normalize_datetime(result.published) is not None
                else "",
            )
        )
    return rows
