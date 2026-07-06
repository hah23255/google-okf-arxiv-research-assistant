from __future__ import annotations

from pathlib import Path

from google_okf_arxiv_assistant.okf import dump_okf_markdown, parse_okf_markdown
from google_okf_arxiv_assistant.validator import validate_bundle


def test_okf_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "concept-test.md"
    frontmatter = {"type": "concept", "title": "Test Concept"}
    body = "# Test Concept\n\ncontent"
    path.write_text(dump_okf_markdown(frontmatter, body), encoding="utf-8")

    doc = parse_okf_markdown(path)
    assert doc.doc_type == "concept"
    assert doc.title == "Test Concept"
    assert "content" in doc.body


def test_validator_catches_missing_type(tmp_path: Path) -> None:
    bad_doc = tmp_path / "index.md"
    bad_doc.write_text(
        dump_okf_markdown({"title": "Index"}, "# Index"),
        encoding="utf-8",
    )

    issues = validate_bundle(tmp_path)
    assert any("Missing required frontmatter key: type" in issue.message for issue in issues)


def test_validator_catches_missing_title(tmp_path: Path) -> None:
    bad_doc = tmp_path / "index.md"
    bad_doc.write_text(
        dump_okf_markdown({"type": "index"}, "# Index"),
        encoding="utf-8",
    )

    issues = validate_bundle(tmp_path)
    assert any("Missing required frontmatter key: title" in issue.message for issue in issues)


def test_validator_enforces_reserved_index_filename_type(tmp_path: Path) -> None:
    bad_doc = tmp_path / "index.md"
    bad_doc.write_text(
        dump_okf_markdown({"type": "concept", "title": "Wrong Index"}, "# Wrong"),
        encoding="utf-8",
    )

    issues = validate_bundle(tmp_path)
    assert any("index.md must declare frontmatter type=index" in issue.message for issue in issues)
