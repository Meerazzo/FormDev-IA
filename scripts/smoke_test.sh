#!/usr/bin/env bash
set -euo pipefail

API_PORT="${API_PORT:-8080}"
API_KEY="${API_KEY:-FormdevINF26}"
MODEL_ID="${MODEL_ID:-Qwen/Qwen2.5-7B-Instruct}"

echo "[1/3] Health..."
curl -s "http://localhost:${API_PORT}/health"
echo

echo "[2/3] Chat..."
curl -s "http://localhost:${API_PORT}/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d "{
    \"model\": \"${MODEL_ID}\",
    \"messages\": [{\"role\":\"user\",\"content\":\"Dis bonjour en une phrase.\"}],
    \"max_tokens\": 60
  }" | head -n 40
echo

echo "[3/3] OK"