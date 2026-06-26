# FormDev IA

API d'inférence, d'analyse de questionnaires et de chatbot documentaire pour FormDev.

Le projet fournit trois briques principales :

- **Projet 1 — RAG documentaire** : chatbot documentaire multi-client (`/rag/*`) avec ingestion de sources, indexation Qdrant, recherche vectorielle et réponses sourcées.
- **Projet 2 — Chat IA** : route de génération / transformation de texte (`/v1/chat`) via vLLM.
- **Projet 3 — Surveys** : pipeline d'analyse de questionnaires de satisfaction (`/surveys/*`) avec traitement asynchrone, segmentation, classification, feedback opérateur et mémoire vectorielle par client.

---

## Documentation technique

| Document | Public cible | Contenu |
| --- | --- | --- |
| [Architecture globale](docs/architecture.md) | développeur / mainteneur | Vue d'ensemble des modules Chat, Surveys et RAG, composants et flux |
| [Runbook opérationnel](docs/runbook.md) | exploitation | Lancement Docker, migrations, tests curl, logs et dépannage |
| [Scripts du projet](docs/scripts.md) | développeur / exploitation | Rôle des scripts, commandes, smoke tests et changement de clé API |
| [Documentation client — Chat IA](docs/client-technique-chat.md) | intégrateur CRM/front | Route `/v1/chat`, payload d'entrée, réponse, erreurs et bonnes pratiques |
| [Documentation client — Surveys](docs/client-technique-surveys.md) | intégrateur CRM/front | Routes `/surveys/*`, format questionnaire, statuts, résultat enrichi et feedback opérateur |
| [Documentation client — RAG documentaire](docs/client-technique-rag.md) | intégrateur CRM/front | Routes `/rag/*`, sources, indexation, search, chat, streaming, jobs et sorties attendues |
| [Architecture RAG détaillée](docs/rag_architecture.md) | développeur RAG | Cycle de vie des sources RAG, Qdrant, réindexation et conversations |
| [Nettoyage stockage RAG](docs/rag_storage_cleanup.md) | exploitation / mainteneur | Politique de suppression des artefacts locaux après indexation et suppression source |
| [Nettoyage feedback Survey](docs/survey_feedback_cleanup.md) | exploitation / mainteneur | Politique de purge PostgreSQL après feedback opérateur |
| [Observabilité Graylog](docs/graylog_observability.md) | exploitation | Activation Graylog, champs structurés, recherches et dashboards recommandés |
| [Limites connues](docs/known_limitations.md) | développeur / exploitation | Limites techniques et points à surveiller |
| [Checklist de livraison finale](docs/final_delivery_checklist.md) | pilotage | Suivi de la passe finale de nettoyage/livraison |

---

## Architecture fonctionnelle

```text
Clients / CRM / Front FormDev
        ↓
FastAPI Gateway
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

Composants principaux :

- **FastAPI** : gateway HTTP, validation, Swagger, sécurité ;
- **vLLM** : serveur d'inférence LLM compatible OpenAI ;
- **PostgreSQL** : stockage métier, jobs, sources, résultats et conversations ;
- **Qdrant** : mémoire vectorielle Survey et RAG ;
- **Redis/RQ** : files de traitement asynchrone ;
- **Graylog** : observabilité optionnelle en développement/exploitation.

---

## Lire le code

Le backend suit une séparation simple :

```text
apps/api/
├── core/                 # configuration, sécurité, rate limit, logging
├── db/
│   ├── models/           # modèles SQLAlchemy
│   └── session.py        # session DB
├── routers/              # couche HTTP FastAPI
│   ├── health.py
│   ├── chat/             # projet Chat IA
│   │   ├── __init__.py
│   │   └── routes.py     # /v1/chat
│   ├── survey/           # projet Surveys
│   │   ├── __init__.py
│   │   └── routes.py     # /surveys/*
│   └── rag/              # projet RAG documentaire
├── schemas/              # contrats Pydantic d'entrée/sortie
├── services/             # logique métier
├── workers/              # workers Redis/RQ
├── utils/                # helpers transverses
└── main.py               # factory FastAPI et assemblage des routers
```

Règle de lecture :

```text
routers/  = traduire HTTP -> service métier
schemas/  = définir les contrats d'entrée/sortie
services/ = exécuter la logique métier
workers/  = exécuter les traitements longs en arrière-plan
docs/     = expliquer l'intégration et l'exploitation
```

Le router RAG est découpé pour éviter un fichier unique trop long :

```text
apps/api/routers/rag/
├── __init__.py           # assemble les sous-routers
├── common.py             # helpers partagés RAG
├── health.py             # /rag/health
├── sources.py            # sources, upload, URL, index/reindex, delete
├── corpora.py            # corpus et resync
├── search.py             # /rag/search
├── conversations.py      # conversations et messages
├── chat.py               # /rag/chat et /rag/chat/stream
└── jobs.py               # /rag/jobs/{job_id}
```

---

## Démarrage rapide

### 1. Préparer l'environnement

```bash
cp infra/.env.example infra/.env
```

Adapter ensuite les secrets, ports et paramètres modèle dans `infra/.env`.

### 2. Lancer les services dev

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build
```

