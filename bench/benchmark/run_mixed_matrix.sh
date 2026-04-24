#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
API_KEY="${API_KEY:-}"
CHAT_SCRIPT="${CHAT_SCRIPT:-bench/benchmark/chat_benchmark_realistic.js}"
SURVEY_SCRIPT="${SURVEY_SCRIPT:-bench/benchmark/survey_benchmark.py}"
RESULTS_DIR="${RESULTS_DIR:-bench/results/mixed}"
CASES="${CASES:-10:5:10 20:5:10 30:10:20}"

mkdir -p "$RESULTS_DIR"

for item in $CASES; do
  chat_vus=$(echo "$item" | cut -d: -f1)
  survey_conc=$(echo "$item" | cut -d: -f2)
  survey_total=$(echo "$item" | cut -d: -f3)

  survey_out="$RESULTS_DIR/mixed_survey_chat_${chat_vus}_sc_${survey_conc}_st_${survey_total}.txt"
  chat_out="$RESULTS_DIR/mixed_chat_chat_${chat_vus}_sc_${survey_conc}_st_${survey_total}.txt"

  echo "===== MIXED CHAT_VUS=$chat_vus SURVEY_CONC=$survey_conc SURVEY_TOTAL=$survey_total ====="

  BASE_URL="$BASE_URL" API_KEY="$API_KEY" CONCURRENCY="$survey_conc" TOTAL="$survey_total" \
    python "$SURVEY_SCRIPT" > "$survey_out" 2>&1 &
  survey_pid=$!

  sleep 3

  k6 run "$CHAT_SCRIPT" \
    -e BASE_URL="$BASE_URL" \
    -e API_KEY="$API_KEY" \
    -e VUS="$chat_vus" \
    -e DURATION="2m" | tee "$chat_out"

  wait "$survey_pid" || true
done