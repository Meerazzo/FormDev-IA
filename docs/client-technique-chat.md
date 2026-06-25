# Documentation client technique — Chat IA

## Route

```text
POST /v1/chat
```

## Authentification

```text
X-API-Key: <clé_api>
```

## Usage

Cette route sert à générer, reformuler, résumer ou enrichir du texte via le modèle LLM servi par vLLM.

Cas d'usage typiques :

- reformulation professionnelle ;
- synthèse ;
- génération de contenu pédagogique ;
- enrichissement de texte ;
- correction optionnelle en seconde passe.

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

## Paramètres principaux

| Champ | Rôle |
| --- | --- |
| `messages` | Conversation envoyée au modèle |
| `system_prompt` | Prompt système optionnel |
| `temperature` | Niveau de créativité |
| `top_p` | Diversité de génération |
| `max_tokens` | Taille maximale de réponse |
| `post_correction` | Active une seconde passe de correction |
| `post_correction_prompt` | Prompt optionnel pour la correction |

## Réponse

La réponse contient le texte généré et les métadonnées d'usage disponibles.

## Erreurs fréquentes

| Code | Cause probable |
| --- | --- |
| 401 | Clé API absente ou invalide |
| 429 | Rate limit atteint |
| 502 | vLLM indisponible ou erreur upstream |

## Bonnes pratiques d'intégration

- Mettre l'instruction principale dans le message `user`.
- Utiliser `temperature=0.2` pour les usages métier stables.
- Limiter `max_tokens` pour éviter des réponses trop longues.
- Activer `post_correction` seulement si une seconde inférence est acceptable en coût/latence.