### 3. Lancer dev + prod-like + observabilité

```bash
docker compose --profile prod --profile observability --env-file infra/.env -f infra/docker-compose.yml up -d --build
```

### 4. Appliquer les migrations

```bash
docker exec -it infra-api-dev-1 alembic upgrade head
docker exec -it infra-api-prod-1 alembic upgrade head
```

### 5. Accéder à Swagger

```text
Dev  : http://localhost:<API_DEV_PORT>/docs
Prod : http://localhost:<API_PROD_PORT>/docs
```

Le port dépend de `API_DEV_PORT` ou `API_PROD_PORT` dans `infra/.env`.

---

## Utiliser Swagger avec l'API key

Toutes les routes métier utilisent le header :

```text
X-API-Key: <clé_api>
```

Si `API_KEYS` est au format :

```text
client_demo:ma-cle-secrete
```

alors dans Swagger il faut cliquer sur **Authorize** et coller uniquement :

```text
ma-cle-secrete
```

Ne pas coller `client_demo:ma-cle-secrete` et ne pas préfixer par `Bearer`.

Après modification de `API_KEYS` dans `infra/.env`, recréer les conteneurs API/workers :

```bash
docker compose --profile prod --profile observability --env-file infra/.env -f infra/docker-compose.yml up -d --force-recreate api-dev api-prod worker-survey-dev worker-rag-dev worker-survey-prod worker-rag-prod
```

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

### Graylog

- `GRAYLOG_ENABLED`
- `GRAYLOG_HOST`
- `GRAYLOG_PORT`
- `GRAYLOG_FACILITY`

---

## Scripts utiles

| Script | Usage rapide | Documentation |
| --- | --- | --- |
| `scripts/smoke_test.sh` | Test global Chat + Surveys + RAG en dev ou prod-like | [docs/scripts.md](docs/scripts.md) |
| `scripts/formdevctl.sh` | Helper d'exploitation pour Docker Compose, logs, smoke, migrations | [docs/scripts.md](docs/scripts.md) |
| `scripts/enable_graylog_dev.sh` | Active Graylog dans `infra/.env` | [docs/scripts.md](docs/scripts.md) |
| `scripts/enable_survey_purge_after_feedback.sh` | Active la purge Survey après feedback opérateur | [docs/scripts.md](docs/scripts.md) |

---

## API exposée

Pour les payloads complets, exemples d'entrées/sorties et recommandations CRM, consulter les documentations client :

- [Chat IA](docs/client-technique-chat.md)
- [Surveys](docs/client-technique-surveys.md)
- [RAG documentaire](docs/client-technique-rag.md)

Résumé des routes principales :

| Module | Routes principales |
| --- | --- |
| System | `GET /health` |
| Chat IA | `POST /v1/chat` |
| Surveys | `POST /surveys/analyze`, `GET /surveys/processings/{processing_id}`, `POST /surveys/feedback`, `GET /surveys/feedback` |
| RAG | `/rag/health`, `/rag/sources/*`, `/rag/corpora/*`, `/rag/search`, `/rag/chat`, `/rag/chat/stream`, `/rag/conversations/*`, `/rag/jobs/*` |

---

## Stockage et mémoire vectorielle

### PostgreSQL

Tables principales :

- `survey_responses`
- `response_points`
- `validated_response_points`
- `point_feedback`
- `survey_processing_jobs`
- `ai_interactions`
- tables RAG de sources, corpus, conversations et jobs

### Qdrant

Deux usages principaux :

- **Surveys** : mémoire d'exemples validés par feedback opérateur, filtrée par client.
- **RAG** : collection documentaire `rag_chunks`, filtrée par `client_id` et `corpus_id`.

---

## Sécurité

Toutes les routes métier sont protégées par le header :

```text
X-API-Key: <clé_api>
```

Les clés sont configurées via `API_KEYS`.

Le rate limiting est configuré via `RATE_LIMIT_RPM`.
