# Compatibility Promises

This project follows strict non-breaking compatibility for v1.

Guaranteed stable:

- Legacy CLI command names and flags:
  - `produce-jsonl`, `produce-arxiv`, `validate`, `query`
- `/health` and `/query` endpoint field names and bounds.
- Core retrieval constraints (no vector DB, no RAG pipeline).

Additive frontend support:

- `app.py` is optional and calls existing backend APIs.
- Frontend additions must not change backend request/response schemas.

Additive v1 interfaces now include:

- CLI: `search`, `show`, `stats`, `produce-arxiv-bulk`
- API: `/search`, `/documents/{doc_name}`, `/stats`, `/query-model`

Any future additive features must preserve legacy contracts by default.
