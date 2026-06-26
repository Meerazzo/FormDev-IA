#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-infra/.env}"
ADMIN_PASSWORD="${1:-admin}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Fichier env introuvable: ${ENV_FILE}" >&2
  echo "Crée-le d'abord avec: cp infra/.env.example infra/.env" >&2
  exit 1
fi

upsert_env() {
  local key="$1"
  local value="$2"

  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

PASSWORD_SECRET="$(python - <<'PY'
import secrets
print(secrets.token_hex(48))
PY
)"

PASSWORD_HASH="$(python - <<PY
import hashlib
password = ${ADMIN_PASSWORD@Q}
print(hashlib.sha256(password.encode('utf-8')).hexdigest())
PY
)"

upsert_env "GRAYLOG_ENABLED" "true"
upsert_env "GRAYLOG_HTTP_PORT" "9000"
upsert_env "GRAYLOG_GELF_UDP_PORT" "12201"
upsert_env "GRAYLOG_HTTP_EXTERNAL_URI" "http://localhost:9000/"
upsert_env "GRAYLOG_PASSWORD_SECRET" "${PASSWORD_SECRET}"
upsert_env "GRAYLOG_ROOT_PASSWORD_SHA2" "${PASSWORD_HASH}"

echo "Graylog activé dans ${ENV_FILE}"
echo "Utilisateur Graylog: admin"
echo "Mot de passe Graylog: ${ADMIN_PASSWORD}"
echo
echo "Démarrage recommandé:"
echo "docker compose --profile observability --env-file infra/.env -f infra/docker-compose.yml up -d graylog"
echo "docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --force-recreate api-dev worker-survey-dev worker-rag-dev"
