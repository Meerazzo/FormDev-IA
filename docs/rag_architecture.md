# Architecture du module RAG documentaire

## Objectif

Le module RAG expose un chatbot documentaire multi-client pour FormDev.

Il permet à un CRM, un ERP ou un extranet client de poser des questions sur une base documentaire composée de fichiers PDF, DOCX, TXT ou d'URLs.

## Routes exposées

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

## Architecture

```text
Client / CRM / Extranet
        ↓
FastAPI /rag/*
        ↓
PostgreSQL : sources, corpus, conversations, jobs
        ↓
Parsing + chunking
        ↓
Embeddings locaux
        ↓
Qdrant : collection rag_chunks
        ↓
Recherche vectorielle filtrée
        ↓
Prompt RAG
        ↓
vLLM
        ↓
Réponse + sources
```

## Collection Qdrant

Collection utilisée :

```text
rag_chunks
```

Payload principal :

```json
{
  "client_id": "client_demo",
  "corpus_id": "default",
  "source_id": "src_123",
  "source_type": "pdf",
  "source_name": "guide.pdf",
  "page": 4,
  "chunk_index": 12,
  "text": "...",
  "metadata": {}
}
```

## Isolation documentaire

Les recherches RAG sont filtrées par :

```text
client_id + corpus_id
```

Cela évite qu'un client récupère des documents appartenant à un autre client ou à un autre corpus.

## Cycle de vie des sources

### Upload

Routes :

```text
POST /rag/sources/upload
POST /rag/sources/upload-async
POST /rag/sources/url/ingest
POST /rag/sources/url/ingest-async
```

Une source importée est sauvegardée, parsée, découpée en chunks et enregistrée en base. Elle doit ensuite être indexée pour être utilisée par la recherche ou le chat.

### Indexation

Routes :

```text
POST /rag/sources/{source_id}/index
POST /rag/sources/{source_id}/index-async
```

L'indexation :

1. lit le fichier `.chunks.json` associé à la source ;
2. calcule les embeddings ;
3. supprime les anciens points Qdrant de cette source ;
4. insère les nouveaux chunks dans Qdrant ;
5. met la source en statut `indexed`.

Cette stratégie évite les chunks obsolètes lorsqu'une source est réindexée avec moins de chunks qu'avant.

### Réindexation et resynchronisation

Routes :

```text
POST /rag/sources/{source_id}/reindex
POST /rag/sources/{source_id}/reindex-async
POST /rag/corpora/resync
POST /rag/corpora/resync-async
GET  /rag/jobs/{job_id}
```

Les routes asynchrones créent un job RAG suivi via `/rag/jobs/{job_id}`.

### Suppression

Route :

```text
DELETE /rag/sources/{source_id}
```

La suppression :

1. supprime physiquement les points Qdrant associés à la source ;
2. marque la source en `deleted` en base PostgreSQL.

## Chat et conversations

Le chat RAG peut être utilisé directement via `/rag/chat` ou en streaming via `/rag/chat/stream`.

Les conversations permettent de conserver l'historique côté backend : création, liste, consultation, renommage, suppression et lecture des messages.

## Note sur le versioning documentaire

Le RAG n'utilise pas de filtre d'activation logique côté Qdrant pour les chunks documentaires à ce stade.

La stratégie retenue pour la livraison est volontairement simple :

```text
suppression physique des points Qdrant
```

Un mécanisme d'activation logique pourra être ajouté plus tard si FormDev souhaite gérer :

- versioning documentaire ;
- rollback ;
- historique de sources ;
- désactivation temporaire sans suppression physique.
