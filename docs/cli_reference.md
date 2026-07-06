# CLI Reference

## Commands

- `produce-jsonl --input --output`
- `produce-arxiv --query --limit --output`
- `produce-arxiv-bulk --output --max-total --years-back --categories --per-category-limit --dry-run`
- `validate --bundle`
- `query --bundle --question --top-k`
- `search --bundle --query --top-k --doc-type --tag --paper-id --sort-by`
- `show --bundle --doc-name`
- `stats --bundle`

## Output contracts

- `validate`: prints `Validation passed: ...` on success.
- `query`: includes `Question`, `Evidence summary`, `Citations` sections.
- `search`: each result includes title/doc_name, score, metadata line, and snippet.
- `show`: includes `Document`, `Frontmatter`, and `Body` sections.
- `stats`: prints JSON with `total_docs`, `types_count`, `tags_count_top`, `has_index`.
- `produce-arxiv-bulk --dry-run`: prints JSON summary including selected counts and filter stats.
