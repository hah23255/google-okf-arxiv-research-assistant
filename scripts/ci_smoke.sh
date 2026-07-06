#!/usr/bin/env bash
set -euo pipefail

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/papers.jsonl" << 'JSONL'
{"paper_id":"2106.09685","title":"LoRA: Low-Rank Adaptation of Large Language Models","abstract":"LoRA adapts large models by injecting trainable low-rank matrices.","url":"https://arxiv.org/abs/2106.09685","categories":["cs.CL","cs.LG"]}
JSONL

uv run okf-assistant produce-jsonl --input "$TMP_DIR/papers.jsonl" --output "$TMP_DIR/okf"
uv run okf-assistant validate --bundle "$TMP_DIR/okf"
uv run okf-assistant query --bundle "$TMP_DIR/okf" --question "What is low rank adaptation?" > "$TMP_DIR/query.txt"

grep -q "Citations:" "$TMP_DIR/query.txt"
echo "Smoke checks passed"
