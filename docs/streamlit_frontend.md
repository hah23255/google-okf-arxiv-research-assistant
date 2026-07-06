# Streamlit Frontend

The frontend is an additive UI that calls existing FastAPI endpoints.

## Run

1. Start backend:

```bash
uv run uvicorn google_okf_arxiv_assistant.api:app --reload
```

2. Start frontend:

```bash
uv run streamlit run app.py
```

## Behavior

- Uses `st.chat_input` and `st.chat_message`.
- Supports deterministic (`POST /query`) and model-backed (`POST /query-model`) chat paths.
- Sidebar provides local model selector:
  - `granite4.1:3b`
  - `qwen3.5:2b`
  - `nemotron-3-nano:4b`
- Renders `answer`, `citations`, and model metadata (`mode`, `model_used`, `warning`).
- Includes `Search Explorer` for `/search` with filters and sort options.
- Supports citation-driven document preview via `GET /documents/{doc_name}`.
- Includes `Status` tab for backend health and `/stats` metrics.
- Includes `History & Export` tab for chat/search replay and JSON/Markdown export.

## Configuration

Priority order:

1. Sidebar `API Base URL`
2. `st.secrets["api_base_url"]` from `.streamlit/secrets.toml`
3. `OKF_API_BASE_URL`
4. Default `http://127.0.0.1:8000`

## Non-breaking guarantee

Frontend is additive only: it does not modify legacy `/query` behavior or lexical retrieval logic.
