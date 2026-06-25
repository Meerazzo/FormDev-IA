# Checklist de livraison finale — FormDev IA

Date de création : 2026-06-25  
Dernière mise à jour : 2026-06-25  
Dépôt : `Meerazzo/FormDev-IA`

## Objectif de la passe finale

Rendre le projet livrable, compréhensible et maintenable pour une intégration CRM/front, sans casser les fonctionnalités existantes.

Modules prioritaires :

1. RAG documentaire (`/rag/*`)
2. Configuration et Docker
3. Chat IA (`/v1/chat`)
4. Surveys (`/surveys/*`)
5. Documentation développeur et documentation client technique
6. Smoke tests et nettoyage final

---

## État final synthétique

| Bloc | État | Validation |
| --- | --- | --- |
| Configuration env | Terminé | `infra/.env.example` aligné avec Docker Compose |
| Docker Compose | Terminé | `docker compose config` validé |
| Dockerfile API | Terminé | Build Docker API validé |
| `.dockerignore` | Terminé | Exclusions de build ajoutées |
| RAG lifecycle Qdrant | Terminé | Upload, index, search, reindex, delete validés |
| README développeur | Terminé | README recentré sur Chat, Surveys et RAG |
| Documentation technique | Terminé | Architecture, runbook, docs client et limitations connues ajoutés |
| Surveys | Terminé | Analyze, processing, feedback et mémoire Qdrant validés |
| Chat IA | Terminé | `/v1/chat` et `scripts/smoke_test.sh` validés |
| Swagger / OpenAPI | Terminé | `/docs` et `/openapi.json` validés, ReDoc désactivé volontairement |
| Workers RQ | Terminé | Healthchecks Redis dédiés, workers RAG et Survey `healthy` |
| Script d'exploitation | Terminé | `scripts/formdevctl.sh` ajouté pour centraliser les commandes courantes |
| Smoke global | Terminé | Health, Swagger, Chat, Surveys et RAG validés ensemble |

---

## Problèmes initiaux traités

### P0 — bloquants livraison

- [x] `infra/.env.example` aligné avec les variables utilisées dans `infra/docker-compose.yml`.
- [x] README corrigé : remplacement des anciennes références `/surveys/forms/analyze` par `/surveys/analyze`.
- [x] README restructuré autour des 3 modules : Chat, Surveys, RAG.
- [x] `scripts/smoke_test.sh` présent, sécurisé et étendu en smoke test global.
- [x] `.dockerignore` ajouté.
- [x] `bench/results` et scripts benchmark/expérimentaux nettoyés du dépôt.
- [x] Documentation RAG corrigée : pas de filtre `is_active=true` annoncé pour les chunks RAG, car le vector store ne l'utilise pas.
- [x] RAG réindexation corrigée : suppression des anciens points Qdrant avant upsert des nouveaux chunks.
- [x] Documentation client créée pour les trois modules : Chat, Surveys et RAG.

### P1 — important

- [x] Docker Compose rendu plus lisible avec profils et services mieux séparés.
- [x] Graylog/OpenSearch/Mongo isolés via profil observabilité.
- [x] Dockerfile allégé : dépendances navigateur rendues optionnelles via `INSTALL_BROWSER_DEPS`.
- [x] Documentation client technique créée pour Chat, Surveys et RAG.
- [x] README enrichi avec liens vers les fichiers de documentation.
- [x] Runbook opérationnel mis à jour.
- [x] Routes RAG complètes documentées dans README, runbook, architecture globale et doc client RAG.
- [x] Swagger/OpenAPI poli : tags, description globale, `operationId`, erreurs communes, auth `X-API-Key`.
- [x] ReDoc désactivé volontairement ; Swagger UI et OpenAPI JSON conservés.
- [x] Healthchecks workers corrigés : les workers RQ vérifient Redis au lieu d'hériter du `/health` HTTP de l'API.
- [x] Page de limitations connues ajoutée : `docs/known_limitations.md`.

### P1 bis — industrialisation / exploitation restante

- [ ] Rendre Graylog pleinement exploitable avec vues erreurs, latences et appels par module.
- [x] Créer un script de gestion projet : `scripts/formdevctl.sh`.
- [ ] Créer une procédure ou un script de nettoyage des données dev.
- [ ] Faire un test en conditions réelles léger : appels Chat, Surveys et RAG en parallèle.

### P2 — amélioration restante possible

- [ ] Découper `routers/rag.py` en sous-routers.
- [ ] Ajouter une CI minimale.
- [ ] Ajouter des tests pytest.
- [ ] Ajouter une collection Postman/Bruno.
- [ ] Ajouter un test de charge k6 ou Locust.
- [ ] Aligner les versions `qdrant-client` et serveur Qdrant pour supprimer le warning de compatibilité mineure.

---

## Validations réalisées

### Infrastructure

