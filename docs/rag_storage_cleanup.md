# Nettoyage stockage RAG

Dernière mise à jour : 2026-06-25

## Objectif

Limiter l'accumulation de fichiers locaux créés pendant l'ingestion RAG sans casser la recherche documentaire ni la réindexation.

## Politique retenue

Mode sûr par défaut :

```text
Après indexation réussie :
- retrait du fichier original uploadé ;
- conservation du fichier .chunks.json ;
- conservation des points Qdrant ;
- conservation des métadonnées PostgreSQL.
```

Cette politique réduit le stockage local tout en gardant `reindex` et `resync` fonctionnels.

## Pourquoi garder `.chunks.json` ?

La réindexation relit les chunks depuis ce fichier avant de recalculer les embeddings et de remplacer les points Qdrant.

Sans ce fichier, les opérations suivantes ne peuvent plus fonctionner pour les fichiers uploadés :

```text
POST /rag/sources/{source_id}/reindex
POST /rag/corpora/resync
```

## Cycle de vie d'une source

Lors du retrait d'une source via :

```text
DELETE /rag/sources/{source_id}
```

le service traite aussi les artefacts locaux associés :

```text
- fichier original s'il existe encore ;
- fichier .chunks.json ;
- points Qdrant associés.
```

Puis la source est marquée en suppression logique dans PostgreSQL.

## Métadonnées

Chaque traitement ajoute une entrée dans `metadata_json.storage_cleanup` et conserve l'historique dans `metadata_json.storage_cleanup_history`.

Exemple :

```json
{
  "trigger": "index_success",
  "policy": "delete_original_keep_chunks",
  "deleted_paths": ["/data/rag/client/document.pdf"],
  "chunks_file_kept": true,
  "reindex_available": true
}
```

## Sécurité

Le service ne traite que des chemins locaux absolus situés sous `RAG_STORAGE_DIR`.

## Validation locale recommandée

Vérifier après upload et indexation :

```text
- source en statut indexed ;
- fichier original absent ;
- fichier .chunks.json présent ;
- search RAG OK ;
- chat RAG OK ;
- reindex OK ;
- retrait de source OK avec nettoyage du .chunks.json.
```
