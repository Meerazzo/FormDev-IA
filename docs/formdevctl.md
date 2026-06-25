# Script d'exploitation — `formdevctl.sh`

Dernière mise à jour : 2026-06-25

Le script `scripts/formdevctl.sh` centralise les commandes opérationnelles courantes du projet FormDev IA.

Il ne remplace pas Docker Compose, mais évite de retaper à chaque fois les mêmes commandes longues avec `--env-file infra/.env -f infra/docker-compose.yml`.

## Lancement

Depuis la racine du dépôt :

```bash
bash scripts/formdevctl.sh help
```

Le fichier est volontairement utilisable avec `bash`, même si le bit exécutable n'est pas encore activé localement.

Si besoin :

```bash
chmod +x scripts/formdevctl.sh
./scripts/formdevctl.sh help
```

## Pré-requis

Le script attend par défaut :

```text
infra/.env
infra/docker-compose.yml
```

Si `infra/.env` n'existe pas encore :

```bash
cp infra/.env.example infra/.env
```

Puis adapter les secrets et valeurs locales.

## Commandes principales

### Vérifier la configuration Compose

```bash
bash scripts/formdevctl.sh config
```

Cette commande écrit aussi la configuration résolue dans un fichier temporaire unique :

```text
/tmp/formdev-compose-check-XXXXXX.yml
```

### Lister les services

```bash
bash scripts/formdevctl.sh services
```

### Voir l'état des conteneurs

```bash
bash scripts/formdevctl.sh ps
```

Alias :

```bash
bash scripts/formdevctl.sh status
```

### Lancer les services dev avec build

```bash
bash scripts/formdevctl.sh up
```

### Lancer sans rebuild

```bash
bash scripts/formdevctl.sh up-no-build
```

### Arrêter les services

```bash
bash scripts/formdevctl.sh down
```

### Redémarrer un service précis

```bash
bash scripts/formdevctl.sh restart api-dev
```

### Redémarrer uniquement les workers

```bash
bash scripts/formdevctl.sh restart-workers
```

Cette commande recrée uniquement :

```text
worker-survey-dev
worker-rag-dev
```

sans rebuild.

### Appliquer les migrations

```bash
bash scripts/formdevctl.sh migrate
```

Équivalent à :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml exec api-dev alembic upgrade head
```

### Lancer le smoke test global

```bash
bash scripts/formdevctl.sh smoke
```

Le script :

1. charge `infra/.env` ;
2. récupère automatiquement la première clé de `API_KEYS` ;
3. définit `API_KEY` ;
4. utilise `API_DEV_PORT` comme port API par défaut ;
5. lance `scripts/smoke_test.sh`.

Variables personnalisables :

```bash
CLIENT_ID="demo-client" \
RAG_CORPUS_ID="demo-corpus" \
bash scripts/formdevctl.sh smoke
```

### Vérifier les endpoints de base

```bash
bash scripts/formdevctl.sh health
```

Cette commande teste :

```text
/health
/docs
/openapi.json
/rag/health
```

## Logs

### Tous les logs

```bash
bash scripts/formdevctl.sh logs
```

### Logs API

```bash
bash scripts/formdevctl.sh logs-api
```

### Logs workers Survey + RAG

```bash
bash scripts/formdevctl.sh logs-workers
```

### Logs worker RAG

```bash
bash scripts/formdevctl.sh logs-rag
```

### Logs worker Survey

```bash
bash scripts/formdevctl.sh logs-survey
```

### Logs vLLM

```bash
bash scripts/formdevctl.sh logs-inference
```

### Logs Graylog

```bash
bash scripts/formdevctl.sh logs-graylog
```

## Observabilité

Lancer le profil observability :

```bash
bash scripts/formdevctl.sh up-observability
```

Cela démarre les services du profil observabilité configurés dans Docker Compose.

## Debug

### Shell dans le conteneur API

```bash
bash scripts/formdevctl.sh shell-api
```

### Lister les collections Qdrant

```bash
bash scripts/formdevctl.sh qdrant-collections
```

Le script récupère automatiquement le port exposé par le service `qdrant-dev`.

## Permission Docker

Si la commande échoue avec :

```text
permission denied while trying to connect to the Docker daemon socket
```

Solution temporaire :

```bash
su
bash scripts/formdevctl.sh ps
```

Solution durable :

```bash
sudo usermod -aG docker $USER
```

Puis rouvrir la session.

## Variables optionnelles

| Variable | Usage | Défaut |
| --- | --- | --- |
| `ENV_FILE` | Fichier d'environnement | `infra/.env` |
| `COMPOSE_FILE` | Fichier Docker Compose | `infra/docker-compose.yml` |
| `API_KEY` | API key explicite | Première clé de `API_KEYS` |
| `API_PORT` | Port API local | `API_DEV_PORT`, puis `8081` |
| `API_URL` | URL API complète | `http://localhost:$API_PORT` |
| `CLIENT_ID` | Client utilisé par le smoke test | `formdevctl-smoke-client` |
| `RAG_CORPUS_ID` | Corpus utilisé par le smoke test | `formdevctl-smoke-corpus` |

Exemple :

```bash
ENV_FILE=infra/.env \
API_PORT=8081 \
CLIENT_ID=client_test \
RAG_CORPUS_ID=corpus_test \
bash scripts/formdevctl.sh smoke
```
