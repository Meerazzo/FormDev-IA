#!/usr/bin/env bash
set -euo pipefail

API_KEY="${API_KEY:-}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ROOT_DIR="bench/results/run_${TIMESTAMP}"

mkdir -p "$ROOT_DIR"

GPU_PID=""
VLLM_PID=""
RQ_PID=""

cleanup() {
  echo "Stopping background collectors..."
  [ -n "$GPU_PID" ] && kill "$GPU_PID" 2>/dev/null || true
  [ -n "$VLLM_PID" ] && kill "$VLLM_PID" 2>/dev/null || true
  [ -n "$RQ_PID" ] && kill "$RQ_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "Results root: $ROOT_DIR"

bash bench/benchmark/capture_gpu.sh "$ROOT_DIR/gpu_metrics.csv" &
GPU_PID=$!

bash bench/benchmark/capture_vllm_metrics_docker.sh "$ROOT_DIR/vllm_metrics" &
VLLM_PID=$!

bash bench/benchmark/capture_rq_queue.sh "$ROOT_DIR/rq_queue.csv" &
RQ_PID=$!

API_KEY="$API_KEY" BASE_URL="$BASE_URL" RESULTS_DIR="$ROOT_DIR/chat" \
  bash bench/benchmark/run_chat_matrix.sh

API_KEY="$API_KEY" BASE_URL="$BASE_URL" RESULTS_DIR="$ROOT_DIR/survey" \
  bash bench/benchmark/run_survey_matrix.sh

API_KEY="$API_KEY" BASE_URL="$BASE_URL" RESULTS_DIR="$ROOT_DIR/mixed" \
  bash bench/benchmark/run_mixed_matrix.sh

python bench/benchmark/summarize_results.py | tee "$ROOT_DIR/summary.txt"

echo "Benchmark completed. Results stored in $ROOT_DIR"