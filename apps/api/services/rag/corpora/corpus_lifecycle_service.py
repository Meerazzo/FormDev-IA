from sqlalchemy.orm import Session

from schemas.rag import RagCorpusDeleteResponse
from services.rag.corpora.corpus_repository import RagCorpusRepository
from services.rag.sources.source_repository import RagSourceRepository
from services.rag.vectorstore.rag_vector_store import RagVectorStore


class RagCorpusLifecycleService:
    """
    Gère le cycle de vie d'un corpus RAG.

    Suppression logique :
    - désactive le corpus ;
    - marque les sources du corpus comme deleted ;
    - supprime les points Qdrant associés aux sources.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.corpus_repository = RagCorpusRepository(db)
        self.source_repository = RagSourceRepository(db)
        self.vector_store = RagVectorStore()

    def delete_corpus(
        self,
        *,
        client_id: str,
        corpus_id: str,
        delete_sources: bool = True,
    ) -> RagCorpusDeleteResponse:
        corpus = self.corpus_repository.get_for_client(
            client_id=client_id,
            corpus_id=corpus_id,
        )

        if corpus is None:
            raise ValueError("Corpus RAG introuvable")

        sources_deleted_count = 0
        qdrant_sources_deleted_count = 0

        if delete_sources:
            sources = self.source_repository.list_by_corpus(
                client_id=client_id,
                corpus_id=corpus_id,
                include_deleted=False,
            )

            for source in sources:
                self.vector_store.delete_source(
                    client_id=source.client_id,
                    corpus_id=source.corpus_id,
                    source_id=source.source_id,
                )
                qdrant_sources_deleted_count += 1

                self.source_repository.mark_deleted(source.source_id)
                sources_deleted_count += 1

        self.corpus_repository.mark_inactive(
            client_id=client_id,
            corpus_id=corpus_id,
        )

        return RagCorpusDeleteResponse(
            client_id=client_id,
            corpus_id=corpus_id,
            deleted=True,
            sources_deleted_count=sources_deleted_count,
            qdrant_sources_deleted_count=qdrant_sources_deleted_count,
            message="Corpus supprimé logiquement",
        )
