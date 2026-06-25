# FormDev IA

API d’inférence, d’analyse de questionnaires et de chatbot documentaire pour FormDev.

Le projet fournit trois briques principales :

- **Projet 1 — RAG documentaire** : un chatbot documentaire multi-client (`/rag/*`) avec ingestion de sources, indexation Qdrant, recherche vectorielle et réponses sourcées.
- **Projet 2 — Chat IA** : une route de génération / transformation de texte (`/v1/chat`) via vLLM.
- **Projet 3 — Surveys** : un pipeline d’analyse de questionnaires de satisfaction (`/surveys/*`) avec traitement asynchrone, segmentation en points, classification sentiment/catégorie, feedback opérateur et mémoire vectorielle par client.

Pour aller plus loin, les détails d'architecture, d'exploitation et d'intégration client sont dans le dossier [`docs/`](docs/).

---

## Sommaire

- [Vue d’ensemble](#vue-densemble)
- [Documentation technique](#documentation-technique)
- [Architecture](#architecture)
- [Technologies](#technologies)
- [Structure du projet](#structure-du-projet)
- [Démarrage rapide](#démarrage-rapide)
- [Configuration](#configuration)
- [API exposée](#api-exposée)
- [Projet 1 — RAG documentaire](#projet-1--rag-documentaire)
- [Projet 2 — Chat IA](#projet-2--chat-ia)
- [Projet 3 — Surveys](#projet-3--surveys)
- [Base de données](#base-de-données)
- [Mémoire vectorielle Qdrant](#mémoire-vectorielle-qdrant)
- [Sécurité](#sécurité)

---

## Vue d’ensemble

### Projet 1 — RAG documentaire

Le module `/rag/*` permet d’importer des sources documentaires, de les découper en chunks, de les indexer dans Qdrant, puis de répondre à des questions à partir des documents du client.

Fonctions principales :

- ingestion de fichiers TXT, PDF, DOCX ;
- ingestion d’URLs ;
- indexation vectorielle dans Qdrant ;
- recherche documentaire filtrée par `client_id` et `corpus_id` ;
- chat RAG JSON et streaming SSE ;
- conversations RAG ;
- jobs asynchrones d'upload, indexation, réindexation et resynchronisation ;
- suppression de source avec suppression des points Qdrant associés.

Documentation complémentaire : [Documentation client — RAG documentaire](docs/client-technique-rag.md) et [Architecture RAG détaillée](docs/rag_architecture.md).

### Projet 2 — Chat IA

La route `/v1/chat` permet d’utiliser un modèle servi par vLLM pour des usages de rédaction en français :

- reformulation ;
- synthèse ;
- enrichissement ;
- génération guidée ;
- correction optionnelle en seconde passe.

L’API prend en charge :

- l’authentification par clé API ;
- le rate limiting ;
- l’injection d’un prompt système backend ;
- une post-correction optionnelle par seconde inférence.

Documentation complémentaire : [Documentation client — Chat IA](docs/client-technique-chat.md).

### Projet 3 — Surveys

La route `/surveys/analyze` lance l’analyse asynchrone d’un ou plusieurs questionnaires de satisfaction.

Le pipeline réalise :

1. l’enregistrement d’un traitement ;
2. l’exécution en arrière-plan via Redis/RQ ;
3. la lecture des questionnaires client ;
4. la segmentation des réponses en points ;
5. la classification sentiment / catégorie ;
6. le stockage du résultat final ;
7. la relecture opérateur via `/surveys/feedback` ;
8. l’alimentation de la mémoire vectorielle Qdrant pour améliorer les classifications futures.

Documentation complémentaire : [Documentation client — Surveys](docs/client-technique-surveys.md).

---

## Documentation technique

| Document | Contenu |
| --- | --- |
| [Architecture globale](docs/architecture.md) | Vue d'ensemble des modules Chat, Surveys et RAG, composants et flux |
| [Runbook opérationnel](docs/runbook.md) | Lancement Docker, migrations, tests curl, logs et dépannage |
| [Documentation client — Chat IA](docs/client-technique-chat.md) | Contrat d'intégration de `/v1/chat` |
| [Documentation client — Surveys](docs/client-technique-surveys.md) | Contrat d'intégration de `/surveys/*` |
| [Documentation client — RAG documentaire](docs/client-technique-rag.md) | Contrat d'intégration complet de `/rag/*` |
| [Architecture RAG détaillée](docs/rag_architecture.md) | Cycle de vie des sources RAG, Qdrant, réindexation et conversations |
| [Checklist de livraison finale](docs/final_delivery_checklist.md) | Suivi de la passe finale de nettoyage/livraison |

---

## Architecture

Le projet repose sur cinq composants :

- **FastAPI** : gateway HTTP, validation, Swagger, sécurité ;
- **vLLM** : serveur d’inférence LLM compatible OpenAI ;
- **PostgreSQL** : stockage métier, jobs, sources, résultats et conversations ;
- **Qdrant** : mémoire vectorielle Survey et RAG ;
- **Redis/RQ** : files de traitement asynchrone.

Flux simplifié :

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

Pour le détail complet : [Architecture globale](docs/architecture.md).

---

## Technologies

- Python 3.12
- FastAPI
- vLLM
- PostgreSQL 16
- SQLAlchemy
- Alembic
- Qdrant
- FastEmbed
- Redis / RQ
- Docker / Docker Compose

---

## Structure du projet

```text
FormDev-IA/
├── apps/
│   └── api/
│       ├── core/
│       ├── db/
│       │   ├── models/
│       │   └── session.py
│       ├── routers/
│       ├── schemas/
│       ├── services/
│       ├── utils/
│       ├── main.py
│       └── requirements.txt
├── infra/
│   ├── docker-compose.yml
│   └── .env.example
├── docs/
├── bench/
├── scripts/
└── README.md
```

### Principaux répertoires

- `apps/api/core` : configuration, sécurité, rate limiting ;
- `apps/api/db/models` : modèles SQLAlchemy ;
- `apps/api/routers` : endpoints HTTP ;
- `apps/api/schemas` : schémas Pydantic ;
- `apps/api/services` : logique métier ;
- `infra` : déploiement Docker ;
- `docs` : documentation développeur et client technique ;
- `bench` : scripts de test / benchmark.

---

## Démarrage rapide

### 1. Préparer l’environnement

```bash
cp infra/.env.example infra/.env
```

Adapter ensuite les secrets, ports et paramètres modèle dans `infra/.env`.

### 2. Lancer les services

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build
```

### 3. Appliquer les migrations

```bash
docker exec -it infra-api-dev-1 alembic upgrade head
```

Adapter le nom du conteneur si nécessaire :

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep api
```

### 4. Accéder à Swagger

```text
http://localhost:<API_PORT>/docs
```

Le port dépend de `API_DEV_PORT` ou `API_PROD_PORT` dans `infra/.env`.

Voir aussi : [Runbook opérationnel](docs/runbook.md).

---

## Configuration

Principales sources :

- `infra/.env`
- `infra/.env.example`
- `apps/api/core/config.py`

Variables importantes :

### API

- `API_KEYS`
- `RATE_LIMIT_RPM`
- `LOG_LEVEL`
- `API_DEV_PORT`
- `API_PROD_PORT`

### vLLM

- `MODEL_ID`
- `VLLM_BASE_URL`
- `MAX_MODEL_LEN`
- `DTYPE`

### PostgreSQL

- `DATABASE_URL`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DEV_DB`
- `POSTGRES_PROD_DB`

### Qdrant

- `QDRANT_URL`
- `QDRANT_COLLECTION`
- `QDRANT_EMBEDDING_MODEL`
- `QDRANT_VECTOR_SIZE`
- `RAG_QDRANT_COLLECTION`
- `RAG_VECTOR_SIZE`

### Redis / RQ

- `REDIS_HOST`
- `REDIS_PORT`
- `RQ_SURVEY_DEV_QUEUE`
- `RQ_RAG_DEV_QUEUE`

---

## API exposée

Cette section liste les routes exposées par les trois modules. Pour les exemples de requêtes et les détails de payload, consulter les docs client liées.

### Projet 1 — RAG documentaire

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

Documentation : [Documentation client — RAG documentaire](docs/client-technique-rag.md).

### Projet 2 — Chat IA

| Méthode | Route | Usage |
| --- | --- | --- |
| POST | `/v1/chat` | Générer, reformuler, résumer ou corriger un texte via vLLM |

Documentation : [Documentation client — Chat IA](docs/client-technique-chat.md).

### Projet 3 — Surveys

| Méthode | Route | Usage |
| --- | --- | --- |
| POST | `/surveys/analyze` | Lancer une analyse asynchrone de questionnaires |
| GET | `/surveys/processings/{processing_id}` | Suivre un traitement et récupérer son résultat final |
| POST | `/surveys/feedback` | Enregistrer un feedback opérateur |
| GET | `/surveys/feedback` | Lister les exemples de feedback/mémoire d'un client |

Documentation : [Documentation client — Surveys](docs/client-technique-surveys.md).

---

## Projet 1 — RAG documentaire

Le RAG utilise la collection Qdrant `rag_chunks`.

La stratégie actuelle est :

- recherche filtrée par `client_id` et `corpus_id` ;
- suppression physique des points Qdrant quand une source est supprimée ;
- suppression des anciens points avant réindexation d’une source.

Pour plus d'informations :

- [Documentation client — RAG documentaire](docs/client-technique-rag.md)
- [Architecture RAG détaillée](docs/rag_architecture.md)

---

## Projet 2 — Chat IA

Le Chat IA est une gateway vers vLLM exposée via `/v1/chat`.

Pour plus d'informations : [Documentation client — Chat IA](docs/client-technique-chat.md).

---

## Projet 3 — Surveys

Le module Surveys lance des traitements asynchrones et expose un workflow de feedback opérateur.

Pour plus d'informations : [Documentation client — Surveys](docs/client-technique-surveys.md).

---

## Base de données

Tables principales :

- `survey_responses`
- `response_points`
- `validated_response_points`
- `point_feedback`
- `survey_processing_jobs`
- `ai_interactions`
- tables RAG de sources, corpus, conversations et jobs

---

## Mémoire vectorielle Qdrant

Deux usages Qdrant principaux :

### Surveys

Collection d’exemples validés par feedback opérateur, filtrée par client.

Payload typique :

- `client_id`
- `question_text`
- `input_point_text`
- `final_text`
- `final_sentiment`
- `final_category`
- `example_type`
- `response_id`
- `point_id`
- `is_active`

### RAG

Collection documentaire `rag_chunks`, filtrée par `client_id` et `corpus_id`.

Payload typique :

- `client_id`
- `corpus_id`
- `source_id`
- `source_type`
- `source_name`
- `page`
- `chunk_index`
- `text`
- `metadata`

---

## Sécurité

Toutes les routes métier sont protégées par le header :

```text
X-API-Key: <clé_api>
```

Les clés sont configurées via `API_KEYS`.

Le rate limiting est configuré via `RATE_LIMIT_RPM`.
