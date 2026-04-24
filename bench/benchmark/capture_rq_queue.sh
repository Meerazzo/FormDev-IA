#!/usr/bin/env bash
set -euo pipefail

OUT_FILE="${1:-bench/results/rq_queue.csv}"
INTERVAL="${INTERVAL:-2}"
CONTAINER="${CONTAINER:-infra-redis-1}"
QUEUE_KEY="${QUEUE_KEY:-rq:queue:survey}"

mkdir -p "$(dirname "$OUT_FILE")"
echo "timestamp,queue_length" > "$OUT_FILE"

while true; do
  ts=$(date +"%Y-%m-%d %H:%M:%S")
  qlen=$(docker exec "$CONTAINER" redis-cli LLEN "$QUEUE_KEY" 2>/dev/null || echo "")
  echo "$ts,$qlen" >> "$OUT_FILE"
  sleep "$INTERVAL"
done