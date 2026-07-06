#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

wait_http() {
  local url="$1"
  local timeout_secs="$2"
  local i
  for ((i = 1; i <= timeout_secs; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

require_cmd uv
require_cmd curl
require_cmd ollama

OLLAMA_MODEL_NAMES="$(ollama list | awk 'NR>1 {print $1}')"
for model in "granite4.1:3b" "qwen3.5:2b" "nemotron-3-nano:4b"; do
  if ! grep -Fxq "$model" <<<"$OLLAMA_MODEL_NAMES"; then
    echo "Required model is missing: ${model}" >&2
    exit 1
  fi
done

TMP_DIR="$(mktemp -d)"
LOG_DIR="$TMP_DIR/logs"
mkdir -p "$LOG_DIR"

BACKEND_PORT="${BACKEND_PORT:-8020}"
BACKEND_FAIL_PORT="${BACKEND_FAIL_PORT:-8021}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8520}"

BACKEND_PID=""
BACKEND_FAIL_PID=""
STREAMLIT_PID=""
KEEP_REAL_RUN_ARTIFACTS="${KEEP_REAL_RUN_ARTIFACTS:-0}"

cleanup() {
  if [[ -n "$STREAMLIT_PID" ]]; then kill "$STREAMLIT_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "$BACKEND_FAIL_PID" ]]; then kill "$BACKEND_FAIL_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "$BACKEND_PID" ]]; then kill "$BACKEND_PID" >/dev/null 2>&1 || true; fi
  if [[ "$KEEP_REAL_RUN_ARTIFACTS" != "1" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

cat > "$TMP_DIR/papers.jsonl" << 'JSONL'
{"paper_id":"2106.09685","title":"LoRA: Low-Rank Adaptation of Large Language Models","abstract":"LoRA adapts large models by injecting trainable low-rank matrices.","url":"https://arxiv.org/abs/2106.09685","categories":["cs.CL","cs.LG"]}
{"paper_id":"2401.77777","title":"Diffusion Transformer","abstract":"Diffusion transformer architectures improve image generation.","url":"https://arxiv.org/abs/2401.77777","categories":["cs.CV"]}
JSONL

echo "[1/8] Building OKF bundle for real-user run..."
uv run okf-assistant produce-jsonl --input "$TMP_DIR/papers.jsonl" --output "$TMP_DIR/okf"
uv run okf-assistant validate --bundle "$TMP_DIR/okf"

echo "[2/8] Starting primary backend..."
OKF_BUNDLE_DIR="$TMP_DIR/okf" \
OLLAMA_BASE_URL="http://127.0.0.1:11434" \
uv run uvicorn google_okf_arxiv_assistant.api:app \
  --host 127.0.0.1 --port "$BACKEND_PORT" \
  > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
wait_http "http://127.0.0.1:${BACKEND_PORT}/health" 60

echo "[3/8] Starting Streamlit app..."
OKF_API_BASE_URL="http://127.0.0.1:${BACKEND_PORT}" \
uv run streamlit run app.py \
  --server.headless true \
  --server.port "$STREAMLIT_PORT" \
  --browser.gatherUsageStats false \
  > "$LOG_DIR/streamlit.log" 2>&1 &
STREAMLIT_PID=$!
wait_http "http://127.0.0.1:${STREAMLIT_PORT}" 90

echo "[4/8] Running model-backed query with granite4.1:3b..."
curl -fsS -X POST "http://127.0.0.1:${BACKEND_PORT}/query-model" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is LoRA?","top_k":5,"model":"granite4.1:3b"}' \
  > "$TMP_DIR/query_model.json"

uv run python - << 'PY' "$TMP_DIR/query_model.json"
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["mode"] == "model", payload
assert payload["model_used"] == "granite4.1:3b", payload
assert isinstance(payload["answer"], str) and payload["answer"].strip(), payload
assert isinstance(payload["citations"], list) and payload["citations"], payload
print("Model-backed query OK")
PY

echo "[4b] Running model-backed query with qwen3.5:2b..."
curl -fsS -X POST "http://127.0.0.1:${BACKEND_PORT}/query-model" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is diffusion transformer?","top_k":5,"model":"qwen3.5:2b"}' \
  > "$TMP_DIR/query_model_qwen.json"

uv run python - << 'PY' "$TMP_DIR/query_model_qwen.json"
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["mode"] == "model", payload
assert payload["model_used"] == "qwen3.5:2b", payload
assert isinstance(payload["answer"], str) and payload["answer"].strip(), payload
print("Qwen model-backed query OK")
PY

echo "[5/8] Running search/document/stats real API paths..."
curl -fsS -X POST "http://127.0.0.1:${BACKEND_PORT}/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"diffusion transformer","top_k":10,"sort_by":"score_desc"}' \
  > "$TMP_DIR/search.json"

uv run python - << 'PY' "$TMP_DIR/search.json"
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert isinstance(payload.get("results"), list), payload
assert payload["results"], payload
print("Search endpoint OK")
PY

FIRST_DOC="$(uv run python - << 'PY' "$TMP_DIR/search.json"
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["results"][0]["doc_name"])
PY
)"

curl -fsS "http://127.0.0.1:${BACKEND_PORT}/documents/${FIRST_DOC}" > "$TMP_DIR/document.json"
curl -fsS "http://127.0.0.1:${BACKEND_PORT}/stats" > "$TMP_DIR/stats.json"

uv run python - << 'PY' "$TMP_DIR/document.json" "$TMP_DIR/stats.json"
import json
import pathlib
import sys

doc_payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
stats_payload = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
assert isinstance(doc_payload.get("body"), str) and doc_payload["body"].strip(), doc_payload
assert isinstance(stats_payload.get("total_docs"), int) and stats_payload["total_docs"] >= 1, stats_payload
print("Document + stats endpoints OK")
PY

echo "[6/8] Validating fallback mode with forced Ollama failure backend..."
OKF_BUNDLE_DIR="$TMP_DIR/okf" \
OLLAMA_BASE_URL="http://127.0.0.1:1" \
uv run uvicorn google_okf_arxiv_assistant.api:app \
  --host 127.0.0.1 --port "$BACKEND_FAIL_PORT" \
  > "$LOG_DIR/backend_fallback.log" 2>&1 &
BACKEND_FAIL_PID=$!
wait_http "http://127.0.0.1:${BACKEND_FAIL_PORT}/health" 60

curl -fsS -X POST "http://127.0.0.1:${BACKEND_FAIL_PORT}/query-model" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is LoRA?","top_k":5,"model":"granite4.1:3b"}' \
  > "$TMP_DIR/query_fallback.json"

uv run python - << 'PY' "$TMP_DIR/query_fallback.json"
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["mode"] == "fallback", payload
assert isinstance(payload.get("warning"), str) and payload["warning"].strip(), payload
assert isinstance(payload.get("citations"), list), payload
print("Fallback mode OK")
PY

echo "[7/8] Checking Streamlit root content..."
curl -fsSI "http://127.0.0.1:${STREAMLIT_PORT}" > "$TMP_DIR/streamlit_headers.txt"
curl -fsS "http://127.0.0.1:${STREAMLIT_PORT}" > "$TMP_DIR/streamlit_home.html"
grep -Eqi '^HTTP/.* 200' "$TMP_DIR/streamlit_headers.txt"
test -s "$TMP_DIR/streamlit_home.html"

echo "[8/8] Real run complete."
echo "Artifacts:"
echo "  Backend logs: $LOG_DIR/backend.log"
echo "  Streamlit logs: $LOG_DIR/streamlit.log"
echo "  Primary model response: $TMP_DIR/query_model.json"
echo "  Secondary model response: $TMP_DIR/query_model_qwen.json"
echo "  Fallback response: $TMP_DIR/query_fallback.json"
if [[ "$KEEP_REAL_RUN_ARTIFACTS" != "1" ]]; then
  echo "  (Set KEEP_REAL_RUN_ARTIFACTS=1 to preserve these files after script exit.)"
fi
