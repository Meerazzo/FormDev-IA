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

Route principale :

```text
POST /v1/chat
```

Usage :

- reformulation ;
- synthèse ;
- génération de texte ;
- enrichissement ;
- post-correction optionnelle.

Le module appelle vLLM via la gateway backend. L'authentification se fait par header `X-API-Key`.

## Module Surveys

Routes principales :

```text
POST /surveys/analyze
GET  /surveys/processings/{processing_id}
POST /surveys/feedback
GET  /surveys/feedback
```

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

## Module RAG documentaire

Routes principales :

```text
GET    /rag/health
POST   /rag/sources/upload
POST   /rag/sources/{source_id}/index
POST   /rag/search
POST   /rag/chat
DELETE /rag/sources/{source_id}
```

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
