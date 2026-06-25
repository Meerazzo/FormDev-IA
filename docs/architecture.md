# Architecture globale — FormDev IA

## Objectif

FormDev IA expose une API FastAPI pour trois modules principaux :

1. **Chat IA** : génération, reformulation et transformation de texte via `/v1/chat`.
2. **Surveys** : analyse asynchrone de questionnaires via `/surveys/*`.
3. **RAG documentaire** : chatbot documentaire multi-client via `/rag/*`.

L'application repose sur une gateway FastAPI, un serveur d'inférence vLLM, PostgreSQL, Qdrant et Redis/RQ.

## Vue d'ensemble

```text
Clients / CRM / Front FormDev
        ↓
FastAPI
        ↓
+----------------------+----------------------+----------------------+
| Chat IA              | Surveys              | RAG documentaire     |
| /v1/chat             | /surveys/*           | /rag/*               |
+----------------------+----------------------+----------------------+
        ↓                      ↓                      ↓
      vLLM             PostgreSQL + Redis/RQ     PostgreSQL + Qdrant
        ↓                      ↓                      ↓
 Réponse texte          Résultat analyse        Réponse + sources
```

## Composants

| Composant | Rôle |
| --- | --- |
| FastAPI | Gateway HTTP, Swagger, validation, authentification par clé API |
| vLLM | Serveur d'inférence LLM compatible OpenAI |
| PostgreSQL | Stockage métier, jobs, sources, résultats, conversations |
| Qdrant | Mémoire vectorielle Surveys et chunks RAG |
| Redis/RQ | Files de traitement asynchrone |
| Docker Compose | Environnement de dev/prod local |

## Module Chat IA

Route exposée :

| Méthode | Route | Usage |
| --- | --- | --- |
| POST | `/v1/chat` | Génération, reformulation, synthèse ou correction via vLLM |

Usage :

- reformulation ;
- synthèse ;
- génération de texte ;
- enrichissement ;
- post-correction optionnelle.

Le module appelle vLLM via la gateway backend. L'authentification se fait par header `X-API-Key`.

Documentation complémentaire : [Documentation client — Chat IA](client-technique-chat.md).

## Module Surveys

Routes exposées :

| Méthode | Route | Usage |
| --- | --- | --- |
| POST | `/surveys/analyze` | Lancer une analyse asynchrone de questionnaires |
| GET | `/surveys/processings/{processing_id}` | Suivre un traitement et récupérer son résultat final |
| POST | `/surveys/feedback` | Enregistrer un feedback opérateur sur les points analysés |
| GET | `/surveys/feedback` | Lister les exemples de feedback/mémoire d'un client |

Flux :

```text
Client
  ↓ POST /surveys/analyze
FastAPI crée un processing_id
  ↓
Redis/RQ exécute le traitement
  ↓
vLLM analyse les réponses
  ↓
PostgreSQL stocke le résultat
  ↓
GET /surveys/processings/{processing_id}
  ↓
POST /surveys/feedback
  ↓
PostgreSQL + Qdrant mémorisent les corrections utiles
```

Documentation complémentaire : [Documentation client — Surveys](client-technique-surveys.md).

## Module RAG documentaire

Routes exposées :

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

Flux :

```text
Upload source
  ↓
Parsing + chunking
  ↓
Embeddings locaux
  ↓
Qdrant collection rag_chunks
  ↓
Recherche vectorielle filtrée client_id + corpus_id
  ↓
Prompt RAG
  ↓
vLLM
  ↓
Réponse + sources
```

Documentation complémentaire :

- [Documentation client — RAG documentaire](client-technique-rag.md)
- [Architecture RAG détaillée](rag_architecture.md)

## Isolation multi-client

L'isolation repose sur les champs métier suivants :

```text
client_id
corpus_id
source_id
```

Pour le RAG, les recherches Qdrant sont filtrées par `client_id` et `corpus_id`.

Pour Surveys, les exemples validés sont rattachés au client concerné.

## Cycle de vie Qdrant RAG

La stratégie actuelle est volontairement simple :

```text
Suppression source     → suppression physique des points Qdrant associés
Réindexation source    → suppression des anciens points, puis upsert des nouveaux chunks
Recherche RAG          → filtre client_id + corpus_id
```

Le RAG ne s'appuie pas sur un filtre d'activation logique côté Qdrant à ce stade. Ce mécanisme pourra être ajouté plus tard pour gérer l'historique, le versioning ou des suppressions logiques.

## Sécurité

Toutes les routes métier sont protégées par :

```text
X-API-Key
```

La configuration se fait via :

```text
API_KEYS
RATE_LIMIT_RPM
```

## Swagger

Swagger est disponible sur :

```text
http://localhost:<API_PORT>/docs
```

En dev Docker, le port dépend de `API_DEV_PORT` dans `infra/.env`.
