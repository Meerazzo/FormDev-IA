# Documentation client technique — Surveys

## Routes

```text
POST /surveys/analyze
GET  /surveys/processings/{processing_id}
POST /surveys/feedback
GET  /surveys/feedback
```

## Authentification

```text
X-API-Key: <clé_api>
```

## Lancer une analyse

```bash
curl -s -X POST "$API/surveys/analyze" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "questionnaires": [
      {
        "id": 1,
        "availableCategories": [
          {"id": 10, "label": "Satisfaction", "metadata": {}},
          {"id": 11, "label": "Amélioration", "metadata": {}}
        ],
        "questions": [
          {
            "id": 100,
            "label": "Avez-vous des suggestions ?",
            "type": "OPEN",
            "answers": [
              {
                "id": 2000,
                "type": "FREE_TEXT",
                "label": "Très bonne formation, mais davantage d'exercices seraient utiles.",
                "metadata": {}
              }
            ],
            "metadata": {}
          }
        ],
        "metadata": {
          "client_id": "client_demo"
        }
      }
    ]
  }' | jq
```

## Réponse de création

```json
{
  "processing_id": "...",
  "status": "QUEUED"
}
```

Le statut peut aussi être `RECEIVED` si le job a été enregistré mais que l'envoi vers Redis/RQ n'a pas abouti.

## Suivre le traitement

```bash
curl -s "$API/surveys/processings/$PROCESSING_ID?client_id=client_demo" \
  -H "X-API-Key: $KEY" | jq
```

## Statuts

| Statut | Signification |
| --- | --- |
| `RECEIVED` | Traitement reçu |
| `QUEUED` | Traitement envoyé dans Redis/RQ |
| `STARTED` | Worker en cours |
| `FINISHED` | Résultat disponible |
| `FAILED` | Erreur |

## Feedback opérateur

```bash
curl -s -X POST "$API/surveys/feedback?client_id=client_demo" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "response_id": "response_123",
    "operator_id": "operator_1",
    "metadata": {
      "review_source": "manual_review"
    },
    "points": [
      {
        "point_id": "response_123_pt_1",
        "is_correct": false,
        "corrected_text": "Plus d'exercices pratiques souhaités",
        "corrected_sentiment": 2,
        "corrected_category": "Amélioration",
        "action": "update"
      }
    ]
  }' | jq
```

## Actions de feedback

| Action | Effet |
| --- | --- |
| `update` | Valide ou corrige un point existant |
| `delete` | Supprime/désactive un point non pertinent |
| `add` | Ajoute un point manuel non détecté par le modèle |

## Mémoire Qdrant

Les feedbacks validés peuvent alimenter Qdrant pour améliorer les classifications futures par similarité d'exemples.

La mémoire Survey est distincte du RAG documentaire. Elle sert aux few-shots dynamiques de classification.

## Erreurs fréquentes

| Code | Cause probable |
| --- | --- |
| 401 | Clé API absente ou invalide |
| 422 | `metadata.client_id` absent ou incohérent |
| 429 | Rate limit atteint |
| 502 | Erreur d'inférence ou de traitement |

## Bonnes pratiques d'intégration

- Toujours fournir `metadata.client_id` sur chaque questionnaire.
- Ne pas mélanger plusieurs clients dans une même requête.
- Stocker le `processing_id` côté CRM/front.
- Interroger `GET /surveys/processings/{processing_id}` jusqu'à `FINISHED` ou `FAILED`.
- Envoyer les corrections opérateur via `/surveys/feedback` pour améliorer les futures analyses.
