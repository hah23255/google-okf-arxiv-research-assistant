# API Reference

## `GET /health`

Response:

```json
{"status": "ok"}
```

## `POST /query`

Request:

```json
{"query":"What is LoRA?","top_k":5}
```

Response:

```json
{
  "answer": "Question: ...",
  "citations": ["concept-....md"]
}
```

Constraints:

- `query`: min length 3
- `top_k`: integer 1..20

## `POST /query-model`

Request:

```json
{"query":"What is LoRA?","top_k":5,"model":"granite4.1:3b"}
```

Response:

```json
{
  "answer": "LoRA adapts models ...\n\nCitations: concept-lora.md",
  "citations": ["concept-lora.md"],
  "mode": "model",
  "model_used": "granite4.1:3b",
  "warning": null
}
```

Fallback behavior:

- When Ollama/model inference fails, endpoint returns `mode="fallback"` with deterministic lexical answer.
- When retrieval has no hits, endpoint skips model call and returns deterministic fallback.

Constraints:

- `query`: min length 3
- `top_k`: integer 1..20
- `model`: `granite4.1:3b` | `qwen3.5:2b` | `nemotron-3-nano:4b`

## `POST /search`

Request:

```json
{
  "query": "diffusion transformer",
  "top_k": 10,
  "filters": {
    "doc_type": "concept",
    "tags_any": ["vision"],
    "paper_id_contains": "2401"
  },
  "sort_by": "updated_at_desc"
}
```

Response:

```json
{
  "results": [
    {
      "doc_name": "concept-dit.md",
      "title": "Diffusion Transformer",
      "doc_type": "concept",
      "paper_id": "2401.77777",
      "tags": ["vision", "diffusion"],
      "score": 0.77,
      "snippet": "Diffusion transformer for images.",
      "highlights": ["diffusion", "transformer"]
    }
  ]
}
```

Constraints:

- `query`: min length 3
- `top_k`: integer 1..50
- `sort_by`: `score_desc` | `title_asc` | `updated_at_desc`

## `GET /documents/{doc_name}`

Response:

```json
{
  "doc_name": "concept-lora.md",
  "frontmatter": {
    "type": "concept",
    "title": "LoRA"
  },
  "body": "# LoRA\n\nLow-rank adaptation..."
}
```

Notes:

- Returns `400` when `doc_name` is not a plain filename.
- Returns `404` when the document does not exist.

## `GET /stats`

Response:

```json
{
  "total_docs": 42,
  "types_count": {
    "index": 1,
    "concept": 41
  },
  "tags_count_top": [
    {"tag": "vision", "count": 11}
  ],
  "has_index": true
}
```
