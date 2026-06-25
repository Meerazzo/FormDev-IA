# Documentation client technique — RAG documentaire

## Authentification

Toutes les routes RAG sont protégées par clé API :

```text
X-API-Key: <API_KEY>
```

Ne pas documenter de vraie clé API dans le dépôt. Les exemples utilisent la variable d'environnement locale `KEY`.

## Routes RAG exposées

| Méthode | Route | Usage |
| --- | --- | --- |
| GET | `/rag/health` | Vérifier l'état du module RAG et de Qdrant |
| POST | `/rag/sources/upload` | Importer un fichier RAG en synchrone |
| POST | `/rag/sources/upload-async` | Importer un fichier RAG en asynchrone |
| POST | `/rag/sources/url` | Créer une source URL sans ingestion immédiate |
| POST | `/rag/sources/url/ingest` | Importer une URL RAG en synchrone |
| POST | `/rag/sources/url/ingest-async` | Importer une URL RAG en asynchrone |
| GET | `/rag/corpora` | Lister les corpus RAG d'un client |
| GET | `/rag/corpora/{corpus_id}/sources` | Lister les sources d'un corpus |
| GET | `/rag/sources` | Lister les sources RAG |
| GET | `/rag/sources/{source_id}` | Récupérer une source RAG |
| PATCH | `/rag/sources/{source_id}` | Renommer ou mettre à jour les métadonnées d'une source |
| DELETE | `/rag/sources/{source_id}` | Supprimer une source et ses points Qdrant |
| POST | `/rag/sources/{source_id}/index` | Indexer une source en synchrone |
| POST | `/rag/sources/{source_id}/index-async` | Indexer une source en asynchrone |
| POST | `/rag/sources/{source_id}/reindex` | Réindexer une source en synchrone |
| POST | `/rag/sources/{source_id}/reindex-async` | Réindexer une source en asynchrone |
| POST | `/rag/corpora/resync` | Resynchroniser un corpus en synchrone |
| POST | `/rag/corpora/resync-async` | Resynchroniser un corpus en asynchrone |
| GET | `/rag/jobs/{job_id}` | Suivre un job RAG asynchrone |
| POST | `/rag/search` | Rechercher des passages documentaires |
| POST | `/rag/conversations` | Créer une conversation RAG |
| GET | `/rag/conversations` | Lister les conversations RAG |
| GET | `/rag/conversations/{conversation_id}` | Récupérer une conversation RAG |
| PATCH | `/rag/conversations/{conversation_id}` | Renommer une conversation RAG |
| DELETE | `/rag/conversations/{conversation_id}` | Supprimer une conversation RAG |
| GET | `/rag/conversations/{conversation_id}/messages` | Lister les messages d'une conversation |
| POST | `/rag/chat` | Poser une question au chatbot RAG en JSON |
| POST | `/rag/chat/stream` | Poser une question au chatbot RAG en streaming SSE |

## Variables de test locales

Adapter `API` au port exposé par Docker Compose et `KEY` à la clé définie dans `infra/.env`.

```bash
export API="http://localhost:<API_PORT>"
export KEY="<API_KEY>"
export CLIENT="client_demo"
export CORPUS="default"
```

## Health

```bash
curl -s "$API/rag/health" \
  -H "X-API-Key: $KEY" | jq
```

## Upload source synchrone

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

## Chat RAG JSON

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

## Chat RAG streaming SSE

La route streaming utilise `POST`, donc un frontend web doit la consommer avec `fetch()` plutôt qu'avec `EventSource`.

```bash
curl -N -X POST "$API/rag/chat/stream" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"$CLIENT\",
    \"corpus_id\": \"$CORPUS\",
    \"question\": \"Explique le rôle de Qdrant dans ce projet.\",
    \"top_k\": 3,
    \"temperature\": 0.2,
    \"max_tokens\": 512
  }"
```

Événements attendus :

```text
metadata
token
sources
done
error
```

## Jobs asynchrones

Les routes asynchrones retournent un `job_id` et un `rq_job_id`.

Suivre un job :

```bash
curl -s "$API/rag/jobs/$JOB_ID" \
  -H "X-API-Key: $KEY" | jq
```

Statuts possibles :

```text
pending
running
succeeded
failed
```

## Supprimer une source

```bash
curl -s -X DELETE "$API/rag/sources/$SOURCE_ID" \
  -H "X-API-Key: $KEY" | jq
```

La suppression marque la source en `deleted` côté PostgreSQL et supprime les points Qdrant associés.

## Réindexation

Lorsqu'une source est indexée ou réindexée, l'API supprime les anciens points Qdrant de cette source avant d'insérer les nouveaux chunks. Cela évite de conserver des chunks obsolètes si le nouveau découpage contient moins de chunks que l'ancien.

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
export QDRANT_PORT=$(docker compose --env-file infra/.env -f infra/docker-compose.yml port qdrant-dev 6333 | awk -F: '{print $NF}')
echo "$QDRANT_PORT"
```

Lister les collections :

```bash
curl -s "http://localhost:$QDRANT_PORT/collections" | jq
```

Compter les points d'une source :

```bash
curl -s -X POST "http://localhost:$QDRANT_PORT/collections/rag_chunks/points/count" \
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
| 404 | Source, conversation ou job introuvable |
| 429 | Rate limit atteint |
| 500 | Erreur d'indexation, Qdrant ou stockage |

## Bonnes pratiques d'intégration

- Toujours conserver le `source_id` retourné après upload.
- Toujours utiliser le même `client_id` et `corpus_id` entre upload, index, search et chat.
- Indexer une source avant de l'utiliser en recherche ou en chat.
- Préférer les routes asynchrones pour les fichiers volumineux ou les corpus importants.
- Supprimer les sources de test pour éviter d'accumuler des points Qdrant inutiles.
