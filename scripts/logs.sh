#!/usr/bin/env bash
set -euo pipefail
SERVICE="${1:-api}"
docker compose -f infra/docker-compose.yml logs -f --tail=100 "$SERVICE"
