import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from core.config import settings
from schemas.rag import (
    RagIndexSourceResponse,
    RagSearchResponse,
    RagSearchResult,
    RagReindexSourceResponse,
    RagCorpusResyncResponse,
    RagCorpusResyncSourceResult,
)
from services.rag.embeddings.local_embedding_service import get_local_embedding_service
from services.rag.sources.source_repository import RagSourceRepository
from services.rag.vectorstore.rag_vector_store import RagVectorStore


class RagIndexingService:
    """
    Service d'indexation RAG.

    Il lit les fichiers .chunks.json, calcule les embeddings,
    insère les points dans Qdrant puis met à jour la source en base.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.source_repository = RagSourceRepository(db)
        self.embedding_service = get_local_embedding_service()
        self.vector_store = RagVectorStore()

    def index_source(self, source_id: str) -> RagIndexSourceResponse:
        source = self.source_repository.get_by_source_id(source_id)

        if source is None:
            raise ValueError("Source RAG introuvable")

        if source.status == "deleted":
            raise ValueError("Impossible d'indexer une source supprimée")

        chunks = self._load_chunks_for_source(source)

        if not chunks:
            raise ValueError("Aucun chunk à indexer pour cette source")

        source.status = "indexing"
        self.db.commit()

        try:
            texts = [chunk["text"] for chunk in chunks]
            vectors = self.embedding_service.embed_texts(texts)

            indexed_count = self.vector_store.upsert_chunks(
                chunks=chunks,
                vectors=vectors,
            )

            source.status = "indexed"
            source.qdrant_points_count = indexed_count
            source.last_indexed_at = datetime.utcnow()
            source.error_message = None
            self.db.commit()
            self.db.refresh(source)

            return RagIndexSourceResponse(
                source_id=source.source_id,
                client_id=source.client_id,
                corpus_id=source.corpus_id,
                status=source.status,
                qdrant_collection=settings.RAG_QDRANT_COLLECTION,
                chunks_indexed=indexed_count,
            )

        except Exception as exc:
            source.status = "error"
            source.error_message = str(exc)
            self.db.commit()
            raise

    def reindex_source(self, source_id: str) -> RagReindexSourceResponse:
        """
        Réindexe proprement une source :
        1. supprime les anciens points Qdrant de cette source
        2. relit le fichier .chunks.json
        3. recalcule les embeddings
        4. upsert les nouveaux points
        """
        source = self.source_repository.get_by_source_id(source_id)

        if source is None:
            raise ValueError("Source RAG introuvable")

        if source.status == "deleted":
            raise ValueError("Impossible de réindexer une source supprimée")

        self.vector_store.delete_source(
            client_id=source.client_id,
            corpus_id=source.corpus_id,
            source_id=source.source_id,
        )

        index_response = self.index_source(source_id)

        return RagReindexSourceResponse(
            source_id=index_response.source_id,
            client_id=index_response.client_id,
            corpus_id=index_response.corpus_id,
            status=index_response.status,
            qdrant_collection=index_response.qdrant_collection,
            chunks_indexed=index_response.chunks_indexed,
            message="Source réindexée avec succès",
        )

    def resync_corpus(
        self,
        *,
        client_id: str,
        corpus_id: str,
        include_pending: bool = True,
        include_error: bool = True,
    ) -> RagCorpusResyncResponse:
        """
        Resynchronise les sources d'un corpus.

        Pour chaque source retenue :
        - suppression des anciens points Qdrant
        - réindexation depuis le .chunks.json
        """
        sources = self.source_repository.list_by_corpus(
            client_id=client_id,
            corpus_id=corpus_id,
            include_deleted=False,
        )

        eligible_sources = []

        for source in sources:
            if source.status == "indexed":
                eligible_sources.append(source)
            elif include_pending and source.status == "pending":
                eligible_sources.append(source)
            elif include_error and source.status == "error":
                eligible_sources.append(source)

        results: list[RagCorpusResyncSourceResult] = []

        for source in eligible_sources:
            previous_status = source.status

            try:
                response = self.reindex_source(source.source_id)

                results.append(
                    RagCorpusResyncSourceResult(
                        source_id=source.source_id,
                        source_name=source.source_name,
                        previous_status=previous_status,
                        new_status=response.status,
                        chunks_indexed=response.chunks_indexed,
                        success=True,
                    )
                )

            except Exception as exc:
                self.db.refresh(source)

                results.append(
                    RagCorpusResyncSourceResult(
                        source_id=source.source_id,
                        source_name=source.source_name,
                        previous_status=previous_status,
                        new_status=source.status,
                        chunks_indexed=0,
                        success=False,
                        error_message=str(exc),
                    )
                )

        indexed_sources = sum(1 for result in results if result.success)
        failed_sources = sum(1 for result in results if not result.success)

        return RagCorpusResyncResponse(
            client_id=client_id,
            corpus_id=corpus_id,
            total_sources=len(results),
            indexed_sources=indexed_sources,
            failed_sources=failed_sources,
            results=results,
        )

    def search(
        self,
        *,
        client_id: str,
        corpus_id: str,
        query: str,
        top_k: int,
        score_threshold: float | None,
    ) -> RagSearchResponse:
        query_vector = self.embedding_service.embed_query(query)

        results = self.vector_store.search(
            query_vector=query_vector,
            client_id=client_id,
            corpus_id=corpus_id,
            top_k=top_k,
            score_threshold=score_threshold,
        )

        return RagSearchResponse(
            client_id=client_id,
            corpus_id=corpus_id,
            query=query,
            results_count=len(results),
            results=[
                RagSearchResult(**result)
                for result in results
            ],
        )

    def _load_chunks_for_source(self, source) -> list[dict]:
        chunks_path = self._find_chunks_path(source)
        return self._load_chunks(chunks_path)

    def _load_chunks(self, chunks_path: Path) -> list[dict]:
        with open(chunks_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError("Le fichier chunks JSON doit contenir une liste")

        return data

    def _find_chunks_path(self, source) -> Path:
        """
        Retrouve le fichier .chunks.json associé à une source.
        """
        metadata = source.metadata_json or {}

        if metadata.get("chunks_path"):
            candidate = Path(metadata["chunks_path"])
            if candidate.exists():
                return candidate

        source_uri = source.source_uri or ""

        if source_uri.startswith("/"):
            source_path = Path(source_uri)
            candidate = source_path.with_suffix(source_path.suffix + ".chunks.json")

            if candidate.exists():
                return candidate

        storage_dir = Path(settings.RAG_STORAGE_DIR) / source.client_id

        for candidate in storage_dir.glob("*.chunks.json"):
            try:
                chunks = self._load_chunks(candidate)
            except Exception:
                continue

            if chunks and chunks[0].get("source_id") == source.source_id:
                return candidate

        raise ValueError(
            f"Fichier chunks introuvable pour la source {source.source_id}"
        )
