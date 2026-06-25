#!/usr/bin/env bash
set -euo pipefail

API_PORT="${API_PORT:-8080}"
API_URL="${API_URL:-http://localhost:${API_PORT}}"
MODEL_ID="${MODEL_ID:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
CLIENT_ID="${CLIENT_ID:-smoke-client}"
RAG_CORPUS_ID="${RAG_CORPUS_ID:-smoke-corpus}"

: "${API_KEY:?Set API_KEY before running smoke_test.sh}"

command -v curl >/dev/null || { echo "curl manquant" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq manquant" >&2; exit 1; }

echo "[1/9] Health"
curl -fsS "${API_URL}/health" | jq

echo "[2/9] Swagger"
curl -fsS "${API_URL}/docs" >/dev/null
echo "Swagger OK"

echo "[3/9] Chat"
CHAT_JSON="$(curl -fsS -X POST "${API_URL}/v1/chat" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${MODEL_ID}\",\"messages\":[{\"role\":\"user\",\"content\":\"Réponds uniquement avec : Chat OK\"}],\"max_tokens\":40,\"temperature\":0.2,\"top_p\":0.9,\"post_correction\":false}")"
echo "${CHAT_JSON}" | jq
echo "${CHAT_JSON}" | jq -e '.content | length > 0' >/dev/null

echo "[4/9] Surveys analyze"
SURVEY_JSON="$(curl -fsS -X POST "${API_URL}/surveys/analyze" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"questionnaires\":[{\"id\":1,\"availableCategories\":[{\"id\":10,\"label\":\"Satisfaction\",\"metadata\":{}},{\"id\":11,\"label\":\"Amélioration\",\"metadata\":{}}],\"questions\":[{\"id\":100,\"label\":\"Avis général ?\",\"type\":\"OPEN\",\"answers\":[{\"id\":2000,\"type\":\"FREE_TEXT\",\"label\":\"Le contenu était clair mais le rythme était parfois trop rapide.\",\"metadata\":{}}],\"metadata\":{}}],\"metadata\":{\"client_id\":\"${CLIENT_ID}\",\"source\":\"smoke_test\"}}]}")"
echo "${SURVEY_JSON}" | jq
PROCESSING_ID="$(echo "${SURVEY_JSON}" | jq -r '.processing_id')"
if [[ -z "${PROCESSING_ID}" || "${PROCESSING_ID}" == "null" ]]; then
  echo "Impossible de récupérer processing_id depuis la réponse Surveys" >&2
  exit 1
fi

echo "[5/9] Surveys processing"
SURVEY_STATUS="UNKNOWN"
for i in {1..20}; do
  PROCESSING_JSON="$(curl -fsS "${API_URL}/surveys/processings/${PROCESSING_ID}?client_id=${CLIENT_ID}" -H "X-API-Key: ${API_KEY}")"
  SURVEY_STATUS="$(echo "${PROCESSING_JSON}" | jq -r '.status')"
  echo "attempt ${i}: ${SURVEY_STATUS}"
  if [[ "${SURVEY_STATUS}" == "FINISHED" || "${SURVEY_STATUS}" == "FAILED" ]]; then
    echo "${PROCESSING_JSON}" | jq
    break
  fi
  sleep 3
done
if [[ "${SURVEY_STATUS}" != "FINISHED" ]]; then
  echo "Survey failed or did not finish: ${SURVEY_STATUS}" >&2
  exit 1
fi

echo "[6/9] RAG upload"
RAG_FILE="$(mktemp)"
SOURCE_ID=""
cat > "${RAG_FILE}" <<'TXT'
FormDev IA contient trois modules principaux.
Le module Chat répond via vLLM.
Le module Surveys analyse les questionnaires et stocke les feedbacks.
Le module RAG utilise Qdrant pour rechercher des chunks documentaires.
TXT
cleanup() {
  rm -f "${RAG_FILE}"
  if [[ -n "${SOURCE_ID:-}" && "${SOURCE_ID}" != "null" ]]; then
    curl -fsS -X DELETE "${API_URL}/rag/sources/${SOURCE_ID}" -H "X-API-Key: ${API_KEY}" >/dev/null || true
  fi
}
trap cleanup EXIT
UPLOAD_JSON="$(curl -fsS -X POST "${API_URL}/rag/sources/upload?client_id=${CLIENT_ID}&corpus_id=${RAG_CORPUS_ID}" -H "X-API-Key: ${API_KEY}" -F "file=@${RAG_FILE};type=text/plain")"
echo "${UPLOAD_JSON}" | jq
SOURCE_ID="$(echo "${UPLOAD_JSON}" | jq -r '.source_id')"
if [[ -z "${SOURCE_ID}" || "${SOURCE_ID}" == "null" ]]; then
  echo "Impossible de récupérer source_id depuis la réponse RAG upload" >&2
  exit 1
fi

echo "[7/9] RAG index"
curl -fsS -X POST "${API_URL}/rag/sources/${SOURCE_ID}/index" -H "X-API-Key: ${API_KEY}" | jq

echo "[8/9] RAG search"
SEARCH_JSON="$(curl -fsS -X POST "${API_URL}/rag/search" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"${CLIENT_ID}\",\"corpus_id\":\"${RAG_CORPUS_ID}\",\"query\":\"Quel module utilise Qdrant ?\",\"top_k\":3,\"score_threshold\":0.0}")"
echo "${SEARCH_JSON}" | jq
echo "${SEARCH_JSON}" | jq -e '.results_count >= 1' >/dev/null

echo "[9/9] RAG chat"
RAG_CHAT_JSON="$(curl -fsS -X POST "${API_URL}/rag/chat" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"${CLIENT_ID}\",\"corpus_id\":\"${RAG_CORPUS_ID}\",\"question\":\"Quels sont les trois modules principaux de FormDev IA ?\",\"top_k\":3,\"temperature\":0.2,\"max_tokens\":256}")"
echo "${RAG_CHAT_JSON}" | jq
echo "${RAG_CHAT_JSON}" | jq -e '.answer | length > 0' >/dev/null
echo "${RAG_CHAT_JSON}" | jq -e '.used_chunks_count >= 1' >/dev/null

echo "Global smoke test OK"
