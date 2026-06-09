from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from db.models.rag_source import RagSource


class RagSourceRepository:
    """
    Accès base de données pour les sources documentaires RAG.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_source(
        self,
        *,
        client_id: str,
        corpus_id: str,
        source_type: str,
        source_name: str,
        source_uri: str | None = None,
        metadata_json: dict | None = None,
        content_hash: str | None = None,
    ) -> RagSource:
        source = RagSource(
            source_id=f"src_{uuid4().hex}",
            client_id=client_id,
            corpus_id=corpus_id,
            source_type=source_type,
            source_name=source_name,
            source_uri=source_uri,
            status="pending",
            metadata_json=metadata_json or {},
            content_hash=content_hash,
        )

        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)

        return source

    def get_by_source_id(self, source_id: str) -> RagSource | None:
        return (
            self.db.query(RagSource)
            .filter(RagSource.source_id == source_id)
            .first()
        )

    def list_by_client(
        self,
        *,
        client_id: str,
        corpus_id: str | None = None,
        include_deleted: bool = False,
    ) -> list[RagSource]:
        query = self.db.query(RagSource).filter(RagSource.client_id == client_id)

        if corpus_id:
            query = query.filter(RagSource.corpus_id == corpus_id)

        if not include_deleted:
            query = query.filter(RagSource.status != "deleted")

        return query.order_by(RagSource.created_at.desc()).all()

    def update_status(
        self,
        *,
        source_id: str,
        status: str,
        error_message: str | None = None,
        qdrant_points_count: int | None = None,
        mark_indexed: bool = False,
    ) -> RagSource | None:
        source = self.get_by_source_id(source_id)
        if source is None:
            return None

        source.status = status
        source.error_message = error_message

        if qdrant_points_count is not None:
            source.qdrant_points_count = qdrant_points_count

        if mark_indexed:
            source.last_indexed_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(source)

        return source

    def mark_deleted(self, source_id: str) -> RagSource | None:
        source = self.get_by_source_id(source_id)
        if source is None:
            return None

        source.status = "deleted"
        source.deleted_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(source)

        return source
