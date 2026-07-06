# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-07-06

### Added

- Pure-OKF application baseline (producer, validator, lexical consumer, API).
- CLI commands for bundle production, validation, and query.
- API endpoints: `/health` and `/query`.
- Optional Streamlit frontend (`app.py`) that consumes existing API contracts.
- Additive CLI features: `search`, `show`, `stats`.
- New bulk corpus CLI feature: `produce-arxiv-bulk` for multi-category ArXiv ingestion with recency filter, dedupe, and global cap.
- Additive API features: `/search`, `/documents/{doc_name}`, `/stats`.
- Additive model-aware API feature: `/query-model` with local Ollama synthesis and deterministic fallback mode.
- Streamlit feature expansion: Search Explorer, citation preview, history replay/export, status metrics.
- Streamlit chat model mode: sidebar selector for `granite4.1:3b`, `qwen3.5:2b`, `nemotron-3-nano:4b`.
- Bulk build manifest artifact: `build_manifest.json`.
- Contract and behavior tests for OKF parser, validator, consumer, CLI/API flows.
- Frontend client tests for backend communication and error handling.
- CI workflow with tests, docs-link checks, frontend import smoke, and smoke checks.
- Zero-to-mastery tutorial artifacts in three formats:
  - `MASTER_GUIDE.md`
  - MkDocs-style multi-page `docs/`
  - Notebook-first tutorial in `tutorials/notebook_first_tutorial.ipynb`

### Compatibility

- No breaking changes are allowed for v1 CLI/API contracts.
