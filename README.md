# FormDev IA

API d’inférence et d’analyse de questionnaires pour FormDev.

Le projet fournit deux briques principales :

- **Projet 2** : une route de génération / transformation de texte (`/v1/chat`)
- **Projet 3** : un pipeline d’analyse de formulaires de satisfaction avec :
  - traitement asynchrone
  - segmentation en points
  - classification sentiment / catégorie
  - workflow de feedback opérateur
  - mémoire vectorielle par client via Qdrant pour few-shots dynamiques

---

## Sommaire

- [Vue d’ensemble](#vue-densemble)
- [Architecture](#architecture) 
- [Technologies](#technologies)
- [Structure du projet](#structure-du-projet)
- [Démarrage rapide](#démarrage-rapide)
- [Configuration](#configuration)
- [API exposée](#api-exposée)
- [Projet 2 — `/v1/chat`](#projet-2--v1chat)
- [Projet 3 — questionnaires](#projet-3--questionnaires)
- [Base de données](#base-de-données)
- [Mémoire vectorielle Qdrant](#mémoire-vectorielle-qdrant)
- [Migrations Alembic](#migrations-alembic)
- [Sécurité](#sécurité)
- [Limites actuelles](#limites-actuelles)

---

## Vue d’ensemble

### Projet 2 — Génération / reformulation de texte
La route `/v1/chat` permet d’utiliser un modèle servi par vLLM pour des usages de rédaction en français :

- reformulation
- synthèse
- enrichissement
- génération guidée

L’API prend en charge :
- l’authentification par clé API
- le rate limiting
- l’injection d’un prompt système backend
- une post-correction optionnelle par seconde inférence

### Projet 3 — Analyse de questionnaires
La route `/surveys/forms/analyze` permet de lancer l’analyse complète d’un formulaire de satisfaction.

Le pipeline réalise :
1. l’extraction des questions distinctes
2. la sélection automatique des questions pertinentes
3. le stockage des réponses
4. la segmentation des réponses en points
5. la classification de chaque point :
   - sentiment sur 5
   - catégorie métier
6. le stockage du résultat final
7. la relecture opérateur via `/surveys/feedback`
8. l’alimentation d’une mémoire vectorielle Qdrant pour améliorer la classification sur les cas futurs

---

## Architecture

Le projet repose sur quatre composants :

- **FastAPI** : gateway HTTP, validation, Swagger, sécurité
- **vLLM** : serveur d’inférence LLM OpenAI-compatible
- **PostgreSQL** : stockage métier et logs d’interactions IA
- **Qdrant** : mémoire vectorielle des exemples validés par client

### Flux Projet 3
1. Le client appelle `POST /surveys/forms/analyze`
2. L’API crée un `processing_id`
3. Le traitement est exécuté en arrière-plan
4. Le client suit l’état via `GET /surveys/processings/{processing_id}`
5. Le résultat final est retourné une fois le job terminé
6. L’opérateur relit le résultat via `POST /surveys/feedback`
7. Les corrections alimentent PostgreSQL et Qdrant
8. Les futures classifications peuvent réutiliser des exemples proches pour le même client

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
├── bench/
├── scripts/
└── README.md
```

### Principaux répertoires

- `apps/api/core` : configuration, sécurité, rate limiting  
- `apps/api/db/models` : modèles SQLAlchemy  
- `apps/api/routers` : endpoints HTTP  
- `apps/api/schemas` : schémas Pydantic  
- `apps/api/services` : logique métier  
- `infra` : déploiement Docker  
- `bench` : scripts de test / benchmark  

---

## Démarrage rapide

### 1. Préparer l’environnement

```bash
cp infra/.env.example infra/.env
```

### 2. Lancer les services

```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d --build
```

### 3. Appliquer les migrations

```bash
docker exec -it infra-api-1 alembic upgrade head
```

### 4. Accéder à Swagger

http://localhost:8080/docs

### 5. Vérifier Qdrant

```bash
curl http://localhost:6333
```

---

## Configuration

Principales sources :

- `infra/.env`
- `apps/api/core/config.py`

### Variables importantes

#### API
- `API_KEYS`
- `RATE_LIMIT_RPM`
- `LOG_LEVEL`

#### PostgreSQL
- `DATABASE_URL`

#### Qdrant
- `QDRANT_URL`
- `QDRANT_COLLECTION`
- `QDRANT_EMBEDDING_MODEL`
- `QDRANT_VECTOR_SIZE`

---

## API exposée

### Projet 2
- `POST /v1/chat`

### Projet 3
- `POST /surveys/forms/analyze`
- `GET /surveys/processings/{processing_id}`
- `POST /surveys/feedback`

---

## Projet 3 — questionnaires

### 1. Lancer une analyse

`POST /surveys/forms/analyze`

### 2. Suivre un traitement

`GET /surveys/processings/{processing_id}`

### 3. Feedback opérateur

`POST /surveys/feedback`

---

## Base de données

Tables principales :

- `survey_responses`
- `response_points`
- `validated_response_points`
- `point_feedback`
- `survey_processing_jobs`
- `ai_interactions`

---

## Mémoire vectorielle Qdrant

Chaque exemple contient :

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

Utilisation :

- recherche par similarité
- filtrage par client
- injection en few-shot

---

## Migrations Alembic

```bash
docker exec -it infra-api-1 alembic upgrade head
```

---

## Sécurité

- Auth via `X-API-Key`
- Rate limiting actif

---

## Limites actuelles

- Pas encore de worker distribué
- Taxonomie globale
- Pas de gestion multi-taxonomie avancée