Commandes validées pendant la passe finale :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml config
docker compose --env-file infra/.env -f infra/docker-compose.yml config --services
docker compose --env-file infra/.env -f infra/docker-compose.yml --profile prod config --services
docker compose --env-file infra/.env -f infra/docker-compose.yml --profile observability config --services
docker build -f apps/api/Dockerfile -t formdev-api:test .
python -m compileall apps/api
```

### Docker runtime

État validé après correction des healthchecks :

- [x] `api-dev` : `healthy`
- [x] `postgres-dev` : `healthy`
- [x] `qdrant-dev` : `running`
- [x] `redis-dev` : `running`
- [x] `inference` : `running`
- [x] `worker-rag-dev` : `healthy`
- [x] `worker-survey-dev` : `healthy`

La correction appliquée consiste à utiliser un healthcheck Redis pour les workers RQ, au lieu du healthcheck HTTP `/health` de l'API.

### RAG documentaire

Scénarios validés :

- [x] `GET /rag/health`
- [x] `POST /rag/sources/upload`
- [x] `POST /rag/sources/{source_id}/index`
- [x] `POST /rag/search`
- [x] `POST /rag/chat`
- [x] `POST /rag/sources/{source_id}/reindex`
- [x] suppression des anciens chunks lors de la réindexation
- [x] `DELETE /rag/sources/{source_id}` avec suppression des points Qdrant

Validation spécifique : reindexation d'une source de 30 chunks vers 1 chunk, puis vérification du compteur Qdrant.

### Surveys

Scénarios validés :

- [x] `POST /surveys/analyze`
- [x] retour `processing_id`
- [x] `GET /surveys/processings/{processing_id}`
- [x] statut final `FINISHED`
- [x] segmentation en points
- [x] sentiment détecté
- [x] `categoryId` détecté
- [x] génération de `response_id` et `point_id`
- [x] `POST /surveys/feedback`
- [x] `GET /surveys/feedback`
- [x] stockage mémoire Qdrant Survey avec `is_active=true`
- [x] worker `worker-survey-dev` : job terminé avec `Job OK`

### Chat IA

Scénarios validés :

- [x] `POST /v1/chat`
- [x] réponse courte contrôlée
- [x] reformulation métier
- [x] `finish_reason=stop`
- [x] `usage` retourné
- [x] `latency_ms` retourné
- [x] `scripts/smoke_test.sh` exécuté avec `API_KEY` fourni par variable d'environnement

### Swagger / OpenAPI

Scénarios validés :

- [x] `/docs` retourne `200`
- [x] `/openapi.json` retourne `200`
- [x] `/redoc` retourne `404`, comportement attendu car ReDoc est désactivé volontairement
- [x] Authentification `X-API-Key` visible dans Swagger
- [x] Tags principaux lisibles : System, Chat, Surveys, RAG

### Script d'exploitation `formdevctl.sh`

Script ajouté : `scripts/formdevctl.sh`.

Commandes couvertes :

- [x] `config`
- [x] `services`
- [x] `ps` / `status`
- [x] `up`
- [x] `up-no-build`
- [x] `down`
- [x] `restart <service>`
- [x] `restart-workers`
- [x] `migrate`
- [x] `smoke`
- [x] `health`
- [x] `logs*`
- [x] `up-observability`
- [x] `qdrant-collections`

Documentation associée : `docs/formdevctl.md`.

### Smoke global final

Smoke global manuel validé avec :

- [x] `GET /health`
- [x] Swagger accessible via `/docs`
- [x] Chat : réponse `Chat OK`
- [x] Surveys : analyse puis processing `FINISHED`
- [x] RAG : upload TXT
- [x] RAG : indexation dans `rag_chunks`
- [x] RAG : recherche avec `results_count >= 1`
- [x] RAG : chat avec sources et `used_chunks_count >= 1`
- [x] RAG : suppression de la source et des points Qdrant
- [x] `Global smoke test OK`
- [x] `git status` propre après validation

Le script `scripts/smoke_test.sh` couvre désormais ce smoke global.

---

## Documentation finale disponible

- [Architecture globale](architecture.md)
- [Runbook opérationnel](runbook.md)
- [Script d'exploitation formdevctl](formdevctl.md)
- [Limitations connues](known_limitations.md)
- [Documentation client — Chat IA](client-technique-chat.md)
- [Documentation client — Surveys](client-technique-surveys.md)
- [Documentation client — RAG documentaire](client-technique-rag.md)
- [Architecture RAG détaillée](rag_architecture.md)

---

## Définition de terminé pour la livraison finale

Le projet est considéré livrable quand un développeur externe peut :

1. cloner le dépôt ;
2. copier `infra/.env.example` vers `infra/.env` ;
3. lancer les services Docker ;
4. appliquer les migrations ;
5. ouvrir Swagger ;
6. tester les endpoints principaux ;
7. comprendre les flux Chat, Surveys et RAG ;
8. intégrer les endpoints côté CRM/front à partir des documents `docs/client-technique-*.md` ;
9. exécuter `scripts/smoke_test.sh` pour valider les principaux modules ;
10. consulter `docs/known_limitations.md` pour connaître les limites restantes avant une industrialisation complète ;
11. utiliser `scripts/formdevctl.sh` pour les commandes opérationnelles courantes.
