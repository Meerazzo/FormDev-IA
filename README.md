# FormDev IA — Lot 0 (Socle infrastructure)

Backend IA on-prem (ou OVH) exposé **uniquement via API** pour :
- Projet 1 : Chatbot RAG multi-clients
- Projet 2 : Enrichissement de contenus
- Projet 3 : Analyse de satisfaction + boucle de feedback

> Lot 0 = socle commun : GPU + moteur d’inférence local + API gateway sécurisée + outillage minimal.

---

## Architecture (Lot 0)

- **inference** : vLLM (serveur OpenAI-compatible) chargé sur GPU
- **api** : FastAPI (gateway FormDev)
  - Auth par clé API
  - Rate limiting
  - Proxy vers vLLM

Schéma :
ERP / Extranet → **API FastAPI** → vLLM (GPU)

⚠️ Important : l’ERP ne doit jamais appeler vLLM directement. Seule l’API gateway est exposée.

---

## Prérequis

- Linux (Debian/Ubuntu)
- Docker + Docker Compose
- GPU NVIDIA + driver OK (`nvidia-smi`)
- NVIDIA Container Toolkit pour GPU dans Docker

---

## Démarrage rapide

1) Créer la configuration :
```bash
cp infra/.env.example infra/.env
nano infra/.env 
```

2) Lancer :
```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d --build
docker compose -f infra/docker-compose.yml ps
```

3) Verifier :
```bash
curl -s http://localhost:8080/health
```

4) Test chat :
```bash
API_KEY="FormdevINF26"
curl -s http://localhost:8080/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role":"user","content":"Dis bonjour en une phrase."}],
    "max_tokens": 60
  }'
```

## Configuration (.env)

Variables principales :

- API_KEYS : clés API autorisées. Format : clientA:key1,clientB:key2
- RATE_LIMIT_RPM : limite de requêtes/minute (protection GPU)
- MODEL_ID : modèle Hugging Face servi par vLLM
- MAX_MODEL_LEN : taille contexte max vLLM
- DTYPE : half recommandé
- API_PORT : port de l’API (par défaut 8080)
- VLLM_PORT : port interne vLLM (par défaut 8000)
- HF_CACHE : cache HF (par défaut /root/.cache/huggingface)

## Logs & debug

1) log API: 
```bash
docker compose -f infra/docker-compose.yml logs -f api
```

2) log inference :
```bash
docker compose -f infra/docker-compose.yml logs -f inference
```

3) État GPU :
```bash
nvidia-smi
```

## Évolution (Projets 1/2/3)

Le Lot 0 est conçu pour accueillir 3 pipelines côté API :

- /rag/ : ingestion docs/urls, indexation embeddings, chat RAG multi-tenant

- /content/ : enrichissement de texte

- /surveys/ : segmentation + sentiment + catégories + feedback


Les prochains services prévus (ajoutés au compose au moment venu) :

- Postgres (métadonnées, statuts, résultats)

- Qdrant (vector DB : documents + exemples corrigés)

- Redis + worker (jobs ingestion/batch)


## Sécurité (rappels)

- Ne pas exposer vLLM publiquement : seul le port API doit être accessible.

- Ne pas commiter infra/.env (contient des secrets).

- UFW recommandé (deny incoming par défaut, autoriser SSH + API).

