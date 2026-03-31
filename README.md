# FormDev IA — Infrastructure IA locale & API intelligente

## 1. Présentation

FormDev IA est une infrastructure d’intelligence artificielle déployée localement (on-premise ou cloud privé type OVH) permettant d’exposer des capacités LLM via une API sécurisée.

Cette infrastructure constitue le **socle IA de la plateforme FormDev** et permet d’intégrer directement des fonctionnalités avancées dans l’ERP :

- génération de contenu pédagogique
- assistance conversationnelle
- analyse de données textuelles
- analyse de questionnaires de satisfaction
- futurs pipelines RAG

Le système repose sur un **modèle open source exécuté localement sur GPU**, garantissant :

- contrôle total des données
- latence maîtrisée
- indépendance vis-à-vis d’API externes

---

## 2. Architecture générale

L’architecture repose sur une séparation claire entre :

- **inférence IA (GPU)**
- **API gateway (logique métier + sécurité)**

### Composants

#### inference
- serveur **vLLM**
- moteur d’inférence GPU
- compatible OpenAI API

#### api
- **FastAPI**
- authentification par clé API
- rate limiting
- logique métier
- journalisation PostgreSQL

#### postgres
- stockage des logs IA
- stockage des données métier (questionnaires)

---

### Schéma

```text
ERP / Extranet
      │
      ▼
API Gateway (FastAPI)
      │
      ▼
Serveur vLLM
      │
      ▼
GPU
```

⚠️ Le serveur vLLM n’est **jamais exposé directement**.

---

## 3. Fonctionnalités

## 3.1 Endpoint `/v1/chat`

Interface compatible OpenAI Chat API.

Permet :
- reformulation
- synthèse
- enrichissement
- génération encadrée

### ⚠️ Important

Le prompt système est **contrôlé côté backend**.

➡️ Les messages `system` envoyés par le client sont ignorés.

---

### Exemple requête

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Explique ce qu'est un style dans Word."
    }
  ],
  "max_tokens": 150
}
```

---

### Exemple réponse

```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
  "content": "Un style dans Word permet d'appliquer automatiquement une mise en forme cohérente.",
  "usage": {
    "prompt_tokens": 40,
    "completion_tokens": 15,
    "total_tokens": 55
  },
  "latency_ms": 820
}
```

---

## 3.2 Endpoint `/surveys/analyze`

Analyse une réponse ouverte de questionnaire.

### Pipeline

1. nettoyage texte
2. détection cas vides (RAS, néant…)
3. segmentation en points
4. classification :
   - sentiment
   - catégorie métier
5. stockage en base

---

### Exemple requête

```json
{
  "survey_id": "formation_word",
  "question_id": "q1",
  "question_text": "Ce que vous avez particulièrement apprécié :",
  "response_text": "Petit groupe, tout le monde peut prendre la parole. Formateur clair.",
  "metadata": {
    "client": "Entreprise X"
  }
}
```

---

### Exemple réponse

```json
{
  "response_id": "uuid",
  "points": [
    {
      "point_id": "uuid_pt_1",
      "text": "Petit groupe, tout le monde peut prendre la parole.",
      "sentiment": "positive",
      "category": "pedagogie",
      "confidence": null
    }
  ]
}
```

---

## 4. Multi-utilisateurs & performance

vLLM utilise un **KV cache paginé** :

- mémoire GPU partagée
- batching automatique
- exécution concurrente

➡️ permet de servir plusieurs utilisateurs simultanément

---

## 5. Base de données

### Tables principales

#### ai_interactions
- logs complets IA
- tokens, latence, erreurs

#### survey_responses
- réponses brutes

#### response_points
- points extraits + classification

#### point_feedback (future)
- corrections opérateur

---

## 6. Sécurité

### Authentification

Header obligatoire :

```
X-API-Key
```

---

### Rate limiting

Actuellement :
```
30 requêtes / minute / IP
```

⚠️ (évolutif vers par client)

---

### Isolation

- vLLM non exposé
- API gateway obligatoire

---

### Firewall

Ports :

| port | usage |
|------|------|
| 22 | SSH |
| 8080 | API |
| 8000 | vLLM interne |

---

## 7. Prérequis

- Linux
- Docker + Compose
- GPU NVIDIA
- NVIDIA Container Toolkit

```bash
nvidia-smi
```

---

## 8. Installation

### 1. Config

```bash
cp infra/.env.example infra/.env
```

---

### 2. Lancement

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

---

### 3. Vérification

```bash
curl http://localhost:8080/health
```

---

## 9. Configuration (.env)

| variable | description |
|----------|------------|
| API_KEYS | clés autorisées |
| RATE_LIMIT_RPM | limite |
| MODEL_ID | modèle |
| MAX_MODEL_LEN | contexte |
| DTYPE | précision |
| API_PORT | port API |

---

## 10. Logs

```bash
docker compose logs -f api
docker compose logs -f inference
```

---

## 11. Monitoring GPU

```bash
nvidia-smi
```

---

## 12. Scripts

```bash
./scripts/up.sh
./scripts/restart.sh
./scripts/logs.sh
```

---

## 13. Bonnes pratiques

- centraliser la config
- éviter les prompts en dur
- privilégier JSON strict
- préférer "unknown" à erreur

---

## 14. Roadmap

- feedback opérateur
- few-shot dynamique
- batch 1M réponses
- RAG
- vector DB (Qdrant)
- workers async

