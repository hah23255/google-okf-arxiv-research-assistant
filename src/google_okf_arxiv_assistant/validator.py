"""Validator for OKF bundle structure and document-level constraints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from google_okf_arxiv_assistant.okf import parse_okf_markdown

ALLOWED_TYPES = {
    "concept",
    "index",
    "log",
    "reference",
    "decision",
    "process",
}


@dataclass(slots=True)
class ValidationIssue:
    """Single validation issue."""

    path: Path
    message: str


def _check_reserved_filename(path: Path, doc_type: str) -> str | None:
    if path.name == "index.md" and doc_type != "index":
        return "index.md must declare frontmatter type=index"
    if path.name == "log.md" and doc_type != "log":
        return "log.md must declare frontmatter type=log"
    return None


def validate_bundle(bundle_dir: Path) -> list[ValidationIssue]:
    """Validate a bundle and return all detected issues."""
    issues: list[ValidationIssue] = []

    markdown_files = sorted(bundle_dir.glob("*.md"))
    if not markdown_files:
        issues.append(ValidationIssue(path=bundle_dir, message="No markdown documents found"))
        return issues

    for path in markdown_files:
        try:
            doc = parse_okf_markdown(path)
        except Exception as exc:
            issues.append(ValidationIssue(path=path, message=f"Parse failure: {exc}"))
            continue

        doc_type = str(doc.frontmatter.get("type", "")).strip()
        title = str(doc.frontmatter.get("title", "")).strip()

        if not doc_type:
            issues.append(ValidationIssue(path=path, message="Missing required frontmatter key: type"))
        elif doc_type not in ALLOWED_TYPES:
            issues.append(
                ValidationIssue(
                    path=path,
                    message=f"Invalid type={doc_type!r}; expected one of {sorted(ALLOWED_TYPES)}",
                )
            )

        if not title:
            issues.append(ValidationIssue(path=path, message="Missing required frontmatter key: title"))

        reserved_issue = _check_reserved_filename(path, doc_type)
        if reserved_issue:
            issues.append(ValidationIssue(path=path, message=reserved_issue))

    if not (bundle_dir / "index.md").exists():
        issues.append(ValidationIssue(path=bundle_dir, message="Bundle should include index.md"))

    return issues
