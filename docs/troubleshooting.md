# Troubleshooting

## Bundle directory not found

- Set `--bundle` correctly for CLI.
- Set `OKF_BUNDLE_DIR` correctly for API runtime.

## Frontmatter parse failure

- Ensure docs start with `---`.
- Ensure frontmatter is valid YAML mapping.

## Validator failures for reserved files

- `index.md` must use `type: index`.
- `log.md` must use `type: log`.

## Empty query results

- Use terms that appear in title/summary text.

## Model query falls back to deterministic mode

- Ensure Ollama is running (`ollama list` should respond).
- Ensure selected model is installed (`granite4.1:3b`, `qwen3.5:2b`, or `nemotron-3-nano:4b`).
- Verify `OLLAMA_BASE_URL` and `OLLAMA_TIMEOUT_SECONDS` environment values.

## Bulk build fails on output directory

- `produce-arxiv-bulk` fails if `--output` already contains files.
- Use a fresh output path for each bulk build.

## Invalid document preview request

- `GET /documents/{doc_name}` requires a plain filename.
- Do not pass path segments like `../foo.md` or `dir/foo.md`.

## Unexpected `/search` order

- Verify `sort_by` (`score_desc`, `title_asc`, `updated_at_desc`).
- For `updated_at_desc`, ensure `updated_at` exists in frontmatter.
