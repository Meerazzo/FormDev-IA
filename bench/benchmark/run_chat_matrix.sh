#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
API_KEY="${API_KEY:-}"
DURATION="${DURATION:-1m}"
SCRIPT="${SCRIPT:-bench/benchmark/chat_benchmark_realistic.js}"
RESULTS_DIR="${RESULTS_DIR:-bench/results/chat}"
VUS_LIST="${VUS_LIST:-10 20 30 50 100}"

mkdir -p "$RESULTS_DIR"

for vus in $VUS_LIST; do
  out="$RESULTS_DIR/chat_vus_${vus}.txt"
  echo "===== CHAT VUS=$vus ====="
  k6 run "$SCRIPT" \
    -e BASE_URL="$BASE_URL" \
    -e API_KEY="$API_KEY" \
    -e VUS="$vus" \
    -e DURATION="$DURATION" | tee "$out"
done