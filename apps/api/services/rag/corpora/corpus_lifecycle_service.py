import logging

from sqlalchemy.orm import Session

from schemas.rag import RagCorpusDeleteResponse

from services.rag.conversations.conversation_repository import (
    RagConversationRepository,
)
from services.rag.corpora.corpus_repository import (
    RagCorpusRepository,
)
from services.rag.sources.source_lifecycle_service import (
    RagSourceLifecycleService,
)
from services.rag.sources.source_repository import (
    RagSourceRepository,
)
from services.rag.vectorstore.rag_vector_store import (
    RagVectorStore,
)


logger = logging.getLogger("formdev_ia_api")


class RagCorpusNotFoundError(ValueError):
    pass


class RagCorpusLifecycleService:

    def __init__(self, db: Session) -> None:
        self.db = db

        self.corpus_repository = RagCorpusRepository(db)
        self.source_repository = RagSourceRepository(db)

        self.conversation_repository = (
            RagConversationRepository(db)
        )

        self.source_lifecycle = (
            RagSourceLifecycleService(db)
        )

        self.vector_store = RagVectorStore()

    def delete_corpus(
        self,
        *,
        client_id: str,
        corpus_id: str,
    ) -> RagCorpusDeleteResponse:

        corpus = self.corpus_repository.get_for_client(
            client_id=client_id,
            corpus_id=corpus_id,
        )

        if corpus is None:
            raise RagCorpusNotFoundError(
                "Corpus RAG introuvable"
            )

        try:
            sources = self.source_repository.list_by_corpus(
                client_id=client_id,
                corpus_id=corpus_id,
                include_deleted=True,
            )

            sources_deleted = 0

            for source in sources:

                if source.status != "deleted":
                    sources_deleted += 1

                self.source_lifecycle.delete_source(
                    source.source_id,
                    client_id=client_id,
                    corpus_id=corpus_id,
                    ensure_cleanup=True,
                )

            # Nettoyage défensif :
            # supprime aussi d'éventuels points orphelins.
            self.vector_store.delete_corpus(
                client_id=client_id,
                corpus_id=corpus_id,
            )

            (
                conversations_deleted,
                messages_deleted,
            ) = (
                self.conversation_repository
                .delete_for_corpus(
                    client_id=client_id,
                    corpus_id=corpus_id,
                )
            )

            deactivated = (
                self.corpus_repository.deactivate(
                    client_id=client_id,
                    corpus_id=corpus_id,
                )
            )

            if deactivated is None:
                raise RuntimeError(
                    "Corpus RAG introuvable "
                    "lors de la désactivation"
                )

        except Exception as exc:

            logger.exception(
                "rag corpus delete failed",
                extra={
                    "event_type":
                        "rag_corpus_delete_failed",
                    "service_name":
                        "formdev-api",
                    "app_module":
                        "rag",
                    "route_family":
                        "rag_corpora",
                    "client_id":
                        client_id,
                    "corpus_id":
                        corpus_id,
                    "error_type":
                        exc.__class__.__name__,
                    "error_message":
                        str(exc),
                },
            )

            raise

        logger.info(
            "rag corpus deleted",
            extra={
                "event_type": "rag_corpus_deleted",
                "service_name": "formdev-api",
                "app_module": "rag",
                "route_family": "rag_corpora",
                "client_id": client_id,
                "corpus_id": corpus_id,
                "sources_deleted": sources_deleted,
                "conversations_deleted":
                    conversations_deleted,
                "messages_deleted":
                    messages_deleted,
            },
        )

        return RagCorpusDeleteResponse(
            client_id=client_id,
            corpus_id=corpus_id,
            deleted=True,
            is_active=False,
            sources_deleted=sources_deleted,
            conversations_deleted=(
                conversations_deleted
            ),
            messages_deleted=messages_deleted,
            qdrant_cleanup_completed=True,
            message=(
                "Corpus désactivé, sources supprimées, "
                "points Qdrant nettoyés et conversations "
                "associées supprimées"
            ),
        )