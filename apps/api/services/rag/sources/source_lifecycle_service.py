import logging

from sqlalchemy.orm import Session

from schemas.rag import RagDeleteSourceResponse
from services.rag.sources.source_repository import RagSourceRepository
from services.rag.storage.local_artifact_cleanup import RagLocalArtifactCleanup
from services.rag.vectorstore.rag_vector_store import RagVectorStore

logger = logging.getLogger(__name__)


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

    def delete_source(self, source_id: str) -> RagDeleteSourceResponse:
        source = self.source_repository.get_by_source_id(source_id)

        if source is None:
            raise ValueError("Source RAG introuvable")

        if source.status == "deleted":
            return RagDeleteSourceResponse(
                source_id=source.source_id,
                client_id=source.client_id,
                corpus_id=source.corpus_id,
                status=source.status,
                qdrant_points_deleted=False,
                message="Source déjà supprimée",
            )

        try:
            self.artifact_cleanup.on_source_delete(source)
        except Exception as cleanup_error:
            logger.warning(
                "RAG artifact cleanup failed during source delete "
                "(source_id=%s): %s",
                source.source_id,
                str(cleanup_error),
            )

        self.vector_store.delete_source(
            client_id=source.client_id,
            corpus_id=source.corpus_id,
            source_id=source.source_id,
        )

        self.source_repository.mark_deleted(source_id)

        self.db.refresh(source)

        return RagDeleteSourceResponse(
            source_id=source.source_id,
            client_id=source.client_id,
            corpus_id=source.corpus_id,
            status=source.status,
            qdrant_points_deleted=True,
            message="Source supprimée logiquement, points Qdrant supprimés et artefacts locaux nettoyés si présents",
        )
