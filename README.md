# Google OKF ArXiv Research Assistant

An OKF-first ArXiv assistant that stores knowledge as markdown documents with YAML frontmatter
and answers questions using deterministic lexical retrieval plus optional local Ollama synthesis.

## Core scope (v1)

- No vector database
- No RAG pipeline
- No embedding models
- Retrieval always stays lexical over local OKF docs
- Optional additive local model synthesis via `/query-model`

## Prerequisites

- Python `>=3.11`
- `uv` installed

## Input schema (`produce-jsonl`)

Each line in the JSONL file must contain:

```json
{
  "paper_id": "2106.09685",
  "title": "LoRA: Low-Rank Adaptation of Large Language Models",
  "abstract": "LoRA adapts large models by injecting trainable low-rank matrices.",
  "url": "https://arxiv.org/abs/2106.09685",
  "categories": ["cs.CL", "cs.LG"]
}
```

`url` is optional. If missing, it defaults to `https://arxiv.org/abs/{paper_id}`.
`submitted_at` is optional but recommended for recency-aware bulk workflows.

## Quickstart

```bash
uv sync --extra dev
uv run okf-assistant produce-jsonl --input papers.jsonl --output okf
uv run okf-assistant validate --bundle okf
uv run okf-assistant query --bundle okf --question "What is LoRA?"
uv run okf-assistant produce-arxiv-bulk --dry-run
uv run okf-assistant produce-arxiv-bulk --output okf_bulk
uv run okf-assistant search --bundle okf --query "low rank adaptation" --top-k 5
uv run okf-assistant stats --bundle okf
uv run uvicorn google_okf_arxiv_assistant.api:app --reload
uv run streamlit run app.py
```

Model-backed query example (local Ollama):

```bash
curl -s -X POST http://127.0.0.1:8000/query-model \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is LoRA?","top_k":5,"model":"granite4.1:3b"}'
```

## Large corpus build (25k+ papers)

Default bulk command profile:

- Source: ArXiv only
- Categories: `cs.AI, cs.CL, cs.LG, cs.CV, stat.ML, cs.IR, eess.SP`
- Recency window: last 5 years
- Per-category fetch cap: 5000
- Global cap: 30000
- Output safety: fails if output directory is non-empty

Examples:

```bash
# Inspect planned corpus stats without writing docs
uv run okf-assistant produce-arxiv-bulk --dry-run

# Build large corpus to a new directory
uv run okf-assistant produce-arxiv-bulk --output okf_bulk

# Custom larger run
uv run okf-assistant produce-arxiv-bulk \
  --output okf_bulk_50k \
  --max-total 50000 \
  --years-back 5 \
  --categories "cs.AI,cs.CL,cs.LG,cs.CV,stat.ML,cs.IR,eess.SP" \
  --per-category-limit 8000
```

Bulk builds also write `build_manifest.json` with configuration and selection stats.

## Streamlit frontend

Streamlit is an additive UI layer that calls the existing FastAPI backend.

Backend terminal:

```bash
uv run uvicorn google_okf_arxiv_assistant.api:app --reload
```

Frontend terminal:

```bash
uv run streamlit run app.py
```

Configuration options for Streamlit:

- Sidebar `API Base URL`
- Environment variable: `OKF_API_BASE_URL`
- `.streamlit/secrets.toml` (`api_base_url`) using `.streamlit/secrets.toml.example`
- Built-in tabs for `Chat`, `Search Explorer`, `History & Export`, and `Status`
- Search presets, citation explorer, document preview, and export utilities
- Model-backed chat toggle and local model selector (`granite4.1:3b`, `qwen3.5:2b`, `nemotron-3-nano:4b`)

## Extended retrieval commands

```bash
# Structured lexical search with metadata filters
uv run okf-assistant search \
  --bundle okf \
  --query "diffusion transformer" \
  --doc-type concept \
  --tag vision \
  --paper-id 2401 \
  --sort-by updated_at_desc

# Inspect one citation/document by name
uv run okf-assistant show --bundle okf --doc-name concept-lora.md

# Bundle-level stats (JSON output)
uv run okf-assistant stats --bundle okf
```

## Expected command outputs

- `produce-jsonl`: logs file creation and writes `index.md` + `concept-*.md` files.
- `validate`: prints `Validation passed: <bundle_dir>` or per-file issues.
- `query`: prints:
  - `Question: ...`
  - `Evidence summary:`
  - `Citations: ...`

## API contract

- `GET /health` -> `{ "status": "ok" }`
- `POST /query` request:
  - `query: string` (min 3 chars)
  - `top_k: int` (1..20, default 5)
- `POST /query` response:
  - `answer: string`
  - `citations: string[]`
- `POST /query-model` request:
  - `query: string` (min 3 chars)
  - `top_k: int` (1..20, default 5)
  - `model: "granite4.1:3b" | "qwen3.5:2b" | "nemotron-3-nano:4b"`
- `POST /query-model` response:
  - `answer: string`
  - `citations: string[]`
  - `mode: "model" | "fallback"`
  - `model_used: string`
  - `warning: string | null`
- `POST /search` request:
  - `query: string` (min 3 chars)
  - `top_k: int` (1..50, default 10)
  - `filters?: { doc_type?: string, tags_any?: string[], paper_id_contains?: string }`
  - `sort_by: "score_desc" | "title_asc" | "updated_at_desc"`
- `POST /search` response:
  - `results: SearchResult[]` where each row includes `doc_name`, `title`, `doc_type`, `paper_id`, `tags`, `score`, `snippet`, `highlights`
- `GET /documents/{doc_name}` -> `{ doc_name, frontmatter, body }`
- `GET /stats` -> `{ total_docs, types_count, tags_count_top, has_index }`

## Compatibility promises

The project guarantees strict non-breaking compatibility for:

- CLI subcommands and flags:
  - `produce-jsonl --input --output`
  - `produce-arxiv --query --limit --output`
  - `validate --bundle`
  - `query --bundle --question --top-k`
- API endpoint shapes for `/health` and `/query`
- Model-aware endpoint is additive: `/query-model`

The project also exposes additive v1 commands/endpoints:

- CLI: `search`, `show`, `stats`, `produce-arxiv-bulk`
- API: `/search`, `/documents/{doc_name}`, `/stats`
- API: `/query-model`

Legacy contracts must remain unchanged even as additive features evolve.

## Common failure modes

- `Bundle directory not found`:
  - Fix `--bundle` path or `OKF_BUNDLE_DIR` env var.
- `Missing frontmatter fence` or parse failures:
  - Ensure markdown docs start with `---` YAML frontmatter.
- `index.md must declare frontmatter type=index`:
  - Ensure reserved filename/type pairing.
- Streamlit cannot reach backend:
  - Verify FastAPI is running and `API Base URL` is correct.
- Model mode returns fallback warnings:
  - Verify Ollama is running and model is installed (`ollama list`).
- Document preview returns 400:
  - Ensure doc name is a plain filename (no path segments).

## Diagnostics

```bash
uv run python -m pytest -p no:cacheprovider
uv run python scripts/check_docs_links.py
bash scripts/ci_smoke.sh
bash scripts/real_user_run.sh
```

## Learning docs

- Zero-to-mastery guide: [MASTER_GUIDE.md](MASTER_GUIDE.md)
- Multi-page tutorial docs: [docs/index.md](docs/index.md)
- Notebook-first path: [tutorials/notebook_first_tutorial.ipynb](tutorials/notebook_first_tutorial.ipynb)
- Release assets: [CHANGELOG.md](CHANGELOG.md), [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)

<p align="center">Made with ❤️ by Ahmad Mujtaba</p>
