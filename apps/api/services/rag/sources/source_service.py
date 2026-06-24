from __future__ import annotations

from sqlalchemy.orm import Session

from schemas.rag import RagSourceResponse
from services.rag.sources.source_repository import RagSourceRepository


class RagSourceService:
    """
    Service métier pour gérer les sources documentaires RAG.

    Pour l'instant, il prépare les opérations d'ingestion.
    L'extraction de texte et l'indexation Qdrant seront ajoutées ensuite.
    """

    def __init__(self, db: Session) -> None:
        self.repository = RagSourceRepository(db)

    @staticmethod
    def to_response(source) -> RagSourceResponse:
        return RagSourceResponse(
            source_id=source.source_id,
            client_id=source.client_id,
            corpus_id=source.corpus_id,
            source_type=source.source_type,
            source_name=source.source_name,
            source_uri=source.source_uri,
            status=source.status,
            qdrant_points_count=source.qdrant_points_count or 0,
            error_message=source.error_message,
            metadata=source.metadata_json or {},
        )

    def create_url_source(
        self,
        *,
        client_id: str,
        corpus_id: str,
        url: str,
        source_name: str | None = None,
        metadata: dict | None = None,
    ) -> RagSourceResponse:
        source = self.repository.create_source(
            client_id=client_id,
            corpus_id=corpus_id,
            source_type="url",
            source_name=source_name or url,
            source_uri=url,
            metadata_json=metadata or {},
        )

        return self.to_response(source)

    def list_sources(
        self,
        *,
        client_id: str,
        corpus_id: str | None = None,
        include_deleted: bool = False,
    ) -> list[RagSourceResponse]:
        sources = self.repository.list_by_client(
            client_id=client_id,
            corpus_id=corpus_id,
            include_deleted=include_deleted,
        )

        return [self.to_response(source) for source in sources]

    def get_source(
        self,
        *,
        source_id: str,
        client_id: str,
        corpus_id: str | None = None,
    ) -> RagSourceResponse | None:
        source = self.repository.get_for_client(
            source_id=source_id,
            client_id=client_id,
            corpus_id=corpus_id,
            include_deleted=False,
        )

        if source is None:
            return None

        return self.to_response(source)

    def update_source(
        self,
        *,
        source_id: str,
        client_id: str,
        corpus_id: str | None = None,
        source_name: str | None = None,
        metadata: dict | None = None,
    ) -> RagSourceResponse | None:
        source = self.repository.update_source(
            source_id=source_id,
            client_id=client_id,
            corpus_id=corpus_id,
            source_name=source_name,
            metadata_json=metadata,
        )

        if source is None:
            return None

        return self.to_response(source)


    def mark_deleted(self, source_id: str) -> RagSourceResponse | None:
        source = self.repository.mark_deleted(source_id)
        if source is None:
            return None

        return self.to_response(source)
