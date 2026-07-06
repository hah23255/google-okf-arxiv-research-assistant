from __future__ import annotations

from pathlib import Path

import pytest

from google_okf_arxiv_assistant.consumer import OkfKnowledgeBase, SearchFilters, answer_from_hits
from google_okf_arxiv_assistant.okf import dump_okf_markdown


def test_search_returns_relevant_concept(tmp_path: Path) -> None:
    (tmp_path / "index.md").write_text(
        dump_okf_markdown(
            {"type": "index", "title": "Index"},
            "# Index\n\n- [LoRA](concept-lora.md)",
        ),
        encoding="utf-8",
    )
    (tmp_path / "concept-lora.md").write_text(
        dump_okf_markdown(
            {"type": "concept", "title": "LoRA"},
            "# LoRA\n\nLow-rank adaptation for LLM fine-tuning.",
        ),
        encoding="utf-8",
    )

    kb = OkfKnowledgeBase(tmp_path)
    kb.load()
    hits = kb.search("What is low rank adaptation?", top_k=3)

    assert hits
    assert hits[0].path.name == "concept-lora.md"


def test_search_no_hit_returns_empty_and_no_hit_answer() -> None:
    hits = []
    answer = answer_from_hits("Unknown topic", hits)

    assert answer == "I could not find supporting OKF concepts for this question."


def test_search_structured_respects_filters_and_sort(tmp_path: Path) -> None:
    (tmp_path / "index.md").write_text(
        dump_okf_markdown({"type": "index", "title": "Index"}, "# Index"),
        encoding="utf-8",
    )
    (tmp_path / "concept-diffusion-old.md").write_text(
        dump_okf_markdown(
            {
                "type": "concept",
                "title": "Diffusion Transformers (Early)",
                "paper_id": "2301.12345",
                "tags": ["vision", "diffusion"],
                "updated_at": "2026-04-01",
            },
            "# Diffusion Early\n\nA diffusion transformer baseline for images.",
        ),
        encoding="utf-8",
    )
    (tmp_path / "concept-diffusion-new.md").write_text(
        dump_okf_markdown(
            {
                "type": "concept",
                "title": "Diffusion Transformers (Latest)",
                "paper_id": "2401.77777",
                "tags": ["vision", "transformer"],
                "updated_at": "2026-07-01",
            },
            "# Diffusion Latest\n\nA stronger diffusion transformer variant.",
        ),
        encoding="utf-8",
    )
    (tmp_path / "concept-lora.md").write_text(
        dump_okf_markdown(
            {
                "type": "concept",
                "title": "LoRA",
                "paper_id": "2106.09685",
                "tags": ["nlp"],
                "updated_at": "2026-06-15",
            },
            "# LoRA\n\nLow-rank adaptation for language models.",
        ),
        encoding="utf-8",
    )

    kb = OkfKnowledgeBase(tmp_path)
    kb.load()
    results = kb.search_structured(
        query="diffusion transformer",
        top_k=5,
        filters=SearchFilters(doc_type="concept", tags_any=["vision"], paper_id_contains="24"),
        sort_by="updated_at_desc",
    )

    assert len(results) == 1
    assert results[0].path.name == "concept-diffusion-new.md"
    assert "diffusion" in results[0].highlights
    assert "transformer" in results[0].highlights


def test_get_document_and_stats(tmp_path: Path) -> None:
    (tmp_path / "index.md").write_text(
        dump_okf_markdown(
            {"type": "index", "title": "Index"},
            "# Index\n\n- [LoRA](concept-lora.md)",
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

    kb = OkfKnowledgeBase(tmp_path)
    kb.load()

    doc = kb.get_document("concept-lora.md")
    assert doc.title == "LoRA"

    with pytest.raises(ValueError):
        kb.get_document("../concept-lora.md")
    with pytest.raises(FileNotFoundError):
        kb.get_document("missing.md")

    stats = kb.get_stats()
    assert stats["total_docs"] == 2
    assert stats["types_count"] == {"index": 1, "concept": 1}
    assert stats["has_index"] is True
    assert {"tag": "nlp", "count": 1} in stats["tags_count_top"]
