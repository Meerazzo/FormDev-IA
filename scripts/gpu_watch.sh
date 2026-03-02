#!/usr/bin/env bash
set -euo pipefail

OUTFILE="${1:-bench/results/gpu_metrics.csv}"
INTERVAL="${2:-1}"

mkdir -p "$(dirname "$OUTFILE")"

# CSV header
echo "timestamp,gpu_index,name,util_gpu_pct,util_mem_pct,mem_used_mib,mem_total_mib,power_w,temp_c" > "$OUTFILE"

while true; do
  # timestamp ISO-like
  TS="$(date '+%Y-%m-%d %H:%M:%S')"

  nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,temperature.gpu \
    --format=csv,noheader,nounits | while IFS=',' read -r idx name ug um mu mt pw tc; do
      # trim spaces
      idx="$(echo "$idx" | xargs)"
      name="$(echo "$name" | xargs)"
      ug="$(echo "$ug" | xargs)"
      um="$(echo "$um" | xargs)"
      mu="$(echo "$mu" | xargs)"
      mt="$(echo "$mt" | xargs)"
      pw="$(echo "$pw" | xargs)"
      tc="$(echo "$tc" | xargs)"
      echo "$TS,$idx,$name,$ug,$um,$mu,$mt,$pw,$tc"
    done >> "$OUTFILE"

  sleep "$INTERVAL"
done