# Documentation client technique — RAG documentaire

Cette page décrit le contrat d'intégration du module RAG pour un CRM ou un front documentaire.

## Authentification

Toutes les routes RAG sont protégées par clé API :

```text
X-API-Key: <API_KEY>
```

Ne pas documenter de vraie clé API dans le dépôt. Les exemples utilisent la variable d'environnement locale `KEY`.

## Principe d'intégration côté CRM

Cycle recommandé :

```text
1. Créer ou importer une source documentaire
2. Indexer la source, ou utiliser une route asynchrone qui délègue au worker
3. Stocker source_id, corpus_id et status côté CRM
4. Utiliser /rag/search pour afficher des extraits documentaires
5. Utiliser /rag/chat pour obtenir une réponse sourcée
6. Supprimer une source lorsqu'elle ne doit plus être utilisée
```

Les données sont isolées par :

```text
client_id
corpus_id
```

Un même client peut avoir plusieurs corpus, par exemple `default`, `formation_securite`, `catalogue_2026`.

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

```bash
export API="http://localhost:<API_PORT>"
export KEY="<API_KEY>"
export CLIENT="client_demo"
export CORPUS="default"
```

## Upload source synchrone

Entrée : `multipart/form-data`.

| Paramètre | Emplacement | Type | Obligatoire | Rôle |
| --- | --- | --- | --- | --- |
| `client_id` | query | string | oui | Client propriétaire de la source. |
| `corpus_id` | query | string | non | Corpus cible. Défaut : `default`. |
| `file` | form-data | file | oui | Fichier TXT, PDF ou DOCX. |

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

Sortie :

```json
{
  "source_id": "src_...",
  "client_id": "client_demo",
  "corpus_id": "default",
  "source_type": "txt",
  "source_name": "rag_test_source.txt",
  "status": "pending",
  "file_path": "/data/rag/.../rag_test_source.txt",
  "chunks_path": "/data/rag/.../rag_test_source.txt.chunks.json",
  "chunks_count": 1,
  "preview_chunks": [
    {
      "page": null,
      "chunk_index": 0,
      "text": "FormDev IA propose un chatbot documentaire RAG..."
    }
  ],
  "parser_metadata": {
    "parser": "txt",
    "encoding": "utf-8"
  }
}
```

Le CRM doit conserver `source_id`, `client_id`, `corpus_id`, `source_name` et `status`.

## Indexer une source

```bash
export SOURCE_ID=$(jq -r '.source_id' /tmp/rag_upload_response.json)

curl -s -X POST "$API/rag/sources/$SOURCE_ID/index" \
  -H "X-API-Key: $KEY" | jq
```

Sortie :

```json
{
  "source_id": "src_...",
  "client_id": "client_demo",
  "corpus_id": "default",
  "status": "indexed",
  "qdrant_collection": "rag_chunks",
  "chunks_indexed": 1
}
```

## Recherche vectorielle

Entrée JSON :

```json
{
  "client_id": "client_demo",
  "corpus_id": "default",
  "query": "Où sont stockés les chunks vectorisés ?",
  "top_k": 3,
  "score_threshold": 0.0
}
```

| Champ | Type | Obligatoire | Rôle |
| --- | --- | --- | --- |
| `client_id` | string | oui | Client propriétaire du corpus. |
| `corpus_id` | string | oui | Corpus à interroger. |
| `query` | string | oui | Question ou recherche utilisateur. |
| `top_k` | integer | non | Nombre maximum de chunks à retourner. |
| `score_threshold` | number/null | non | Score minimal de similarité. |

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

Sortie :

```json
{
  "client_id": "client_demo",
  "corpus_id": "default",
  "query": "Où sont stockés les chunks vectorisés ?",
  "results_count": 1,
  "results": [
    {
      "score": 0.42,
      "source_id": "src_...",
      "source_type": "txt",
      "source_name": "rag_test_source.txt",
      "page": null,
      "chunk_index": 0,
      "text": "Qdrant stocke les chunks vectorisés.",
      "metadata": {}
    }
  ]
}
```

## Chat RAG JSON

Entrée JSON :

```json
{
  "client_id": "client_demo",
  "corpus_id": "default",
  "conversation_id": null,
  "question": "Explique le rôle de Qdrant dans ce projet.",
  "top_k": 3,
  "score_threshold": null,
  "temperature": 0.2,
  "max_tokens": 512
}
```

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

Sortie :

```json
{
  "conversation_id": "rag_conv_...",
  "client_id": "client_demo",
  "corpus_id": "default",
  "question": "Explique le rôle de Qdrant dans ce projet.",
  "answer": "Qdrant stocke les chunks documentaires vectorisés...",
  "sources": [
    {
      "source_id": "src_...",
      "source_type": "txt",
      "source_name": "rag_test_source.txt",
      "page": null,
      "chunk_index": 0,
      "score": 0.68,
      "text": "Qdrant stocke les chunks vectorisés."
    }
  ],
  "used_chunks_count": 1,
  "retrieval_confidence": "high",
  "top_score": 0.68,
  "retrieval_candidates_count": 1,
  "filtered_chunks_count": 1,
  "metadata": {}
}
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

Événements possibles :

```text
metadata
token
sources
done
error
```

## Jobs asynchrones

Les routes asynchrones retournent un `job_id` et un `rq_job_id`.

```json
{
  "job_id": "rag_job_...",
  "rq_job_id": "...",
  "client_id": "client_demo",
  "corpus_id": "default",
  "source_id": "src_...",
  "job_type": "ingest",
  "status": "pending",
  "message": "Job d'ingestion RAG ajouté à la queue"
}
```

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

La suppression marque la source en `deleted` côté PostgreSQL, supprime les points Qdrant associés et nettoie les artefacts locaux si présents.

## Réindexation

Lorsqu'une source est indexée ou réindexée, l'API supprime les anciens points Qdrant de cette source avant d'insérer les nouveaux chunks. Cela évite de conserver des chunks obsolètes si le nouveau découpage contient moins de chunks que l'ancien.

## Bonnes pratiques CRM

- Toujours envoyer `client_id` et `corpus_id`.
- Stocker `source_id` après upload ou ingestion URL.
- Afficher `status` côté CRM pour que l'utilisateur voie si la source est `pending`, `indexed`, `error` ou `deleted`.
- Préférer les routes asynchrones pour les fichiers/URLs volumineux.
- Utiliser `/rag/search` pour du debug ou de l'affichage d'extraits.
- Utiliser `/rag/chat` pour une réponse finale prête à afficher.
- Stocker `conversation_id` si le CRM veut garder un historique conversationnel.
