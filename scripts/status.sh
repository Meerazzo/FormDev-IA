#!/usr/bin/env bash
set -euo pipefail
SERVICE="${1:-}"
if [ -n "$SERVICE" ]; then
  docker compose -f infra/docker-compose.yml ps "$SERVICE"
else
  docker compose -f infra/docker-compose.yml ps
fi
