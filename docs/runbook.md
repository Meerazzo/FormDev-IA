# Runbook — FormDev IA (Lot 0)

## Objectif
Lot 0 fournit un socle exécutable :
- un moteur d’inférence local (vLLM sur GPU)
- une API gateway (FastAPI) avec auth + rate limiting
- déploiement via Docker Compose

## Démarrage / arrêt

### Démarrer
```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d --build
docker compose -f infra/docker-compose.yml ps
```

### Arrêter
```bash
docker compose -f infra/docker-compose.yml down
```

### Redémarrer
```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
```

## Tests rapides
### Health
```bash
curl -s http://localhost:8080/health
```
### Smoke test
```bash
API_KEY="..." ./scripts/smoke_test.sh
```

## Logs
### API
```bash
docker compose -f infra/docker-compose.yml logs -f api
```

### Inference (vLLM)
```bash
docker compose -f infra/docker-compose.yml logs -f inference
```


## Dépannage

Le modèle ne se télécharge pas (HF gating)

Symptômes : 

### 401/403, “gated repo”, “must accept license”.
Actions :
- choisir un modèle non-gated (ex: Qwen2.5 instruct)
- ou fournir un token HF et accepter la licence sur Hugging Face

### OOM / VRAM insuffisante

Actions :
- réduire MAX_MODEL_LEN (ex: 2048)
- changer DTYPE/quantization (selon runtime)
- réduire la concurrence / batch

### GPU non visible dans Docker

Tester :
```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```
Si échec : 
- vérifier NVIDIA Container Toolkit / config Docker runtime.

