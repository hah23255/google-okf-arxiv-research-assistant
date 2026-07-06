#!/usr/bin/env python3
"""Simple local markdown link checker for project docs."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

DOC_FILES = [
    ROOT / "README.md",
    ROOT / "MASTER_GUIDE.md",
    *sorted((ROOT / "docs").glob("*.md")),
    ROOT / "RELEASE_CHECKLIST.md",
    ROOT / "CHANGELOG.md",
]


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def _normalize(target: str) -> str:
    target = target.split("#", maxsplit=1)[0]
    target = target.split("?", maxsplit=1)[0]
    return target.strip()


def main() -> int:
    failures: list[str] = []

    for doc_path in DOC_FILES:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8")

        for match in LINK_RE.finditer(text):
            raw_target = match.group(1).strip()
            if _is_external(raw_target):
                continue

            target = _normalize(raw_target)
            if not target:
                continue

            resolved = (doc_path.parent / target).resolve()
            if not resolved.exists():
                rel = doc_path.relative_to(ROOT)
                failures.append(f"{rel}: missing link target {raw_target}")

    if failures:
        print("Docs link check FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print("Docs link check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
