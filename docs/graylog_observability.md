# Graylog observability

Dernière mise à jour : 2026-06-26

## Objectif

Rendre Graylog exploitable pour suivre rapidement les erreurs, la latence, les modules Chat, Surveys et RAG, ainsi que les interactions IA et les opérations RAG.

Les logs ne contiennent pas de body brut, pas de prompt complet, pas de payload questionnaire et pas de secret.

## Activation locale

Depuis la racine du projet :

```bash
bash scripts/enable_graylog_dev.sh
```

Puis lancer Graylog :

```bash
docker compose --profile observability --env-file infra/.env -f infra/docker-compose.yml up -d graylog
```

Redémarrer ensuite les services applicatifs pour activer l'envoi GELF :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --force-recreate api-dev worker-survey-dev worker-rag-dev
```

Interface locale :

```text
http://localhost:9000
```

## Champs structurés principaux

Logs HTTP :

```text
event_type=http_request
service_name=formdev-api
app_env=dev|prod
request_id=<uuid>
client_id=<client ou ->
module=chat|surveys|rag|system
route_family=chat_gateway|surveys_analyze|surveys_processing|surveys_feedback|rag_sources|rag_search|rag_chat|rag_corpora|rag_jobs|rag_health|system
method=GET|POST|PATCH|DELETE
path=/...
status_code=200|400|500...
status_family=2xx|4xx|5xx
is_error=true|false
duration_ms=<float>
latency_bucket=lt_100ms|100_500ms|500ms_1s|1_3s|3_10s|gt_10s
```

Logs IA :

```text
event_type=ai_interaction
module=chat|surveys
feature=chat|survey_analysis...
endpoint=/v1/chat|/surveys/analyze...
pipeline_name=<pipeline>
model_requested=<model>
model_used=<model>
finish_reason=stop|length|...
prompt_tokens=<int>
completion_tokens=<int>
total_tokens=<int>
latency_ms=<float>
```

Logs RAG métier :

```text
event_type=rag_source_indexed
event_type=rag_source_index_failed
event_type=rag_search_completed
event_type=rag_source_deleted
event_type=rag_corpus_resynced
```

## Recherches Graylog utiles

Erreurs globales :

```text
service_name:formdev-api AND is_error:true
```

Erreurs serveur :

```text
service_name:formdev-api AND status_family:5xx
```

Latence forte :

```text
service_name:formdev-api AND duration_ms:>3000
```

Module Chat :

```text
service_name:formdev-api AND module:chat
```

Module Surveys :

```text
service_name:formdev-api AND module:surveys
```

Module RAG :

```text
service_name:formdev-api AND module:rag
```

Indexations RAG :

```text
event_type:rag_source_indexed OR event_type:rag_source_index_failed
```

Recherches RAG sans résultat :

```text
event_type:rag_search_completed AND results_count:0
```

Interactions IA coûteuses :

```text
event_type:ai_interaction AND total_tokens:>2000
```

Générations coupées :

```text
event_type:ai_interaction AND finish_reason:length
```

## Vues recommandées

Vue `FormDev - Overview` :

```text
- count par module
- count par status_family
- moyenne duration_ms par route_family
- top routes lentes
- count is_error:true par module
```

Vue `FormDev - AI Usage` :

```text
- count event_type=ai_interaction par module
- somme total_tokens par client_id
- moyenne latency_ms par pipeline_name
- count par finish_reason
- top error_type
```

Vue `FormDev - RAG` :

```text
- count rag_source_indexed
- count rag_source_index_failed
- moyenne chunks_indexed
- count rag_search_completed
- recherches avec results_count=0
- count rag_source_deleted
```

Vue `FormDev - Surveys` :

```text
- count /surveys/analyze
- count /surveys/processings par status_family
- count /surveys/feedback
- count ai_interaction où module:surveys
- somme total_tokens sur Surveys
```

## Validation rapide

```bash
set -a
source infra/.env
set +a

KEY="$(printf "%s" "$API_KEYS" | cut -d',' -f1 | cut -d':' -f2-)"

curl -fsS "http://localhost:${API_DEV_PORT}/health"
curl -fsS "http://localhost:${API_DEV_PORT}/rag/health" -H "X-API-Key: ${KEY}"
```

Puis chercher dans Graylog :

```text
service_name:formdev-api
```

On doit voir des logs `http_request` avec `module=system` puis `module=rag`.
