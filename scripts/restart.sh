#!/usr/bin/env bash
set -euo pipefail
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
docker compose -f infra/docker-compose.yml ps
