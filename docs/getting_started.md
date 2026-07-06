# Getting Started

## Prerequisites

- Python >= 3.11
- `uv`

## Install

```bash
uv sync --extra dev
```

## Build bundle from JSONL

```bash
uv run okf-assistant produce-jsonl --input papers.jsonl --output okf
```

## Validate bundle

```bash
uv run okf-assistant validate --bundle okf
```

## Query bundle

```bash
uv run okf-assistant query --bundle okf --question "What is LoRA?"
```

## Model-backed query (optional, local Ollama)

```bash
uv run uvicorn google_okf_arxiv_assistant.api:app --reload
curl -s -X POST http://127.0.0.1:8000/query-model \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is LoRA?","top_k":5,"model":"granite4.1:3b"}'
```

## Structured search and document inspection

```bash
uv run okf-assistant search --bundle okf --query "low rank adaptation" --top-k 5
uv run okf-assistant show --bundle okf --doc-name concept-lora.md
uv run okf-assistant stats --bundle okf
```

## Large ArXiv build (optional)

```bash
uv run okf-assistant produce-arxiv-bulk --dry-run
uv run okf-assistant produce-arxiv-bulk --output okf_bulk
```

## Full real-user validation run

```bash
bash scripts/real_user_run.sh
```
