# Documentation client technique — Surveys

Cette page décrit le contrat d'intégration du module Surveys pour un CRM ou un front client.

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
Content-Type: application/json
```

## Principe d'intégration

Cycle standard côté CRM :

```text
1. Envoyer les questionnaires avec POST /surveys/analyze
2. Stocker le processing_id retourné
3. Poller GET /surveys/processings/{processing_id}?client_id=...
4. Quand status=FINISHED, lire result.questionnaires
5. Afficher les segments à l'opérateur
6. Envoyer les corrections via POST /surveys/feedback?client_id=...
```

## Payload d'entrée — analyse

```json
{
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
        "client_id": "client_demo",
        "formation": "Formation sécurité"
      }
    }
  ]
}
```

## Champs d'entrée principaux

| Champ | Type | Obligatoire | Rôle |
| --- | --- | --- | --- |
| `questionnaires` | array | oui | Liste des questionnaires à analyser. |
| `questionnaires[].id` | integer/string | oui | Identifiant métier du questionnaire. |
| `questionnaires[].metadata.client_id` | string | oui | Client propriétaire des données. Tous les questionnaires de la requête doivent avoir le même client. |
| `availableCategories` | array | oui | Catégories autorisées pour la classification. |
| `availableCategories[].id` | integer | oui | Identifiant catégorie restitué dans `segments[].categoryId`. |
| `availableCategories[].label` | string | oui | Libellé utilisé par le modèle pour choisir la catégorie. |
| `questions` | array | oui | Questions du questionnaire. |
| `questions[].id` | integer/string | oui | Identifiant métier de la question. |
| `questions[].label` | string | oui | Texte de la question. |
| `questions[].type` | string | oui | `OPEN`, `SINGLE_CHOICE`, `MULTIPLE_CHOICE`, `RATING`, `CHECKBOX`. |
| `answers` | array | selon type | Réponses multiples ou réponse ouverte. |
| `answer` | object/null | selon type | Réponse unique pour certains types. |
| `availableAnswers` | array | selon type | Choix possibles pour les questions fermées. |

## Réponse de création

```json
{
  "processing_id": "1f11aa54-a688-43c5-9fd4-9cf09c33364b",
  "status": "QUEUED"
}
```

Le statut peut aussi être `RECEIVED` si le job a été enregistré mais que l'envoi vers Redis/RQ n'a pas abouti.

## Suivre le traitement

```bash
curl -s "$API/surveys/processings/$PROCESSING_ID?client_id=client_demo" \
  -H "X-API-Key: $KEY" | jq
```

## Réponse de suivi

Pendant le traitement :

```json
{
  "processing_id": "...",
  "status": "QUEUED",
  "survey_id": "client_questionnaires",
  "error_message": null,
  "result": null
}
```

Une fois terminé, `result` reprend les questionnaires d'entrée et ajoute les segments :

```json
{
  "processing_id": "...",
  "status": "FINISHED",
  "survey_id": "client_questionnaires",
  "error_message": null,
  "result": {
    "questionnaires": [
      {
        "id": 1,
        "questions": [
          {
            "id": 100,
            "answers": [
              {
                "id": 2000,
                "response_id": "response_demo",
                "segments": [
                  {
                    "text": "Formation appréciée",
                    "point_id": "response_demo_pt_1",
                    "sentiment": "POSITIVE",
                    "categoryId": 10
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

## Champs ajoutés par l'API

| Champ | Rôle |
| --- | --- |
| `response_id` | Identifiant technique de la réponse analysée. À conserver pour le feedback. |
| `segments` | Liste des points détectés dans une réponse. |
| `segments[].point_id` | Identifiant technique du point. À renvoyer dans `/surveys/feedback`. |
| `segments[].text` | Texte final exploitable par le CRM. |
| `segments[].sentiment` | Sentiment public : `VERY_NEGATIVE`, `NEGATIVE`, `NEUTRAL`, `POSITIVE`, `VERY_POSITIVE`. |
| `segments[].categoryId` | ID d'une catégorie fournie dans `availableCategories`. |

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
    "response_id": "response_demo",
    "operator_id": "crm_user",
    "metadata": {
      "review_source": "manual_review"
    },
    "points": [
      {
        "point_id": "response_demo_pt_1",
        "is_correct": false,
        "corrected_text": "Plus d exercices pratiques souhaités",
        "corrected_sentiment": 2,
        "corrected_category": "Amélioration",
        "action": "update"
      }
    ]
  }' | jq
```

## Payload de feedback

| Champ | Type | Obligatoire | Rôle |
| --- | --- | --- | --- |
| `response_id` | string | oui | Identifiant de la réponse à corriger. |
| `operator_id` | string/null | non | Identifiant opérateur ou utilisateur CRM. |
| `metadata` | object | non | Métadonnées CRM libres. |
| `points` | array | oui | Points à valider/corriger/supprimer/ajouter. |
| `points[].point_id` | string/null | oui sauf `add` | Identifiant du segment. Peut être null pour `action=add`. |
| `points[].is_correct` | boolean | oui | `true` si le point est validé tel quel. |
| `points[].corrected_text` | string/null | non | Texte corrigé. |
| `points[].corrected_sentiment` | integer/null | non | Sentiment corrigé sur échelle 1 à 5. |
| `points[].corrected_category` | string/null | non | Libellé catégorie corrigé. |
| `points[].action` | string | oui | `update`, `delete` ou `add`. |

## Réponse feedback

```json
{
  "response_id": "response_demo",
  "saved_feedback_count": 1,
  "status": "ok"
}
```

## Actions de feedback

| Action | Effet |
| --- | --- |
| `update` | Valide ou corrige un point existant. |
| `delete` | Supprime/désactive un point non pertinent. |
| `add` | Ajoute un point manuel non détecté par le modèle. |

## Mémoire Qdrant

Les feedbacks validés peuvent alimenter Qdrant pour améliorer les classifications futures par similarité d'exemples.

La mémoire Survey est distincte du RAG documentaire. Elle sert aux few-shots dynamiques de classification.

## Erreurs fréquentes

| Code | Cause probable | Action CRM |
| --- | --- | --- |
| 401 | Clé API absente ou invalide | Vérifier le header `X-API-Key`. |
| 404 | `processing_id`, `response_id` ou point introuvable | Rafraîchir l'état ou vérifier le client. |
| 422 | `metadata.client_id` absent ou incohérent | Vérifier que tous les questionnaires ont le même client. |
| 429 | Rate limit atteint | Réduire le polling ou retenter plus tard. |
| 502 | Erreur d'inférence, Qdrant ou traitement | Afficher une erreur temporaire et retenter. |

## Bonnes pratiques d'intégration

- Toujours fournir `metadata.client_id` sur chaque questionnaire.
- Ne pas mélanger plusieurs clients dans une même requête.
- Stocker le `processing_id` côté CRM/front.
- Poller raisonnablement `GET /surveys/processings/{processing_id}` jusqu'à `FINISHED` ou `FAILED`.
- Stocker `response_id` et `point_id` pour permettre la relecture opérateur.
- Envoyer les corrections opérateur via `/surveys/feedback` pour améliorer les futures analyses.
