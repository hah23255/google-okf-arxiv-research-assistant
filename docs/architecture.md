# Architecture

OKF-first flow:

1. Producer writes markdown docs with frontmatter.
2. Validator enforces required keys and reserved filename rules.
3. Consumer tokenizes docs and ranks lexical overlap.
4. Consumer exposes structured search filters (`doc_type`, `tags_any`, `paper_id_contains`) and sort modes.
5. Bulk producer mode can fetch multi-category ArXiv corpora with recency filter + dedupe + global cap.
6. API supports deterministic query (`/query`) and additive model-backed query (`/query-model`) with fallback.
7. Bulk builds emit `build_manifest.json` for provenance and reproducibility.

No vector DB, embeddings, or RAG pipeline are used in v1.
