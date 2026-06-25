# Runbook — FormDev IA

## Objectif

Ce runbook décrit les commandes opérationnelles pour lancer, tester et dépanner les trois modules FormDev IA :

1. Chat IA — `/v1/chat`
2. Surveys — `/surveys/*`
3. RAG documentaire — `/rag/*`

## Préparer l'environnement

```bash
cp infra/.env.example infra/.env
```

Adapter ensuite les valeurs sensibles dans `infra/.env` :

```text
API_KEYS
POSTGRES_PASSWORD
MODEL_ID
VLLM_BASE_URL
```

Ne jamais commiter `infra/.env`.

## Lancer les services

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build
```

Vérifier :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml ps
```

Si l'utilisateur courant n'a pas accès à Docker :

```bash
su
# ou
sudo docker compose --env-file infra/.env -f infra/docker-compose.yml ps
```

## Appliquer les migrations

Trouver le conteneur API :

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep api
```

Puis :

```bash
docker exec -it infra-api-dev-1 alembic upgrade head
```

Adapter le nom du conteneur si nécessaire.

## Variables utiles pour les tests curl

Adapter le port et la clé API selon `infra/.env`.

```bash
export API="http://localhost:8081"
export KEY="FormdevINF26"
```

## Health API

```bash
curl -s "$API/health" | jq
```

## Health RAG

```bash
curl -s "$API/rag/health" \
  -H "X-API-Key: $KEY" | jq
```

Résultat attendu :

```json
{
  "status": "ok",
  "qdrant_available": true
}
```

## Tester Chat IA

```bash
curl -s -X POST "$API/v1/chat" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Reformule ce texte en français professionnel : Bonjour, je veux savoir si vous êtes disponible demain."
      }
    ],
    "temperature": 0.2,
    "top_p": 0.9,
    "max_tokens": 200,
    "post_correction": false
  }' | jq
```

## Tester Surveys

Créer une analyse :

```bash
curl -s -X POST "$API/surveys/analyze" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "questionnaires": [
      {
        "id": 1,
        "availableCategories": [
          {"id": 10, "label": "Satisfaction", "metadata": {}},
          {"id": 11, "label": "Amélioration", "metadata": {}}
        ],
        "questions": [
          {
            "id": 100,
            "label": "Avez-vous des suggestions ?",
            "type": "OPEN",
            "answers": [
              {
                "id": 2000,
                "type": "FREE_TEXT",
                "label": "Le contenu est intéressant mais il faudrait plus d'exemples pratiques.",
                "metadata": {}
              }
            ],
            "metadata": {}
          }
        ],
        "metadata": {
          "client_id": "client_demo"
        }
      }
    ]
  }' | tee /tmp/survey_analyze_response.json | jq
```

Récupérer le processing id :

```bash
export PROCESSING_ID=$(jq -r '.processing_id' /tmp/survey_analyze_response.json)
```

Suivre le traitement :

```bash
curl -s "$API/surveys/processings/$PROCESSING_ID?client_id=client_demo" \
  -H "X-API-Key: $KEY" | jq
```

Statuts possibles :

```text
RECEIVED
QUEUED
STARTED
FINISHED
FAILED
```

## Tester RAG

Créer un fichier :

```bash
cat > /tmp/rag_test_source.txt <<'TXT'
FormDev IA propose un chatbot documentaire RAG.
PostgreSQL stocke les sources.
Qdrant stocke les chunks vectorisés.
TXT
```

Variables :

```bash
export CLIENT="client_demo"
export CORPUS="default"
```

Upload :

```bash
curl -s -X POST "$API/rag/sources/upload?client_id=$CLIENT&corpus_id=$CORPUS" \
  -H "X-API-Key: $KEY" \
  -F "file=@/tmp/rag_test_source.txt;type=text/plain" \
  | tee /tmp/rag_upload_response.json | jq
```

Indexation :

```bash
export SOURCE_ID=$(jq -r '.source_id' /tmp/rag_upload_response.json)

curl -s -X POST "$API/rag/sources/$SOURCE_ID/index" \
  -H "X-API-Key: $KEY" | jq
```

Recherche :

```bash
curl -s -X POST "$API/rag/search" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"$CLIENT\",
    \"corpus_id\": \"$CORPUS\",
    \"query\": \"Où sont stockés les chunks vectorisés ?\",
    \"top_k\": 3,
    \"score_threshold\": 0.0
  }" | jq
```

Chat RAG :

```bash
curl -s -X POST "$API/rag/chat" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"$CLIENT\",
    \"corpus_id\": \"$CORPUS\",
    \"question\": \"Explique le rôle de Qdrant dans ce projet.\",
    \"top_k\": 3,
    \"temperature\": 0.2,
    \"max_tokens\": 512
  }" | jq
```

Suppression de la source :

```bash
curl -s -X DELETE "$API/rag/sources/$SOURCE_ID" \
  -H "X-API-Key: $KEY" | jq
```

## Vérifier Qdrant

Trouver le port exposé :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml port qdrant-dev 6333
```

Exemple :

```text
0.0.0.0:6335
```

Lister les collections :

```bash
curl -s "http://localhost:6335/collections" | jq
```

Compter les points RAG d'une source :

```bash
curl -s -X POST "http://localhost:6335/collections/rag_chunks/points/count" \
  -H "Content-Type: application/json" \
  -d "{
    \"exact\": true,
    \"filter\": {
      \"must\": [
        {\"key\": \"client_id\", \"match\": {\"value\": \"$CLIENT\"}},
        {\"key\": \"corpus_id\", \"match\": {\"value\": \"$CORPUS\"}},
        {\"key\": \"source_id\", \"match\": {\"value\": \"$SOURCE_ID\"}}
      ]
    }
  }" | jq
```

## Logs

API dev :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml logs -f api-dev
```

Worker Survey :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml logs -f survey-worker-dev
```

Worker RAG :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml logs -f rag-worker-dev
```

Qdrant :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml logs -f qdrant-dev
```

vLLM :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml logs -f inference
```

## Redémarrer un service

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml restart api-dev
```

## Problèmes fréquents

### Docker permission denied

Symptôme :

```text
permission denied while trying to connect to the Docker daemon socket
```

Solution temporaire :

```bash
su
```

Solution durable :

```bash
sudo usermod -aG docker $USER
```

Puis rouvrir la session.

### Qdrant collection introuvable sur localhost:6333

Vérifier le port réel :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml port qdrant-dev 6333
```

Ne pas supposer que Qdrant écoute forcément sur `localhost:6333`.

### vLLM indisponible

Vérifier :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml logs -f inference
```

Causes possibles :

- modèle Hugging Face gated ;
- VRAM insuffisante ;
- mauvais `MODEL_ID` ;
- serveur vLLM encore en démarrage.

### Surveys bloqué en QUEUED

Vérifier Redis et le worker Survey :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml logs -f redis
docker compose --env-file infra/.env -f infra/docker-compose.yml logs -f survey-worker-dev
```

### RAG source indexée mais aucun résultat

Vérifier :

- `client_id` identique entre upload, index et search ;
- `corpus_id` identique ;
- `chunks_indexed > 0` ;
- collection `rag_chunks` présente dans Qdrant.
