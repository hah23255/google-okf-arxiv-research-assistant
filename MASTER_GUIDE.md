# Zero-to-Mastery Guide: OKF-First ArXiv Research Assistant

This guide takes you from first run to production-ready operation for an OKF-first system.

## 1. Learning outcomes

After this guide, you should be able to:

1. Explain why OKF documents are the system-of-record.
2. Build an OKF bundle from JSONL or ArXiv query input.
3. Validate bundle integrity and reserved filename constraints.
4. Query knowledge deterministically and interpret citations.
5. Operate API and Streamlit frontend safely.
6. Ship changes with CI + release checklist without breaking contracts.

## 2. Mental model

Data flow:

1. Ingest paper metadata.
2. Materialize `concept-*.md` docs + `index.md`.
3. Validate docs against schema-ish rules.
4. Tokenize local docs and rank lexical overlap.
5. Return evidence summary + citations.
6. Support structured retrieval via metadata filters and sort modes.
7. Optionally render answers/search/ops in Streamlit by calling backend APIs.

Non-goals in v1:

- Semantic embeddings
- Vector search
- External RAG pipelines

## 3. Environment setup

```bash
uv sync --extra dev
```

## 4. Build your first bundle

Create sample data:

```bash
cat > papers.jsonl << 'JSONL'
{"paper_id":"2106.09685","title":"LoRA: Low-Rank Adaptation of Large Language Models","abstract":"LoRA adapts large models by injecting trainable low-rank matrices.","url":"https://arxiv.org/abs/2106.09685","categories":["cs.CL","cs.LG"]}
JSONL
```

Produce:

```bash
uv run okf-assistant produce-jsonl --input papers.jsonl --output okf
```

Inspect output:

- `okf/index.md`
- `okf/concept-*.md`

## 5. Validate bundle

```bash
uv run okf-assistant validate --bundle okf
```

A valid bundle prints:

`Validation passed: okf`

## 6. Query bundle (CLI)

```bash
uv run okf-assistant query --bundle okf --question "What is LoRA?"
```

Expected sections:

- `Question:`
- `Evidence summary:`
- `Citations:`

Structured retrieval:

```bash
uv run okf-assistant search --bundle okf --query "low rank adaptation" --top-k 5
uv run okf-assistant show --bundle okf --doc-name concept-lora.md
uv run okf-assistant stats --bundle okf
```

Large corpus build:

```bash
uv run okf-assistant produce-arxiv-bulk --dry-run
uv run okf-assistant produce-arxiv-bulk --output okf_bulk
```

## 7. Run API

```bash
uv run uvicorn google_okf_arxiv_assistant.api:app --reload
```

Health:

```bash
curl -s http://127.0.0.1:8000/health
```

Query:

```bash
curl -s -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is LoRA?","top_k":5}'
```

Model-backed query:

```bash
curl -s -X POST http://127.0.0.1:8000/query-model \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is LoRA?","top_k":5,"model":"granite4.1:3b"}'
```

Structured search:

```bash
curl -s -X POST http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"diffusion transformer","top_k":10,"sort_by":"updated_at_desc","filters":{"doc_type":"concept","tags_any":["vision"]}}'
```

Document preview:

```bash
curl -s http://127.0.0.1:8000/documents/concept-lora.md
```

Bundle stats:

```bash
curl -s http://127.0.0.1:8000/stats
```

## 8. Run Streamlit frontend

```bash
uv run streamlit run app.py
```

Default backend URL is `http://127.0.0.1:8000`.
Override using sidebar settings, `OKF_API_BASE_URL`, or `.streamlit/secrets.toml`.
Tabs: `Chat`, `Search Explorer`, `History & Export`, `Status`.

## 9. Interface contracts you must not break

CLI contracts:

- `produce-jsonl --input --output`
- `produce-arxiv --query --limit --output`
- `validate --bundle`
- `query --bundle --question --top-k`

Additive CLI features:

- `search --bundle --query --top-k --doc-type --tag --paper-id --sort-by`
- `show --bundle --doc-name`
- `stats --bundle`
- `produce-arxiv-bulk --output --max-total --years-back --categories --per-category-limit --dry-run`

API contracts:

- `GET /health` -> status payload
- `POST /query` request/response field names and bounds

Additive API features:

- `POST /query-model` local model-backed query with fallback
- `POST /search` structured retrieval
- `GET /documents/{doc_name}` citation preview
- `GET /stats` bundle metrics

## 10. Troubleshooting playbook

- Bundle path errors: verify `--bundle` or `OKF_BUNDLE_DIR`.
- Parse failures: verify frontmatter fences and YAML mapping.
- Empty retrieval: ask a query using terms present in `title` or `summary`.
- Streamlit backend errors: verify FastAPI URL and health endpoint response.
- Model fallback warnings: verify Ollama is running and the selected model exists.
- Document preview 400: ensure `doc_name` is a plain filename.

## 11. CI and release workflow

Run local gates:

```bash
uv run python -m pytest -p no:cacheprovider
uv run python scripts/check_docs_links.py
bash scripts/ci_smoke.sh
```

Before release, follow [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## 12. Mastery exercises

1. Add 20 papers and compare retrieval quality for specific vs broad queries.
2. Create intentionally invalid docs and confirm validator catches each case.
3. Add one new document `type` and update tests without breaking old behavior.
4. Compare `/search` sort modes and explain the ranking differences.
5. Add a doc page in `docs/` and keep links passing in `check_docs_links.py`.
6. Launch Streamlit and validate citations match CLI/API outputs.

## 13. Learning tracks

- Multi-page docs: [docs/index.md](docs/index.md)
- Notebook-first lab: [tutorials/notebook_first_tutorial.ipynb](tutorials/notebook_first_tutorial.ipynb)
