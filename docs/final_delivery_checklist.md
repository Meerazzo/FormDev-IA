# Checklist de livraison finale — FormDev IA

Ce document fige l'état initial du dépôt avant la passe de nettoyage/livraison.

Date de création : 2026-06-25
Branche de travail : `chore/day1-01-freeze-state`

## Objectif de la passe finale

Rendre le projet livrable, compréhensible et maintenable pour une intégration CRM/front, sans casser les fonctionnalités existantes.

Priorité des modules :

1. Chatbot RAG documentaire (`/rag/*`)
2. Configuration et Docker
3. API Chat (`/v1/chat`)
4. Analyse de questionnaires (`/surveys/*`)
5. Documentation développeur et documentation client technique
6. Smoke tests et nettoyage final

## État initial observé

### Dépôt principal

- Dépôt : `Meerazzo/FormDev-IA`
- Branche source : `main`
- Application principale : `apps/api/main.py`
- Framework API : FastAPI
- Services principaux : vLLM, PostgreSQL, Qdrant, Redis/RQ

### Modules API exposés

| Module | Router | Routes principales | État initial |
| --- | --- | --- | --- |
| Health | `apps/api/routers/health.py` | `GET /health` | Présent |
| Chat | `apps/api/routers/chat_proxy.py` | `POST /v1/chat` | Présent, documenté dans Swagger |
| Questionnaires | `apps/api/routers/surveys.py` | `POST /surveys/analyze`, `GET /surveys/processings/{processing_id}`, `POST /surveys/feedback` | Présent, async via Redis/RQ |
| RAG documentaire | `apps/api/routers/rag.py` | `/rag/health`, `/rag/sources/*`, `/rag/corpora/*`, `/rag/conversations/*`, `/rag/chat`, `/rag/chat/stream`, `/rag/jobs/*` | Présent, prioritaire pour la livraison |

## Points déjà validés par structure de code

- API construite via factory `create_app()`.
- Routers principaux enregistrés dans `main.py`.
- Authentification par `X-API-Key`.
- Rate limiting avec SlowAPI.
- Logging centralisé avec request id.
- Modèles Pydantic présents pour Chat, Surveys et RAG.
- RAG structuré avec services d'ingestion, indexation, vector store, conversations et jobs.
- Workers RQ présents pour Survey et RAG.
- Docker Compose présent dans `infra/docker-compose.yml`.
- Dockerfile API présent dans `apps/api/Dockerfile`.
- README et runbook existants.

## Problèmes identifiés à corriger

### P0 — bloquants livraison

- [ ] `infra/.env.example` n'est pas aligné avec toutes les variables utilisées dans `infra/docker-compose.yml`.
- [ ] Le README mentionne encore `/surveys/forms/analyze` alors que le code expose `POST /surveys/analyze`.
- [ ] Le README doit présenter clairement les 3 modules : Chat, Surveys, RAG.
- [ ] `scripts/smoke_test.sh` est référencé mais semble absent.
- [ ] `.dockerignore` est absent.
- [ ] `bench/results/` est ignoré dans `.gitignore` mais des résultats semblent déjà versionnés.
- [ ] La documentation RAG mentionne un filtre `is_active=true` côté Qdrant, mais le vector store ne l'applique pas encore explicitement.

### P1 — important

- [ ] Docker Compose mélange dev, prod, vLLM, observabilité et services optionnels dans un seul fichier.
- [ ] Graylog/OpenSearch/Mongo devraient être optionnels ou isolés.
- [ ] Le Dockerfile installe Playwright/Patchright même lorsque le parser URL avancé n'est pas utilisé.
- [ ] Les tags Swagger peuvent être harmonisés.
- [ ] Les documentations client technique doivent être créées pour Chat, Surveys et RAG.

### P2 — amélioration si temps disponible

- [ ] Découper `routers/rag.py` en plusieurs sous-routers.
- [ ] Ajouter une CI minimale.
- [ ] Ajouter des tests pytest.
- [ ] Ajouter une collection Postman/Bruno.

## Branches prévues

| Bloc | Branche prévue | Objectif |
| --- | --- | --- |
| Gel état actuel | `chore/day1-01-freeze-state` | Ajouter la checklist de départ |
| Configuration env | `chore/day1-02-env-example` | Corriger `infra/.env.example` |
| Docker Compose | `chore/day1-03-docker-compose-cleanup` | Rendre le compose plus lisible et livrable |
| Dockerfile + dockerignore | `chore/day1-04-dockerfile-dockerignore` | Nettoyer build Docker et exclusions |

## Checklist de validation par module

Pour chaque module terminé :

- [ ] Branche dédiée créée.
- [ ] Modifications limitées au périmètre du module.
- [ ] Fichiers critiques relus.
- [ ] Aucun secret ajouté.
- [ ] Instructions de lancement cohérentes.
- [ ] Résumé de validation fourni.
- [ ] Liste du reste à faire mise à jour.
- [ ] Fusion vers `main` uniquement après validation stable.

## Définition de terminé pour la livraison finale

Le projet est considéré livrable quand un développeur externe peut :

1. cloner le dépôt ;
2. copier `infra/.env.example` vers `infra/.env` ;
3. lancer les services Docker ;
4. appliquer les migrations ;
5. ouvrir Swagger ;
6. tester les endpoints principaux ;
7. comprendre les flux Chat, Surveys et RAG ;
8. intégrer les endpoints côté CRM/front à partir des documents `docs/client-technique-*.md`.
