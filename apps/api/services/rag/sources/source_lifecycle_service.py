import logging

from sqlalchemy.orm import Session

from schemas.rag import RagDeleteSourceResponse
from services.rag.sources.source_repository import RagSourceRepository
from services.rag.storage.local_artifact_cleanup import RagLocalArtifactCleanup
from services.rag.vectorstore.rag_vector_store import RagVectorStore

logger = logging.getLogger("formdev_ia_api")


class RagSourceLifecycleService:
    """
    Gère le cycle de vie d'une source RAG.

    Suppression :
    - suppression des artefacts locaux si présents ;
    - suppression des points associés dans Qdrant ;
    - suppression logique en base.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.source_repository = RagSourceRepository(db)
        self.vector_store = RagVectorStore()
        self.artifact_cleanup = RagLocalArtifactCleanup(db)

    def delete_source(
        self,
        source_id: str,
        *,
        client_id: str | None = None,
        corpus_id: str | None = None,
        ensure_cleanup: bool = False,
    ) -> RagDeleteSourceResponse:

        if client_id is not None:
            source = self.source_repository.get_for_client(
                source_id=source_id,
                client_id=client_id,
                corpus_id=corpus_id,
                include_deleted=True,
            )
        else:
            source = self.source_repository.get_by_source_id(
                source_id
            )

        if source is None:
            raise ValueError("Source RAG introuvable")

        already_deleted = source.status == "deleted"

        if already_deleted and not ensure_cleanup:
            return RagDeleteSourceResponse(
                source_id=source.source_id,
                client_id=source.client_id,
                corpus_id=source.corpus_id,
                status=source.status,
                qdrant_points_deleted=False,
                message="Source déjà supprimée",
            )

        # Qdrant d'abord :
        # si Qdrant échoue, on ne perd pas les fichiers locaux.
        self.vector_store.delete_source(
            client_id=source.client_id,
            corpus_id=source.corpus_id,
            source_id=source.source_id,
        )

        cleanup_report = {}

        try:
            cleanup_report = (
                self.artifact_cleanup.on_source_delete(source)
            )

        except Exception as cleanup_error:
            logger.warning(
                "RAG artifact cleanup failed during source delete",
                extra={
                    "event_type":
                        "rag_artifact_cleanup_failed",
                    "service_name":
                        "formdev-api",
                    "app_module":
                        "rag",
                    "route_family":
                        "rag_sources",
                    "client_id":
                        source.client_id,
                    "corpus_id":
                        source.corpus_id,
                    "source_id":
                        source.source_id,
                    "source_type":
                        source.source_type,
                    "error_type":
                        cleanup_error.__class__.__name__,
                    "error_message":
                        str(cleanup_error),
                },
            )

        if not already_deleted:
            self.source_repository.mark_deleted(source_id)
            self.db.refresh(source)

        logger.info(
            "rag source deleted",
            extra={
                "event_type": "rag_source_deleted",
                "service_name": "formdev-api",
                "app_module": "rag",
                "route_family": "rag_sources",
                "client_id": source.client_id,
                "corpus_id": source.corpus_id,
                "source_id": source.source_id,
                "source_type": source.source_type,
                "already_deleted": already_deleted,
                "qdrant_points_deleted": True,
                "local_artifacts_deleted_count": len(
                    cleanup_report.get(
                        "deleted_paths", []
                    )
                )
                if cleanup_report
                else 0,
            },
        )

        return RagDeleteSourceResponse(
            source_id=source.source_id,
            client_id=source.client_id,
            corpus_id=source.corpus_id,
            status=source.status,
            qdrant_points_deleted=True,
            message=(
                "Source déjà supprimée ; nettoyage réconcilié"
                if already_deleted
                else "Source supprimée logiquement, points Qdrant "
                    "et artefacts locaux nettoyés"
            ),
        )