from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from sqlalchemy.orm import Session

from db.models.rag_source import RagSource
from services.rag.corpora.corpus_repository import RagCorpusRepository


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
        RagCorpusRepository(self.db).get_or_create(
            client_id=client_id,
            corpus_id=corpus_id,
        )

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

    def find_duplicate_by_hash(
        self,
        *,
        client_id: str,
        corpus_id: str,
        content_hash: str | None,
    ) -> RagSource | None:
        if not content_hash:
            return None

        return (
            self.db.query(RagSource)
            .filter(
                RagSource.client_id == client_id,
                RagSource.corpus_id == corpus_id,
                RagSource.content_hash == content_hash,
                RagSource.status != "deleted",
            )
            .order_by(RagSource.created_at.desc())
            .first()
        )

    def find_duplicate_by_source_uri(
        self,
        *,
        client_id: str,
        corpus_id: str,
        source_uri: str,
        source_type: str = "url",
    ) -> RagSource | None:
        normalized_uri = self.normalize_source_uri(source_uri)

        candidates = (
            self.db.query(RagSource)
            .filter(
                RagSource.client_id == client_id,
                RagSource.corpus_id == corpus_id,
                RagSource.source_type == source_type,
                RagSource.status != "deleted",
            )
            .all()
        )

        for candidate in candidates:
            if self.normalize_source_uri(candidate.source_uri or "") == normalized_uri:
                return candidate

        return None

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

    def list_by_corpus(
        self,
        *,
        client_id: str,
        corpus_id: str,
        include_deleted: bool = False,
    ):
        query = self.db.query(RagSource).filter(
            RagSource.client_id == client_id,
            RagSource.corpus_id == corpus_id,
        )

        if not include_deleted:
            query = query.filter(RagSource.status != "deleted")

        return query.order_by(RagSource.created_at.desc()).all()

    @staticmethod
    def normalize_source_uri(source_uri: str) -> str:
        source_uri = (source_uri or "").strip()

        if not source_uri:
            return ""

        parsed = urlparse(source_uri)

        scheme = (parsed.scheme or "https").lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"

        if path != "/":
            path = path.rstrip("/")

        return urlunparse(
            (
                scheme,
                netloc,
                path,
                "",
                parsed.query,
                "",
            )
        )
