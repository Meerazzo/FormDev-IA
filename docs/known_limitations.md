# Limitations connues — FormDev IA

Dernière mise à jour : 2026-06-25

Ce document liste les limites connues à la fin de la passe de livraison. Elles ne bloquent pas le smoke test global ni l'utilisation des trois modules principaux, mais elles doivent être connues avant une mise en production plus large.

## 1. Accès Docker selon l'utilisateur local

Sur l'environnement de validation, l'utilisateur standard ne peut pas toujours accéder directement au socket Docker :

```text
permission denied while trying to connect to the Docker daemon socket
```

Contournement utilisé pendant la validation : exécuter les commandes Docker depuis un shell `root` via `su`.

Correction recommandée hors code applicatif : ajouter l'utilisateur local au groupe `docker`, puis rouvrir la session.

```bash
sudo usermod -aG docker <user>
```

## 2. Workers RQ dépendants de Redis

Les workers `worker-survey-*` et `worker-rag-*` n'exposent pas d'endpoint HTTP. Leur healthcheck Docker vérifie donc la connectivité Redis, et non l'exécution complète d'un job métier.

Ce choix corrige le faux état `unhealthy` causé par l'ancien healthcheck API `/health`, mais ne remplace pas un smoke test complet.

Validation recommandée :

```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env ps
./scripts/smoke_test.sh
```

## 3. vLLM et GPU

Le service `inference` repose sur `vllm/vllm-openai` et sur l'accès GPU NVIDIA. Le temps de démarrage, la mémoire VRAM consommée et la latence dépendent fortement :

- du modèle configuré avec `MODEL_ID` ;
- de `MAX_MODEL_LEN` ;
- de la mémoire GPU disponible ;
- du cache Hugging Face local.

Le smoke test valide que l'inférence répond, mais ne garantit pas un comportement stable en charge élevée.

## 4. Image vLLM non pinée

Le compose utilise encore :

```yaml
image: vllm/vllm-openai:latest
```

Pour une production plus stricte, il faudra pinner une version afin d'éviter des changements de comportement lors des prochains pulls Docker.

## 5. Graylog optionnel mais pas encore exploité comme dashboard final

Graylog, Mongo et OpenSearch sont isolés via le profil `observability`. L'infrastructure est présente, mais les vues d'exploitation ne sont pas encore finalisées.

À faire pour une exploitation plus complète :

- vérifier les logs structurés Chat, Surveys et RAG ;
- créer des vues erreurs 4xx/5xx ;
- créer des vues latence par module ;
- créer des vues par `client_id`, `corpus_id`, `processing_id`, `source_id` et `conversation_id` quand disponibles.

## 6. Données de test et nettoyage dev

Le smoke test supprime la source RAG qu'il crée, mais certaines données de validation peuvent rester selon les scénarios testés manuellement :

- conversations RAG de test ;
- jobs Survey terminés ;
- feedbacks Survey de test ;
- fichiers RAG temporaires si une commande manuelle échoue avant cleanup ;
- points Qdrant orphelins en cas d'arrêt brutal pendant une indexation.

Une procédure ou un script `cleanup_dev_data` reste à créer pour purger proprement l'environnement dev.

## 7. Tests automatisés et CI

Le dépôt contient un smoke test global shell validé manuellement, mais pas encore :

- suite pytest complète ;
- CI GitHub Actions ;
- collection Postman ou Bruno ;
- test de charge k6 ou Locust.

Le smoke test reste la validation de référence pour cette livraison.

## 8. Charge et concurrence

Les trois modules principaux ont été validés fonctionnellement ensemble, mais pas encore sous charge réelle multi-utilisateurs.

Avant une production plus large, il faudra tester :

- plusieurs appels `/v1/chat` en parallèle ;
- plusieurs appels `/rag/chat` en parallèle ;
- upload et indexation RAG concurrents ;
- plusieurs analyses Survey simultanées ;
- saturation vLLM/GPU ;
- comportement des queues RQ sous backlog.

## 9. Qdrant client / serveur

Un warning de compatibilité mineure peut apparaître dans les logs Survey :

```text
Qdrant client version 1.14.2 is incompatible with server version 1.17.1
```

Le traitement Survey fonctionne malgré ce warning pendant la validation, mais il faudra aligner les versions `qdrant-client` et serveur Qdrant pour supprimer ce bruit et réduire le risque de divergence API.

## 10. ReDoc désactivé volontairement

`/redoc` retourne `404` volontairement. La documentation interactive de référence est Swagger UI :

```text
/docs
```

Le schéma OpenAPI reste disponible ici :

```text
/openapi.json
```

## 11. Refactor RAG non réalisé

Le router RAG reste encore relativement volumineux. Le découpage suivant reste une amélioration possible :

```text
apps/api/routers/rag/
  health.py
  sources.py
  corpora.py
  search.py
  chat.py
  conversations.py
  jobs.py
```

Ce refactor n'est pas bloquant pour la livraison actuelle, car le smoke test global valide les routes principales.
