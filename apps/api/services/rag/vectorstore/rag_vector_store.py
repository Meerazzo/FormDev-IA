from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from core.config import settings


class RagVectorStore:
    """
    Service minimal d'accès à Qdrant pour le RAG documentaire.

    Jour 1 :
    - vérification de connexion ;
    - création de collection ;
    - création des index payload utiles.

    Les méthodes d'indexation, recherche et suppression seront ajoutées
    dans les jours suivants.
    """

    def __init__(
        self,
        qdrant_url: str | None = None,
        collection_name: str | None = None,
        vector_size: int | None = None,
    ) -> None:
        self.qdrant_url = qdrant_url or settings.QDRANT_URL
        self.collection_name = collection_name or settings.RAG_QDRANT_COLLECTION
        self.vector_size = vector_size or settings.RAG_VECTOR_SIZE
        self.client = QdrantClient(url=self.qdrant_url)

    def collection_exists(self) -> bool:
        return self.client.collection_exists(self.collection_name)

    def ensure_collection(self) -> None:
        """
        Crée la collection RAG si elle n'existe pas.

        La collection est séparée de la collection survey_feedback_examples afin
        de ne pas mélanger la mémoire documentaire et les exemples validés des
        questionnaires.
        """
        if not self.collection_exists():
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self) -> None:
        """
        Crée les index payload utiles au filtrage multi-client.

        Les exceptions sont ignorées volontairement afin de rendre l'opération
        idempotente : Qdrant peut renvoyer une erreur si l'index existe déjà.
        """
        indexes: list[tuple[str, models.PayloadSchemaType]] = [
            ("client_id", models.PayloadSchemaType.KEYWORD),
            ("corpus_id", models.PayloadSchemaType.KEYWORD),
            ("source_id", models.PayloadSchemaType.KEYWORD),
            ("source_type", models.PayloadSchemaType.KEYWORD),
            ("source_name", models.PayloadSchemaType.KEYWORD),
            ("is_active", models.PayloadSchemaType.BOOL),
            ("content_hash", models.PayloadSchemaType.KEYWORD),
            ("created_at", models.PayloadSchemaType.DATETIME),
        ]

        for field_name, field_schema in indexes:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                )
            except Exception:
                pass

    def health(self) -> dict[str, Any]:
        """
        Retourne un état minimal de Qdrant pour /rag/health.
        """
        try:
            exists = self.collection_exists()
            return {
                "available": True,
                "collection_exists": exists,
                "error": None,
            }
        except Exception as exc:
            return {
                "available": False,
                "collection_exists": None,
                "error": str(exc),
            }