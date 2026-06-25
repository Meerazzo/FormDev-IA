# Architecture du module RAG documentaire

## Objectif

Le module RAG expose un chatbot documentaire multi-client pour FormDev.

Il permet à un CRM, un ERP ou un extranet client de poser des questions sur une base documentaire composée de fichiers PDF, DOCX, TXT ou d'URLs.

## Routes principales

```text
GET    /rag/health
POST   /rag/sources/upload
POST   /rag/sources/upload-async
POST   /rag/sources/url
POST   /rag/sources/url/ingest
POST   /rag/sources/url/ingest-async
GET    /rag/sources
GET    /rag/sources/{source_id}
PATCH  /rag/sources/{source_id}
DELETE /rag/sources/{source_id}
POST   /rag/sources/{source_id}/index
POST   /rag/search
POST   /rag/chat
POST   /rag/chat/stream
```

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

Route :

```text
POST /rag/sources/upload
```

Le fichier est :

1. sauvegardé ;
2. parsé ;
3. découpé en chunks ;
4. enregistré comme source en base ;
5. laissé en statut `pending` jusqu'à l'indexation.

### Indexation

Route :

```text
POST /rag/sources/{source_id}/index
```

L'indexation :

1. lit le fichier `.chunks.json` associé à la source ;
2. calcule les embeddings ;
3. supprime les anciens points Qdrant de cette source ;
4. insère les nouveaux chunks dans Qdrant ;
5. met la source en statut `indexed`.

Cette stratégie évite les chunks obsolètes lorsqu'une source est réindexée avec moins de chunks qu'avant.

### Suppression

Route :

```text
DELETE /rag/sources/{source_id}
```

La suppression :

1. supprime physiquement les points Qdrant associés à la source ;
2. marque la source en `deleted` en base PostgreSQL.

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
