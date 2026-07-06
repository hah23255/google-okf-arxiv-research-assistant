"""CLI entrypoint for producer, validator, search, and local querying."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from google_okf_arxiv_assistant.consumer import OkfKnowledgeBase, SearchFilters, answer_from_hits
from google_okf_arxiv_assistant.producer import (
    DEFAULT_BULK_CATEGORIES,
    ArxivBulkConfig,
    bulk_build_manifest,
    records_from_arxiv_query,
    records_from_arxiv_bulk,
    records_from_jsonl,
    write_build_manifest,
    write_okf_bundle,
)
from google_okf_arxiv_assistant.validator import validate_bundle


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Google OKF ArXiv research assistant")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs")

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_jsonl = subparsers.add_parser("produce-jsonl", help="Build OKF bundle from JSONL input")
    p_jsonl.add_argument("--input", type=Path, required=True, help="JSONL file path")
    p_jsonl.add_argument("--output", type=Path, default=Path("okf"), help="Output bundle dir")

    p_arxiv = subparsers.add_parser("produce-arxiv", help="Build OKF bundle from ArXiv query")
    p_arxiv.add_argument("--query", type=str, required=True, help="ArXiv search query")
    p_arxiv.add_argument("--limit", type=int, default=100, help="Maximum papers to fetch")
    p_arxiv.add_argument("--output", type=Path, default=Path("okf"), help="Output bundle dir")

    p_arxiv_bulk = subparsers.add_parser(
        "produce-arxiv-bulk",
        help="Build a large OKF bundle from multiple ArXiv categories",
    )
    p_arxiv_bulk.add_argument("--output", type=Path, default=Path("okf_bulk"), help="Output bundle dir")
    p_arxiv_bulk.add_argument("--max-total", type=int, default=30000, help="Global maximum papers")
    p_arxiv_bulk.add_argument("--years-back", type=int, default=5, help="Recency window in years")
    p_arxiv_bulk.add_argument(
        "--categories",
        type=str,
        default=",".join(DEFAULT_BULK_CATEGORIES),
        help="Comma-separated ArXiv categories (e.g. cs.AI,cs.CL,cs.LG)",
    )
    p_arxiv_bulk.add_argument(
        "--per-category-limit",
        type=int,
        default=5000,
        help="Maximum candidates fetched per category",
    )
    p_arxiv_bulk.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and select records, print stats, but do not write files",
    )

    p_validate = subparsers.add_parser("validate", help="Validate an OKF bundle")
    p_validate.add_argument("--bundle", type=Path, default=Path("okf"), help="Bundle dir")

    p_query = subparsers.add_parser("query", help="Run local lexical query against bundle")
    p_query.add_argument("--bundle", type=Path, default=Path("okf"), help="Bundle dir")
    p_query.add_argument("--question", type=str, required=True, help="Question text")
    p_query.add_argument("--top-k", type=int, default=5, help="Number of documents to return")

    p_search = subparsers.add_parser("search", help="Run structured search with filters")
    p_search.add_argument("--bundle", type=Path, default=Path("okf"), help="Bundle dir")
    p_search.add_argument("--query", type=str, required=True, help="Search query")
    p_search.add_argument("--top-k", type=int, default=10, help="Number of documents to return")
    p_search.add_argument("--doc-type", type=str, default="", help="Filter by document type")
    p_search.add_argument("--tag", action="append", default=[], help="Filter by tag (repeatable)")
    p_search.add_argument("--paper-id", type=str, default="", help="Filter by paper_id substring")
    p_search.add_argument(
        "--sort-by",
        type=str,
        choices=["score_desc", "title_asc", "updated_at_desc"],
        default="score_desc",
        help="Sort mode",
    )

    p_show = subparsers.add_parser("show", help="Show full document contents by filename")
    p_show.add_argument("--bundle", type=Path, default=Path("okf"), help="Bundle dir")
    p_show.add_argument("--doc-name", type=str, required=True, help="Document filename (e.g. concept-foo.md)")

    p_stats = subparsers.add_parser("stats", help="Show bundle-level stats")
    p_stats.add_argument("--bundle", type=Path, default=Path("okf"), help="Bundle dir")

    return parser


def _run(args: argparse.Namespace) -> int:
    if args.command == "produce-jsonl":
        records = records_from_jsonl(args.input)
        files = write_okf_bundle(records=records, output_dir=args.output)
        logging.info("Created %s files", len(files))
        return 0

    if args.command == "produce-arxiv":
        records = records_from_arxiv_query(query=args.query, limit=args.limit)
        files = write_okf_bundle(records=records, output_dir=args.output)
        logging.info("Created %s files", len(files))
        return 0

    if args.command == "produce-arxiv-bulk":
        categories = [part.strip() for part in args.categories.split(",") if part.strip()]
        config = ArxivBulkConfig(
            categories=categories,
            per_category_limit=int(args.per_category_limit),
            max_total=int(args.max_total),
            years_back=int(args.years_back),
        )
        records, stats = records_from_arxiv_bulk(config=config)
        summary_payload = {
            "selected_total": len(records),
            "output_dir": str(args.output),
            "config": {
                "categories": config.categories,
                "per_category_limit": config.per_category_limit,
                "max_total": config.max_total,
                "years_back": config.years_back,
            },
            "stats": stats,
            "dry_run": bool(args.dry_run),
        }

        if args.dry_run:
            print(json.dumps(summary_payload, indent=2, sort_keys=True))
            return 0

        files = write_okf_bundle(
            records=records,
            output_dir=args.output,
            fail_if_non_empty=True,
        )
        manifest = bulk_build_manifest(
            config=config,
            selection_stats=stats,
            output_dir=args.output,
        )
        manifest_path = write_build_manifest(args.output, manifest)
        logging.info("Created %s markdown files and manifest %s", len(files), manifest_path.name)
        return 0

    if args.command == "validate":
        issues = validate_bundle(args.bundle)
        if issues:
            for issue in issues:
                print(f"{issue.path}: {issue.message}")
            return 1
        print(f"Validation passed: {args.bundle}")
        return 0

    if args.command == "query":
        kb = OkfKnowledgeBase(args.bundle)
        kb.load()
        hits = kb.search(query=args.question, top_k=args.top_k)
        print(answer_from_hits(args.question, hits))
        return 0

    if args.command == "search":
        kb = OkfKnowledgeBase(args.bundle)
        kb.load()
        filters = SearchFilters(
            doc_type=args.doc_type.strip() or None,
            tags_any=[tag for tag in args.tag if str(tag).strip()] or None,
            paper_id_contains=args.paper_id.strip() or None,
        )
        results = kb.search_structured(
            query=args.query,
            top_k=args.top_k,
            filters=filters,
            sort_by=args.sort_by,
        )
        if not results:
            print("No results.")
            return 0

        for idx, item in enumerate(results, start=1):
            print(f"[{idx}] {item.title} ({item.path.name}) score={item.score:.4f}")
            print(
                "  type="
                f"{item.doc_type or 'n/a'} paper_id={item.paper_id or 'n/a'} "
                f"tags={','.join(item.tags) if item.tags else 'n/a'}"
            )
            if item.highlights:
                print("  highlights=" + ", ".join(item.highlights))
            print("  snippet=" + item.snippet)
        return 0

    if args.command == "show":
        kb = OkfKnowledgeBase(args.bundle)
        kb.load()
        try:
            doc = kb.get_document(args.doc_name)
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

        print(f"Document: {doc.path.name}")
        print("Frontmatter:")
        print(json.dumps(doc.frontmatter, indent=2, sort_keys=True))
        print("Body:")
        print(doc.body.rstrip())
        return 0

    if args.command == "stats":
        kb = OkfKnowledgeBase(args.bundle)
        kb.load()
        print(json.dumps(kb.get_stats(), indent=2, sort_keys=True))
        return 0

    raise RuntimeError(f"Unknown command: {args.command}")


def main() -> None:
    """CLI main entrypoint."""
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)
    code = _run(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
