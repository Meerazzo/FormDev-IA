#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-bench/results/vllm_metrics}"
INTERVAL="${INTERVAL:-2}"
CONTAINER="${CONTAINER:-infra-inference-1}"
PORT="${PORT:-8000}"

mkdir -p "$OUT_DIR"

while true; do
  ts=$(date +"%Y%m%d_%H%M%S")
  docker exec "$CONTAINER" curl -s "http://localhost:${PORT}/metrics" > "$OUT_DIR/metrics_${ts}.txt" || true
  sleep "$INTERVAL"
done