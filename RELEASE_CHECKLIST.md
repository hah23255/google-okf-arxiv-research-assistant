# Release Checklist

## Pre-release checks

- [ ] `uv sync --extra dev`
- [ ] `uv run python -m pytest -p no:cacheprovider`
- [ ] `uv run python scripts/check_docs_links.py`
- [ ] `bash scripts/ci_smoke.sh`
- [ ] `bash scripts/real_user_run.sh`
- [ ] `uv run python -c "import streamlit; import app"`
- [ ] README, docs, and guide links verified
- [ ] Compatibility promises still true (CLI and API)

## Versioning and notes

- [ ] Update `CHANGELOG.md`
- [ ] Bump version in `pyproject.toml` (if applicable)
- [ ] Tag release

## Post-release verification

- [ ] Re-run smoke flow in clean env
- [ ] Verify `/health` and `/query` behavior in deployed runtime
- [ ] Verify `/query-model` model and fallback behavior in deployed runtime
- [ ] Verify `/search`, `/documents/{doc_name}`, `/stats` behavior in deployed runtime
- [ ] Verify Streamlit frontend can reach backend and show citations
