"""Utilities for reading/writing OKF-style markdown documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class OkfDocument:
    """A single OKF markdown document.

    Attributes:
        path: File path on disk.
        frontmatter: Parsed YAML frontmatter.
        body: Markdown body content.
    """

    path: Path
    frontmatter: dict[str, Any]
    body: str

    @property
    def title(self) -> str:
        """Return frontmatter title, if available."""
        title = self.frontmatter.get("title")
        return str(title) if title is not None else ""

    @property
    def doc_type(self) -> str:
        """Return frontmatter type, if available."""
        doc_type = self.frontmatter.get("type")
        return str(doc_type) if doc_type is not None else ""


def parse_okf_markdown(path: Path) -> OkfDocument:
    """Parse an OKF markdown file with YAML frontmatter.

    Args:
        path: Markdown file path.

    Returns:
        Parsed OkfDocument.

    Raises:
        ValueError: If frontmatter format is invalid.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Missing frontmatter fence in {path}")

    parts = text.split("\n---\n", maxsplit=1)
    if len(parts) != 2:
        raise ValueError(f"Could not parse frontmatter/body split in {path}")

    raw_frontmatter = parts[0].removeprefix("---\n")
    body = parts[1]

    parsed = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Frontmatter must be a mapping in {path}")

    return OkfDocument(path=path, frontmatter=parsed, body=body)


def dump_okf_markdown(frontmatter: dict[str, Any], body: str) -> str:
    """Render an OKF markdown document from frontmatter + body."""
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip()
    return f"---\n{yaml_text}\n---\n{body.rstrip()}\n"
