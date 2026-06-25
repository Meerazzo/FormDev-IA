#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${ROOT_DIR}/infra/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/infra/.env}"
PROJECT_NAME="${PROJECT_NAME:-infra}"

cd "${ROOT_DIR}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Commande manquante: $1" >&2
    exit 1
  }
}

require_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Fichier env introuvable: ${ENV_FILE}" >&2
    echo "Copie d'abord infra/.env.example vers infra/.env puis adapte les secrets." >&2
    exit 1
  fi
}

compose() {
  require_env_file
  require_cmd docker
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

load_env() {
  require_env_file
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

first_api_key() {
  if [[ -n "${API_KEY:-}" ]]; then
    printf "%s" "${API_KEY}"
    return
  fi

  if [[ -z "${API_KEYS:-}" ]]; then
    echo "API_KEY non défini et API_KEYS absent de ${ENV_FILE}" >&2
    exit 1
  fi

  printf "%s" "${API_KEYS}" | cut -d',' -f1 | cut -d':' -f2-
}

api_port() {
  printf "%s" "${API_PORT:-${API_DEV_PORT:-8081}}"
}

api_url() {
  printf "%s" "${API_URL:-http://localhost:$(api_port)}"
}

pretty_json() {
  if command -v jq >/dev/null 2>&1; then
    jq
  else
    cat
  fi
}

usage() {
  cat <<'EOF'
FormDev IA helper

Usage:
  bash scripts/formdevctl.sh <commande> [args]

Commandes principales:
  help                  Affiche cette aide
  config                Valide docker compose config
  services              Liste les services Compose
  ps                    Affiche l'état des conteneurs
  up                    Lance les services dev avec build
  up-no-build           Lance les services dev sans rebuild
  down                  Arrête les services dev
  restart <service>     Redémarre un service Compose
  restart-workers       Redémarre les workers Survey et RAG
  migrate               Applique les migrations Alembic dans api-dev
  smoke                 Lance scripts/smoke_test.sh avec la première API key de infra/.env
  health                Vérifie /health, /docs, /openapi.json et /rag/health

Logs:
  logs [service]        Suit les logs d'un service, ou tous les logs si aucun service
  logs-api              Suit les logs api-dev
  logs-workers          Suit les logs des workers Survey et RAG
  logs-rag              Suit les logs worker-rag-dev
  logs-survey           Suit les logs worker-survey-dev
  logs-inference        Suit les logs vLLM

Observabilité:
  up-observability      Lance les services du profil observability
  logs-graylog          Suit les logs Graylog

Debug:
  shell-api             Ouvre un shell dans infra-api-dev-1
  qdrant-collections    Liste les collections Qdrant via le port exposé

Variables optionnelles:
  ENV_FILE              Chemin du fichier .env, défaut: infra/.env
  COMPOSE_FILE          Chemin du docker-compose, défaut: infra/docker-compose.yml
  API_KEY               API key explicite pour smoke/health
  API_PORT              Port API local, défaut: API_DEV_PORT puis 8081
  API_URL               URL API explicite, défaut: http://localhost:$API_PORT
  CLIENT_ID             Client id pour smoke, défaut: formdevctl-smoke-client
  RAG_CORPUS_ID         Corpus id pour smoke, défaut: formdevctl-smoke-corpus

Note:
  Si Docker renvoie permission denied, exécute la commande depuis un shell root via su,
  ou ajoute ton utilisateur au groupe docker puis rouvre la session.
EOF
}

cmd_config() {
  local config_output
  config_output="$(mktemp -t formdev-compose-check-XXXXXX.yml)"
  compose config >"${config_output}"
  echo "Compose config OK: ${config_output}"
}

cmd_services() {
  compose config --services
}

cmd_ps() {
  compose ps
}

cmd_up() {
  compose up -d --build "$@"
}

cmd_up_no_build() {
  compose up -d --no-build "$@"
}

cmd_down() {
  compose down "$@"
}

cmd_restart() {
  if [[ $# -lt 1 ]]; then
    echo "Usage: bash scripts/formdevctl.sh restart <service>" >&2
    exit 1
  fi
  compose restart "$@"
}

cmd_restart_workers() {
  compose up -d --force-recreate --no-build worker-survey-dev worker-rag-dev
  compose ps worker-survey-dev worker-rag-dev
}

cmd_migrate() {
  compose exec api-dev alembic upgrade head
}

cmd_smoke() {
  require_cmd curl
  require_cmd jq
  load_env

  export API_KEY="$(first_api_key)"
  export API_PORT="$(api_port)"
  export CLIENT_ID="${CLIENT_ID:-formdevctl-smoke-client}"
  export RAG_CORPUS_ID="${RAG_CORPUS_ID:-formdevctl-smoke-corpus}"

  bash "${ROOT_DIR}/scripts/smoke_test.sh"
}

cmd_health() {
  require_cmd curl
  load_env

  local url
  local key
  url="$(api_url)"
  key="$(first_api_key)"

  echo "API URL: ${url}"

  echo "[1/4] /health"
  curl -fsS "${url}/health" | pretty_json

  echo "[2/4] /docs"
  curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "${url}/docs"

  echo "[3/4] /openapi.json"
  curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "${url}/openapi.json"

  echo "[4/4] /rag/health"
  curl -fsS "${url}/rag/health" -H "X-API-Key: ${key}" | pretty_json
}

cmd_logs() {
  compose logs -f "$@"
}

cmd_logs_api() {
  compose logs -f api-dev
}

cmd_logs_workers() {
  compose logs -f worker-survey-dev worker-rag-dev
}

cmd_logs_rag() {
  compose logs -f worker-rag-dev
}

cmd_logs_survey() {
  compose logs -f worker-survey-dev
}

cmd_logs_inference() {
  compose logs -f inference
}

cmd_up_observability() {
  require_env_file
  require_cmd docker
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" --profile observability up -d
}

cmd_logs_graylog() {
  compose logs -f graylog
}

cmd_shell_api() {
  compose exec api-dev bash
}

cmd_qdrant_collections() {
  require_cmd curl
  local port
  port="$(compose port qdrant-dev 6333 | awk -F: '{print $NF}')"
  if [[ -z "${port}" ]]; then
    echo "Impossible de trouver le port Qdrant exposé." >&2
    exit 1
  fi
  curl -fsS "http://localhost:${port}/collections" | pretty_json
}

main() {
  local cmd="${1:-help}"
  shift || true

  case "${cmd}" in
    help|-h|--help) usage ;;
    config) cmd_config "$@" ;;
    services) cmd_services "$@" ;;
    ps|status) cmd_ps "$@" ;;
    up) cmd_up "$@" ;;
    up-no-build) cmd_up_no_build "$@" ;;
    down) cmd_down "$@" ;;
    restart) cmd_restart "$@" ;;
    restart-workers) cmd_restart_workers "$@" ;;
    migrate) cmd_migrate "$@" ;;
    smoke) cmd_smoke "$@" ;;
    health) cmd_health "$@" ;;
    logs) cmd_logs "$@" ;;
    logs-api) cmd_logs_api "$@" ;;
    logs-workers) cmd_logs_workers "$@" ;;
    logs-rag) cmd_logs_rag "$@" ;;
    logs-survey) cmd_logs_survey "$@" ;;
    logs-inference) cmd_logs_inference "$@" ;;
    up-observability) cmd_up_observability "$@" ;;
    logs-graylog) cmd_logs_graylog "$@" ;;
    shell-api) cmd_shell_api "$@" ;;
    qdrant-collections) cmd_qdrant_collections "$@" ;;
    *)
      echo "Commande inconnue: ${cmd}" >&2
      echo >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
