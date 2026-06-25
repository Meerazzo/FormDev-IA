# Documentation client technique — RAG documentaire

## Routes principales

```text
GET    /rag/health
POST   /rag/sources/upload
POST   /rag/sources/{source_id}/index
POST   /rag/search
POST   /rag/chat
DELETE /rag/sources/{source_id}
```

## Authentification

```text
X-API-Key: <clé_api>
```

## Variables de test

```bash
export API="http://localhost:8081"
export KEY="FormdevINF26"
export CLIENT="client_demo"
export CORPUS="default"
```

## Health

```bash
curl -s "$API/rag/health" \
  -H "X-API-Key: $KEY" | jq
```

## Upload source

```bash
cat > /tmp/rag_test_source.txt <<'TXT'
FormDev IA propose un chatbot documentaire RAG.
Qdrant stocke les chunks vectorisés.
TXT

curl -s -X POST "$API/rag/sources/upload?client_id=$CLIENT&corpus_id=$CORPUS" \
  -H "X-API-Key: $KEY" \
  -F "file=@/tmp/rag_test_source.txt;type=text/plain" \
  | tee /tmp/rag_upload_response.json | jq
```

## Indexer une source

```bash
export SOURCE_ID=$(jq -r '.source_id' /tmp/rag_upload_response.json)

curl -s -X POST "$API/rag/sources/$SOURCE_ID/index" \
  -H "X-API-Key: $KEY" | jq
```

## Recherche vectorielle

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

## Chat RAG

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

## Supprimer une source

```bash
curl -s -X DELETE "$API/rag/sources/$SOURCE_ID" \
  -H "X-API-Key: $KEY" | jq
```

La suppression marque la source en `deleted` côté PostgreSQL et supprime les points Qdrant associés.

## Réindexation

Lorsqu'une source est indexée à nouveau, l'API supprime les anciens points Qdrant de cette source avant d'insérer les nouveaux chunks. Cela évite de conserver des chunks obsolètes si le nouveau découpage contient moins de chunks que l'ancien.

## Isolation documentaire

Chaque requête RAG doit fournir :

```text
client_id
corpus_id
```

Les recherches vectorielles sont filtrées sur ces deux champs pour éviter les mélanges entre clients ou corpus.

## Vérifier Qdrant

Trouver le port exposé :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml port qdrant-dev 6333
```

Lister les collections :

```bash
curl -s "http://localhost:<QDRANT_PORT>/collections" | jq
```

Compter les points d'une source :

```bash
curl -s -X POST "http://localhost:<QDRANT_PORT>/collections/rag_chunks/points/count" \
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

## Erreurs fréquentes

| Code | Cause probable |
| --- | --- |
| 401 | Clé API absente ou invalide |
| 400 | Source introuvable, chunks absents ou requête invalide |
| 429 | Rate limit atteint |
| 500 | Erreur d'indexation, Qdrant ou stockage |

## Bonnes pratiques d'intégration

- Toujours conserver le `source_id` retourné après upload.
- Toujours utiliser le même `client_id` et `corpus_id` entre upload, index, search et chat.
- Indexer une source avant de l'utiliser en recherche ou en chat.
- Supprimer les sources de test pour éviter d'accumuler des points Qdrant inutiles.
