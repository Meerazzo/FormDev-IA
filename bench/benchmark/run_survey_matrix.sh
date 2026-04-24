#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
API_KEY="${API_KEY:-}"
SCRIPT="${SCRIPT:-bench/benchmark/survey_benchmark.py}"
RESULTS_DIR="${RESULTS_DIR:-bench/results/survey}"
CASES="${CASES:-5:5 10:10 20:20 50:50}"

mkdir -p "$RESULTS_DIR"

for item in $CASES; do
  conc="${item%%:*}"
  total="${item##*:}"
  out="$RESULTS_DIR/survey_conc_${conc}_total_${total}.txt"
  echo "===== SURVEY CONCURRENCY=$conc TOTAL=$total ====="
  BASE_URL="$BASE_URL" API_KEY="$API_KEY" CONCURRENCY="$conc" TOTAL="$total" \
    python "$SCRIPT" | tee "$out"
done