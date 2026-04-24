#!/usr/bin/env bash
set -euo pipefail

OUT_FILE="${1:-bench/results/gpu_metrics.csv}"

mkdir -p "$(dirname "$OUT_FILE")"

nvidia-smi \
  --query-gpu=timestamp,name,utilization.gpu,utilization.memory,memory.used,memory.total \
  --format=csv \
  -l 1 > "$OUT_FILE"