from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import types

import pytest

from google_okf_arxiv_assistant.producer import (
    ArxivBulkConfig,
    PaperRecord,
    bulk_build_manifest,
    records_from_arxiv_bulk,
    select_bulk_records,
    write_build_manifest,
    write_okf_bundle,
)


def _paper(
    *,
    paper_id: str,
    submitted_at: str,
    categories: list[str] | None = None,
) -> PaperRecord:
    return PaperRecord(
        paper_id=paper_id,
        title=f"Title {paper_id}",
        abstract=f"Abstract {paper_id}",
        url=f"https://arxiv.org/abs/{paper_id}",
        categories=categories or ["cs.AI"],
        submitted_at=submitted_at,
    )


def test_select_bulk_records_applies_recency_dedupe_and_limit() -> None:
    config = ArxivBulkConfig(
        categories=["cs.AI", "cs.CL"],
        per_category_limit=100,
        max_total=3,
        years_back=5,
    )
    now = datetime(2026, 7, 6, 0, 0, tzinfo=UTC)

    category_records = {
        "cs.AI": [
            _paper(paper_id="a1", submitted_at="2026-06-01T00:00:00+00:00", categories=["cs.AI"]),
            _paper(paper_id="shared", submitted_at="2025-09-01T00:00:00+00:00", categories=["cs.AI"]),
            _paper(paper_id="old", submitted_at="2010-01-01T00:00:00+00:00", categories=["cs.AI"]),
        ],
        "cs.CL": [
            _paper(paper_id="shared", submitted_at="2026-01-01T00:00:00+00:00", categories=["cs.CL"]),
            _paper(paper_id="c1", submitted_at="2024-01-01T00:00:00+00:00", categories=["cs.CL"]),
        ],
    }

    selected, stats = select_bulk_records(
        category_records=category_records,
        config=config,
        now=now,
    )

    assert [row.paper_id for row in selected] == ["a1", "shared", "c1"]
    assert stats["duplicate_skipped"] == 1
    assert stats["recency_skipped"] == 1
    assert stats["selected_total"] == 3
    assert stats["selected_by_category"] == {"cs.AI": 2, "cs.CL": 1}
    assert stats["reached_max_total"] is True


def test_select_bulk_records_respects_global_max_total() -> None:
    config = ArxivBulkConfig(
        categories=["cs.AI"],
        per_category_limit=100,
        max_total=2,
        years_back=5,
    )
    now = datetime(2026, 7, 6, 0, 0, tzinfo=UTC)
    category_records = {
        "cs.AI": [
            _paper(paper_id="a1", submitted_at="2026-06-01T00:00:00+00:00"),
            _paper(paper_id="a2", submitted_at="2026-05-01T00:00:00+00:00"),
            _paper(paper_id="a3", submitted_at="2026-04-01T00:00:00+00:00"),
        ],
    }

    selected, stats = select_bulk_records(
        category_records=category_records,
        config=config,
        now=now,
    )

    assert len(selected) == 2
    assert [row.paper_id for row in selected] == ["a1", "a2"]
    assert stats["reached_max_total"] is True


def test_records_from_arxiv_bulk_fetches_per_category(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeSearch:
        def __init__(self, query: str, max_results: int, sort_by: object) -> None:
            self.query = query
            self.max_results = max_results
            self.sort_by = sort_by

    class _FakeResult:
        def __init__(
            self,
            *,
            entry_id: str,
            title: str,
            summary: str,
            categories: list[str],
            published: datetime,
        ) -> None:
            self.entry_id = entry_id
            self.title = title
            self.summary = summary
            self.categories = categories
            self.published = published

    class _FakeClient:
        def __init__(self, payload: dict[str, list[_FakeResult]]) -> None:
            self.payload = payload
            self.calls: list[tuple[str, int, object]] = []

        def results(self, search: _FakeSearch):
            self.calls.append((search.query, search.max_results, search.sort_by))
            return iter(self.payload.get(search.query, []))

    payload = {
        "cat:cs.AI": [
            _FakeResult(
                entry_id="https://arxiv.org/abs/2401.00001",
                title="AI One",
                summary="Summary",
                categories=["cs.AI"],
                published=datetime(2025, 6, 1, tzinfo=UTC),
            ),
        ],
        "cat:cs.CL": [
            _FakeResult(
                entry_id="https://arxiv.org/abs/2401.00002",
                title="CL One",
                summary="Summary",
                categories=["cs.CL"],
                published=datetime(2025, 6, 2, tzinfo=UTC),
            ),
        ],
    }
    fake_client = _FakeClient(payload)
    fake_module = types.SimpleNamespace(
        Client=lambda: fake_client,
        Search=_FakeSearch,
        SortCriterion=types.SimpleNamespace(SubmittedDate="submitted_date"),
    )
    monkeypatch.setitem(sys.modules, "arxiv", fake_module)

    config = ArxivBulkConfig(
        categories=["cs.AI", "cs.CL"],
        per_category_limit=3,
        max_total=10,
        years_back=5,
    )
    records, stats = records_from_arxiv_bulk(config=config, now=datetime(2026, 7, 6, tzinfo=UTC))

    assert [row.paper_id for row in records] == ["2401.00001", "2401.00002"]
    assert fake_client.calls == [
        ("cat:cs.AI", 3, "submitted_date"),
        ("cat:cs.CL", 3, "submitted_date"),
    ]
    assert stats["selected_total"] == 2
    assert stats["selected_by_category"] == {"cs.AI": 1, "cs.CL": 1}


def test_write_okf_bundle_fails_if_non_empty(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    output.mkdir(parents=True)
    (output / "existing.txt").write_text("sentinel", encoding="utf-8")

    with pytest.raises(ValueError, match="not empty"):
        write_okf_bundle(
            records=[_paper(paper_id="x1", submitted_at="2026-01-01T00:00:00+00:00")],
            output_dir=output,
            fail_if_non_empty=True,
        )


def test_bulk_manifest_write_roundtrip(tmp_path: Path) -> None:
    config = ArxivBulkConfig(categories=["cs.AI"], per_category_limit=2, max_total=1, years_back=5)
    manifest = bulk_build_manifest(
        config=config,
        selection_stats={
            "selected_total": 1,
            "scanned_total": 2,
            "scanned_by_category": {"cs.AI": 2},
            "selected_by_category": {"cs.AI": 1},
            "recency_skipped": 0,
            "duplicate_skipped": 0,
            "cutoff_utc": "2021-07-07T00:00:00+00:00",
            "max_total": 1,
            "reached_max_total": True,
        },
        output_dir=tmp_path,
    )
    path = write_build_manifest(tmp_path, manifest)

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert '"source": "arxiv"' in text
    assert '"max_total": 1' in text
