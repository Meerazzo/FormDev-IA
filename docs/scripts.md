# Scripts du projet

Cette page référence les scripts disponibles dans `scripts/`, leur rôle et les commandes d'utilisation.

## Règles générales

Tous les scripts sont à lancer depuis la racine du dépôt :

```bash
cd /home/meara/Formdev_IA
```

La plupart des commandes Docker utilisent :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml ...
```

Ne jamais utiliser `docker compose down -v` sauf volonté explicite de supprimer les volumes PostgreSQL, Qdrant, RAG et Graylog.

## `scripts/smoke_test.sh`

Test global de non-régression de l'API.

Il vérifie notamment :

- `GET /health` ;
- Swagger / OpenAPI ;
- `POST /v1/chat` ;
- `POST /surveys/analyze` puis suivi du processing ;
- upload RAG ;
- indexation RAG ;
- recherche RAG ;
- chat RAG.

### Utilisation dev

```bash
set -a
source infra/.env
set +a

KEY="$(printf "%s" "$API_KEYS" | cut -d',' -f1 | cut -d':' -f2-)"

API_KEY="$KEY" \
API_PORT="$API_DEV_PORT" \
CLIENT_ID="smoke-dev-client" \
RAG_CORPUS_ID="smoke-dev-corpus" \
bash scripts/smoke_test.sh
```

### Utilisation prod-like

```bash
set -a
source infra/.env
set +a

KEY="$(printf "%s" "$API_KEYS" | cut -d',' -f1 | cut -d':' -f2-)"

API_KEY="$KEY" \
API_PORT="$API_PROD_PORT" \
CLIENT_ID="smoke-prod-client" \
RAG_CORPUS_ID="smoke-prod-corpus" \
bash scripts/smoke_test.sh
```

Résultat attendu :

```text
Global smoke test OK
```

## `scripts/formdevctl.sh`

Helper d'exploitation pour éviter de retaper les commandes Docker Compose longues.

Il ne remplace pas Docker Compose : il centralise seulement les commandes fréquentes.

### Aide

```bash
bash scripts/formdevctl.sh help
```

### Commandes utiles

| Commande | Usage |
| --- | --- |
| `bash scripts/formdevctl.sh config` | Vérifier la configuration Docker Compose résolue. |
| `bash scripts/formdevctl.sh services` | Lister les services Compose. |
| `bash scripts/formdevctl.sh ps` | Voir l'état des conteneurs. |
| `bash scripts/formdevctl.sh up` | Lancer la stack dev avec build. |
| `bash scripts/formdevctl.sh up-no-build` | Lancer la stack dev sans rebuild. |
| `bash scripts/formdevctl.sh down` | Arrêter la stack dev sans supprimer les volumes. |
| `bash scripts/formdevctl.sh restart api-dev` | Redémarrer un service précis. |
| `bash scripts/formdevctl.sh restart-workers` | Redémarrer les workers dev. |
| `bash scripts/formdevctl.sh migrate` | Appliquer les migrations Alembic côté dev. |
| `bash scripts/formdevctl.sh smoke` | Lancer le smoke test dev. |
| `bash scripts/formdevctl.sh health` | Vérifier `/health`, `/docs`, `/openapi.json` et `/rag/health`. |
| `bash scripts/formdevctl.sh logs-api` | Voir les logs API dev. |
| `bash scripts/formdevctl.sh logs-workers` | Voir les logs workers Survey/RAG dev. |
| `bash scripts/formdevctl.sh logs-inference` | Voir les logs vLLM. |
| `bash scripts/formdevctl.sh logs-graylog` | Voir les logs Graylog. |
| `bash scripts/formdevctl.sh up-observability` | Lancer le profil Graylog. |
| `bash scripts/formdevctl.sh shell-api` | Ouvrir un shell dans `api-dev`. |
| `bash scripts/formdevctl.sh qdrant-collections` | Lister les collections Qdrant dev. |

## `scripts/enable_graylog_dev.sh`

Active Graylog dans `infra/.env` pour l'environnement local/dev.

```bash
bash scripts/enable_graylog_dev.sh
```

Puis relancer les services concernés :

```bash
docker compose --profile observability --env-file infra/.env -f infra/docker-compose.yml up -d --build --force-recreate api-dev worker-survey-dev worker-rag-dev graylog
```

Graylog est ensuite accessible sur :

```text
http://localhost:9000
```

## `scripts/enable_survey_purge_after_feedback.sh`

Active la purge PostgreSQL des données Survey après feedback opérateur.

```bash
bash scripts/enable_survey_purge_after_feedback.sh
```

Puis relancer les services API/workers pour que la nouvelle variable d'environnement soit prise en compte :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build --force-recreate api-dev worker-survey-dev
```

À utiliser seulement si le fonctionnement attendu est :

- conserver les exemples validés dans Qdrant ;
- réduire la conservation PostgreSQL des points/réponses après feedback.

## Changement de clé API

Si `API_KEYS` est modifié dans `infra/.env`, il faut recréer les conteneurs API et workers :

```bash
docker compose --profile prod --profile observability --env-file infra/.env -f infra/docker-compose.yml up -d --force-recreate api-dev api-prod worker-survey-dev worker-rag-dev worker-survey-prod worker-rag-prod
```

Vérifier ensuite que la clé visible dans le conteneur correspond au `.env` sans l'afficher en clair :

```bash
set -a
source infra/.env
set +a

KEY="$(printf "%s" "$API_KEYS" | cut -d',' -f1 | cut -d':' -f2-)"
printf "local key len=%s sha=%s\n" "${#KEY}" "$(printf "%s" "$KEY" | sha256sum | cut -c1-12)"

docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T api-dev sh -lc '
python - <<"PY"
from core.config import settings
import hashlib
key = settings.API_KEYS.split(",", 1)[0].split(":", 1)[-1].strip()
print(f"container key len={len(key)} sha={hashlib.sha256(key.encode()).hexdigest()[:12]}")
PY'
```
