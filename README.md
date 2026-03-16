# FormDev IA — Infrastructure IA locale

Backend IA on-premise (ou OVH) exposé **uniquement via API** pour permettre aux applications FormDev d’interroger un modèle de langage local.

Cette infrastructure constitue le **socle IA de la plateforme** et permet d’intégrer des capacités d’intelligence artificielle directement dans l’ERP FormDev.

Fonctionnalités principales :

- génération de contenu pédagogique
- assistance conversationnelle
- analyse de données textuelles
- futurs pipelines RAG et analyse de satisfaction

L’infrastructure repose sur un **modèle open source exécuté localement sur GPU**.

---

## Architecture générale

L’architecture repose sur une séparation claire entre :

- **l’inférence IA**
- **l’API gateway**

Composants principaux :

### inference

- serveur vLLM
- moteur d’inférence GPU
- compatible API OpenAI

### api

- FastAPI
- authentification par clé API
- rate limiting
- proxy vers vLLM

Schéma de fonctionnement :

```text
ERP / Extranet
      │
      ▼
API Gateway (FastAPI)
      │
      ▼
Serveur d'inférence vLLM
      │
      ▼
GPU
```

⚠️ L’ERP ne communique **jamais directement avec vLLM**.  
Toutes les requêtes passent par l’API gateway.

Cela permet :

- contrôle d’accès
- limitation du trafic
- journalisation
- stabilité du service

---

## Endpoint principal

### POST `/v1/chat`

Permet d’interroger le modèle de langage via une interface **compatible OpenAI Chat API**.

Les requêtes doivent contenir une liste de **messages structurés**.

Chaque message possède un rôle :

| rôle | description |
|------|-------------|
| `system` | instructions générales données au modèle |
| `user` | message envoyé par l’utilisateur |
| `assistant` | réponse précédente du modèle (optionnel) |

Exemple de requête :

```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "messages": [
    {
      "role": "system",
      "content": "Tu es un assistant pédagogique spécialisé dans la formation bureautique."
    },
    {
      "role": "user",
      "content": "Explique ce qu'est un style dans Word."
    }
  ],
  "max_tokens": 150,
  "temperature": 0.7
}
```

---

## Réponse de l’API

Exemple de réponse :

```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
  "content": "Un style dans Word permet d'appliquer automatiquement une mise en forme cohérente à des titres ou paragraphes.",
  "finish_reason": "stop",
  "usage": {
    "prompt_tokens": 47,
    "completion_tokens": 13,
    "total_tokens": 60
  },
  "latency_ms": 842.3
}
```

---

## Multi-utilisateurs et gestion de charge

Le serveur d’inférence **vLLM** permet de gérer plusieurs requêtes simultanément.

Le mécanisme repose sur le **KV cache paginé** :

- la mémoire GPU est divisée en pages
- les requêtes partagent efficacement ces pages de mémoire
- les générations de tokens sont intercalées entre plusieurs utilisateurs

Cela permet de servir **plusieurs utilisateurs simultanément** avec une seule instance GPU.

Pour protéger l’infrastructure, un **rate limiting** est appliqué :

```text
30 requêtes / minute / client
```

Cela évite :

- la saturation GPU
- les abus d’API
- les blocages du serveur

---

## Prérequis

- Linux (Debian / Ubuntu)
- Docker
- Docker Compose
- GPU NVIDIA
- drivers NVIDIA installés
- NVIDIA Container Toolkit

Vérification :

```bash
nvidia-smi
```

---

## Démarrage rapide

### 1. Configuration

```bash
cp infra/.env.example infra/.env
nano infra/.env
```

### 2. Lancement des services

```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d --build
```

Vérification :

```bash
docker compose -f infra/docker-compose.yml ps
```

### 3. Vérifier que l’API fonctionne

```bash
curl http://localhost:8080/health
```

Réponse attendue :

```json
{"status": "ok"}
```

### 4. Test de génération

```bash
API_KEY="FormdevINF26"

curl http://localhost:8080/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [
      {"role":"user","content":"Dis bonjour en une phrase."}
    ],
    "max_tokens": 60
  }'
```

---

## Configuration (`.env`)

Variables principales :

| variable | description |
|----------|-------------|
| `API_KEYS` | clés API autorisées |
| `RATE_LIMIT_RPM` | limite requêtes/minute |
| `MODEL_ID` | modèle Hugging Face |
| `MAX_MODEL_LEN` | taille contexte max |
| `DTYPE` | type de précision GPU |
| `API_PORT` | port de l’API |
| `VLLM_PORT` | port interne vLLM |
| `HF_CACHE` | cache Hugging Face |

Exemple :

```env
API_KEYS=client1:key123,client2:key456
RATE_LIMIT_RPM=30
MODEL_ID=Qwen/Qwen2.5-7B-Instruct
```

---

## Logs et debug

Logs API :

```bash
docker compose -f infra/docker-compose.yml logs -f api
```

Logs serveur IA :

```bash
docker compose -f infra/docker-compose.yml logs -f inference
```

Emplacement des logs Docker :

```bash
CID=$(docker ps -qf "name=infra-api-1")
docker inspect --format='{{.LogPath}}' "$CID"
```

---

## Surveillance GPU

```bash
nvidia-smi
```

Permet de vérifier :

- utilisation GPU
- mémoire GPU
- processus actifs

---

## Exploitation via scripts

Les scripts facilitent l’administration.

Sur ce serveur Docker est accessible uniquement en **root**.

Connexion :

```bash
su -
cd /home/meara/Formdev_IA
```

Commandes principales :

```bash
./scripts/up.sh
./scripts/restart.sh
./scripts/down.sh
./scripts/status.sh
./scripts/logs.sh api
./scripts/logs.sh inference
```

---

## Tests automatisés

Smoke test :

```bash
API_KEY="FormdevINF26" ./scripts/smoke_test.sh
```

Benchmark :

```bash
API_KEY="FormdevINF26" N=20 ./scripts/bench.sh
```

---

## Sécurité

Principes appliqués :

### Isolation de l’inférence

Le serveur vLLM **n’est pas exposé publiquement**.

Seule l’API gateway est accessible.

### Authentification

Chaque requête doit fournir l’en-tête :

```text
X-API-Key
```

Les clés autorisées sont définies dans `.env`.

### Rate limiting

Limitation :

```text
30 requêtes / minute / client
```

Protection contre :

- abus d’API
- saturation GPU

### Firewall

Le serveur utilise **UFW**.

Ports autorisés :

| port | usage |
|------|-------|
| `22` | SSH |
| `8080` | API FormDev |
| `8000` | vLLM (interne uniquement) |

Tous les autres ports sont bloqués.

---

## Évolutions prévues

L’infrastructure est conçue pour accueillir d’autres services IA.

Projets futurs :

- RAG multi-documents
- analyse de satisfaction
- classification automatique
- base d’exemples pédagogiques

Services à ajouter :

- Postgres
- Qdrant (vector database)
- Redis + workers
