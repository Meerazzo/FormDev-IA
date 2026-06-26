# Documentation client technique — Chat IA

Cette page décrit ce qu'un CRM/front doit envoyer à l'API Chat et ce qu'il peut attendre en retour.

## Route

```text
POST /v1/chat
```

## Authentification

Toutes les requêtes doivent fournir la clé API client :

```text
X-API-Key: <clé_api>
Content-Type: application/json
```

## Usage attendu côté CRM

La route sert à générer, reformuler, résumer, enrichir ou corriger du texte via le modèle LLM servi par vLLM.

Cas d'usage typiques :

- reformulation professionnelle ;
- synthèse ;
- génération de contenu pédagogique ;
- enrichissement de texte ;
- correction optionnelle en seconde passe.

## Payload d'entrée

```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
  "messages": [
    {
      "role": "user",
      "content": "Résume ce texte en 3 phrases claires : ..."
    }
  ],
  "system_prompt": "Tu es un assistant de rédaction professionnelle.",
  "temperature": 0.2,
  "top_p": 0.9,
  "max_tokens": 300,
  "post_correction": false,
  "post_correction_prompt": null
}
```

## Champs d'entrée

| Champ | Type | Obligatoire | Rôle |
| --- | --- | --- | --- |
| `messages` | array | oui | Conversation envoyée au modèle. Au minimum un message `user`. |
| `messages[].role` | string | oui | `user`, `assistant` ou `system`. Les `system` fournis dans l'historique sont remplacés par `system_prompt`. |
| `messages[].content` | string | oui | Texte envoyé au modèle. |
| `model` | string | non | Nom du modèle demandé. Si absent, le backend utilise sa valeur par défaut. |
| `system_prompt` | string | non | Prompt système métier. Permet de cadrer le ton, le rôle et les contraintes. |
| `temperature` | number | non | Niveau de variation. Recommandé : `0.2` pour les usages métier stables. |
| `top_p` | number | non | Diversité de génération. Recommandé : `0.9`. |
| `max_tokens` | integer | non | Longueur maximale de la réponse générée. |
| `post_correction` | boolean | non | Si `true`, lance une seconde inférence de correction linguistique. |
| `post_correction_prompt` | string | non | Prompt spécifique de correction si `post_correction=true`. |

## Réponse de sortie

```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
  "content": "Texte généré par le modèle.",
  "finish_reason": "stop",
  "usage": {
    "prompt_tokens": 323,
    "completion_tokens": 58,
    "total_tokens": 381
  },
  "latency_ms": 167.5
}
```

## Champs de sortie

| Champ | Type | Rôle |
| --- | --- | --- |
| `model` | string | Modèle réellement utilisé par le serveur d'inférence. |
| `content` | string | Texte final à afficher ou stocker côté CRM. |
| `finish_reason` | string/null | Raison d'arrêt du modèle : souvent `stop`, parfois `length`. |
| `usage.prompt_tokens` | integer/null | Tokens consommés par l'entrée. |
| `usage.completion_tokens` | integer/null | Tokens générés. |
| `usage.total_tokens` | integer/null | Total utilisé pour le suivi coût/usage. |
| `latency_ms` | number | Latence totale côté API. |

## Exemple curl

```bash
curl -s -X POST "$API/v1/chat" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Résume ce texte en 3 phrases claires : ..."
      }
    ],
    "temperature": 0.2,
    "top_p": 0.9,
    "max_tokens": 300,
    "post_correction": false
  }' | jq
```

## Erreurs fréquentes

| Code | Cause probable | Action CRM |
| --- | --- | --- |
| 401 | Clé API absente ou invalide | Vérifier le header `X-API-Key`. |
| 422 | Payload invalide | Vérifier `messages`, types et champs numériques. |
| 429 | Rate limit atteint | Retenter plus tard ou limiter les appels. |
| 502 | vLLM indisponible ou erreur upstream | Afficher un message temporaire et retenter. |

## Bonnes pratiques d'intégration

- Mettre l'instruction principale dans le message `user`.
- Utiliser `temperature=0.2` pour les usages métier stables.
- Limiter `max_tokens` pour éviter des réponses trop longues.
- Stocker `usage.total_tokens` si le CRM veut suivre la consommation.
- Activer `post_correction` seulement si une seconde inférence est acceptable en coût/latence.
