#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-infra/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Fichier env introuvable: ${ENV_FILE}" >&2
  echo "Crée-le d'abord avec: cp infra/.env.example infra/.env" >&2
  exit 1
fi

if grep -q '^SURVEY_PURGE_AFTER_FEEDBACK=' "${ENV_FILE}"; then
  sed -i 's/^SURVEY_PURGE_AFTER_FEEDBACK=.*/SURVEY_PURGE_AFTER_FEEDBACK=true/' "${ENV_FILE}"
else
  printf '\nSURVEY_PURGE_AFTER_FEEDBACK=true\n' >> "${ENV_FILE}"
fi

echo "SURVEY_PURGE_AFTER_FEEDBACK=true dans ${ENV_FILE}"
echo "Redémarre ensuite api-dev et worker-survey-dev pour appliquer la configuration."
