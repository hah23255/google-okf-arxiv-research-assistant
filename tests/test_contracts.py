from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path
import tomllib

import pytest
from pydantic import ValidationError

from google_okf_arxiv_assistant import cli
from google_okf_arxiv_assistant.api import (
    QueryModelRequest,
    QueryModelResponse,
    QueryRequest,
    QueryResponse,
    SearchRequest,
    SearchResponse,
)
from google_okf_arxiv_assistant.okf import dump_okf_markdown


def _write_min_bundle(root: Path) -> None:
    (root / "index.md").write_text(
        dump_okf_markdown(
            {"type": "index", "title": "Index"},
            "# Index\n\n- [LoRA](concept-lora.md)",
        ),
        encoding="utf-8",
    )
    (root / "concept-lora.md").write_text(
        dump_okf_markdown(
            {
                "type": "concept",
                "title": "LoRA",
                "paper_id": "2106.09685",
                "tags": ["nlp", "finetuning"],
                "updated_at": "2026-07-06",
            },
            "# LoRA\n\nLow-rank adaptation for LLM fine-tuning.",
        ),
        encoding="utf-8",
    )


def test_cli_subcommand_contracts_stable() -> None:
    parser = cli._build_parser()
    subparser_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    choices = set(subparser_action.choices)
    assert {
        "produce-jsonl",
        "produce-arxiv",
        "validate",
        "query",
    }.issubset(choices)

    # Additive v1 extensions are allowed, but these new commands are now also contractual.
    assert {
        "search",
        "show",
        "stats",
        "produce-arxiv-bulk",
    }.issubset(choices)

    expected_legacy_flags = {
        "produce-jsonl": {"--input", "--output"},
        "produce-arxiv": {"--query", "--limit", "--output"},
        "validate": {"--bundle"},
        "query": {"--bundle", "--question", "--top-k"},
    }
    for command_name, expected_flags in expected_legacy_flags.items():
        subparser = subparser_action.choices[command_name]
        option_strings = {
            option
            for action in subparser._actions
            for option in action.option_strings
        }
        assert expected_flags.issubset(option_strings)


def test_cli_additive_command_flags_contract() -> None:
    parser = cli._build_parser()
    subparser_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    expected_additive_flags = {
        "search": {"--bundle", "--query", "--top-k", "--doc-type", "--tag", "--paper-id", "--sort-by"},
        "show": {"--bundle", "--doc-name"},
        "stats": {"--bundle"},
        "produce-arxiv-bulk": {
            "--output",
            "--max-total",
            "--years-back",
            "--categories",
            "--per-category-limit",
            "--dry-run",
        },
    }
    for command_name, expected_flags in expected_additive_flags.items():
        subparser = subparser_action.choices[command_name]
        option_strings = {
            option
            for action in subparser._actions
            for option in action.option_strings
        }
        assert expected_flags.issubset(option_strings)


def test_cli_validate_success_output_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_min_bundle(tmp_path)
    code = cli._run(Namespace(command="validate", bundle=tmp_path))
    out = capsys.readouterr().out

    assert code == 0
    assert out.startswith("Validation passed:")


def test_cli_query_output_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_min_bundle(tmp_path)
    code = cli._run(
        Namespace(
            command="query",
            bundle=tmp_path,
            question="What is LoRA?",
            top_k=3,
        )
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "Question: What is LoRA?" in out
    assert "Evidence summary:" in out
    assert "Citations:" in out


def test_cli_search_output_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_min_bundle(tmp_path)
    code = cli._run(
        Namespace(
            command="search",
            bundle=tmp_path,
            query="low rank adaptation",
            top_k=5,
            doc_type="",
            tag=[],
            paper_id="",
            sort_by="score_desc",
        )
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "[1]" in out
    assert "score=" in out
    assert "snippet=" in out


def test_cli_show_output_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_min_bundle(tmp_path)
    code = cli._run(Namespace(command="show", bundle=tmp_path, doc_name="concept-lora.md"))
    out = capsys.readouterr().out

    assert code == 0
    assert "Document: concept-lora.md" in out
    assert "Frontmatter:" in out
    assert "Body:" in out


def test_cli_stats_output_contract(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_min_bundle(tmp_path)
    code = cli._run(Namespace(command="stats", bundle=tmp_path))
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert payload["total_docs"] == 2
    assert payload["has_index"] is True


def test_cli_produce_arxiv_bulk_dry_run_output_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_records_from_arxiv_bulk(config):
        return [], {
            "selected_total": 0,
            "scanned_total": 0,
            "scanned_by_category": {"cs.AI": 0},
            "selected_by_category": {"cs.AI": 0},
            "recency_skipped": 0,
            "duplicate_skipped": 0,
            "cutoff_utc": "2021-01-01T00:00:00+00:00",
            "max_total": config.max_total,
            "reached_max_total": False,
        }

    monkeypatch.setattr(cli, "records_from_arxiv_bulk", fake_records_from_arxiv_bulk)

    code = cli._run(
        Namespace(
            command="produce-arxiv-bulk",
            output=tmp_path / "okf_bulk",
            max_total=100,
            years_back=5,
            categories="cs.AI,cs.CL",
            per_category_limit=100,
            dry_run=True,
        )
    )
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert payload["dry_run"] is True
    assert payload["config"]["max_total"] == 100
    assert payload["config"]["categories"] == ["cs.AI", "cs.CL"]


def test_api_request_response_schema_contract() -> None:
    req_schema = QueryRequest.model_json_schema()
    resp_schema = QueryResponse.model_json_schema()

    assert set(req_schema["properties"].keys()) == {"query", "top_k"}
    assert req_schema["properties"]["top_k"]["minimum"] == 1
    assert req_schema["properties"]["top_k"]["maximum"] == 20
    assert set(resp_schema["properties"].keys()) == {"answer", "citations"}


def test_api_search_request_response_schema_contract() -> None:
    req_schema = SearchRequest.model_json_schema()
    resp_schema = SearchResponse.model_json_schema()

    assert {"query", "top_k", "filters", "sort_by"}.issubset(req_schema["properties"].keys())
    assert req_schema["properties"]["top_k"]["minimum"] == 1
    assert req_schema["properties"]["top_k"]["maximum"] == 50
    assert set(req_schema["properties"]["sort_by"]["enum"]) == {
        "score_desc",
        "title_asc",
        "updated_at_desc",
    }
    assert "results" in resp_schema["properties"]


def test_api_query_model_request_response_schema_contract() -> None:
    req_schema = QueryModelRequest.model_json_schema()
    resp_schema = QueryModelResponse.model_json_schema()

    assert {"query", "top_k", "model"} == set(req_schema["properties"].keys())
    assert req_schema["properties"]["top_k"]["minimum"] == 1
    assert req_schema["properties"]["top_k"]["maximum"] == 20
    assert set(req_schema["properties"]["model"]["enum"]) == {
        "granite4.1:3b",
        "qwen3.5:2b",
        "nemotron-3-nano:4b",
    }
    assert {"answer", "citations", "mode", "model_used", "warning"} == set(resp_schema["properties"].keys())


def test_api_query_request_enforces_top_k_bounds() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(query="valid query", top_k=0)

    with pytest.raises(ValidationError):
        QueryRequest(query="valid query", top_k=21)


def test_pure_okf_dependency_contract() -> None:
    project_root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    deps = [dep.lower() for dep in data["project"]["dependencies"]]
    banned = ("faiss", "chromadb", "langchain", "llamaindex", "pinecone", "weaviate", "milvus")

    for blocked in banned:
        assert not any(blocked in dep for dep in deps), f"Disallowed dependency found: {blocked}"
