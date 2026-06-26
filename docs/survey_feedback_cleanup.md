# Nettoyage Survey après feedback

Dernière mise à jour : 2026-06-25

## Objectif

Réduire les données conservées en PostgreSQL après validation ou correction opérateur.

Le module Survey possède déjà un mécanisme de purge contrôlé par la variable :

```text
SURVEY_PURGE_AFTER_FEEDBACK
```

Quand elle vaut `true`, le feedback opérateur est d'abord transformé en exemple validé dans Qdrant, puis les données PostgreSQL liées aux points feedbackés sont retirées.

## Comportement

Après un feedback :

```text
- l'exemple opérateur est ajouté ou mis à jour dans Qdrant ;
- le résultat du processing est synchronisé avec les corrections ;
- les points concernés sont retirés des tables PostgreSQL ;
- si une réponse n'a plus aucun point actif, la réponse est aussi retirée.
```

Cette approche évite de perdre l'information utile pour l'apprentissage dynamique, car la mémoire opérateur reste dans Qdrant.

## Activation locale

Un helper est fourni :

```bash
bash scripts/enable_survey_purge_after_feedback.sh
```

Il met à jour `infra/.env` avec :

```text
SURVEY_PURGE_AFTER_FEEDBACK=true
```

Puis il faut redémarrer les services concernés :

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --force-recreate --no-build api-dev worker-survey-dev
```

## Validation locale recommandée

1. Lancer une analyse Survey.
2. Attendre le statut `FINISHED`.
3. Envoyer un feedback sur un `point_id`.
4. Vérifier que le feedback répond `status=ok`.
5. Vérifier que l'exemple est consultable dans la mémoire Qdrant Survey.
6. Vérifier que les points PostgreSQL concernés ne sont plus présents.
7. Vérifier qu'un second feedback reste possible grâce à la mémoire Qdrant.

## Limite volontaire

La purge n'est pas faite immédiatement après `FINISHED`, car le client doit pouvoir récupérer le résultat via :

```text
GET /surveys/processings/{processing_id}
```

Le nettoyage intervient après feedback opérateur, quand le résultat a été revu et converti en exemple exploitable.
