#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8080/v1/chat}"
API_KEY="${API_KEY:-}"
MODEL_ID_PAYLOAD="${MODEL_ID_PAYLOAD:-${MODEL_ID:-}}"
REPEAT="${REPEAT:-3}"
TIMEOUT="${TIMEOUT:-180}"
PROMPTS="${PROMPTS:-bench/prompts.json}"
GPU_INTERVAL="${GPU_INTERVAL:-1}"

if [[ -z "${API_KEY}" ]]; then
  echo "ERROR: API_KEY is required (export API_KEY=...)" >&2
  exit 1
fi

# Create a run folder first, so GPU metrics and bench results go together
RUN_DIR="bench/results/$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$RUN_DIR"

echo "Run dir: $RUN_DIR"

# Start GPU monitor in background
GPU_CSV="$RUN_DIR/gpu_metrics.csv"
./scripts/gpu_watch.sh "$GPU_CSV" "$GPU_INTERVAL" &
GPU_PID=$!

# Ensure we stop the monitor even if bench fails
cleanup() {
  kill "$GPU_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Run the bench and force output into the same RUN_DIR
python3 scripts/bench_run.py \
  --api-url "${API_URL}" \
  --api-key "${API_KEY}" \
  --model "${MODEL_ID_PAYLOAD}" \
  --repeat "${REPEAT}" \
  --timeout "${TIMEOUT}" \
  --prompts "${PROMPTS}" \
  --outdir "$RUN_DIR"

echo "Bench done."
echo "Summary: $RUN_DIR/summary.json"
echo "GPU CSV:  $RUN_DIR/gpu_metrics.csv"