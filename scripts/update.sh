#!/usr/bin/env bash
set -euo pipefail

git pull
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d --build
docker compose -f infra/docker-compose.yml ps

# Smoke test (nécessite une API_KEY en env)
if [ -n "${API_KEY:-}" ]; then
  ./scripts/smoke_test.sh
else
  echo "INFO: API_KEY non défini -> smoke_test non exécuté (export API_KEY=... pour l'activer)"
fi
