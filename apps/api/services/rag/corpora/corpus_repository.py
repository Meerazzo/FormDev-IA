from uuid import uuid4

from sqlalchemy.orm import Session

from db.models.rag_corpus import RagCorpus
from db.models.rag_source import RagSource
from schemas.rag import RagCorpusResponse


class RagCorpusRepository:
    """Repository PostgreSQL pour les corpus RAG."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_client(
        self,
        *,
        client_id: str,
        corpus_id: str,
    ) -> RagCorpus | None:
        return (
            self.db.query(RagCorpus)
            .filter(
                RagCorpus.client_id == client_id,
                RagCorpus.corpus_id == corpus_id,
            )
            .first()
        )

    def get_or_create(
        self,
        *,
        client_id: str,
        corpus_id: str = "default",
        name: str | None = None,
        description: str | None = None,
    ) -> RagCorpus:
        corpus = self.get_for_client(
            client_id=client_id,
            corpus_id=corpus_id,
        )

        if corpus is not None:
            return corpus

        corpus = RagCorpus(
            id=f"corp_{uuid4().hex}",
            client_id=client_id,
            corpus_id=corpus_id,
            name=name or corpus_id,
            description=description,
            is_active=True,
        )

        self.db.add(corpus)
        self.db.commit()
        self.db.refresh(corpus)

        return corpus

    def list_by_client(
        self,
        *,
        client_id: str,
        include_empty: bool = True,
    ) -> list[RagCorpusResponse]:
        corpora = (
            self.db.query(RagCorpus)
            .filter(
                RagCorpus.client_id == client_id,
                RagCorpus.is_active.is_(True),
            )
            .order_by(RagCorpus.corpus_id.asc())
            .all()
        )

        sources = (
            self.db.query(RagSource)
            .filter(
                RagSource.client_id == client_id,
                RagSource.status != "deleted",
            )
            .all()
        )

        corpus_map: dict[str, dict] = {}

        for corpus in corpora:
            corpus_map[corpus.corpus_id] = {
                "client_id": corpus.client_id,
                "corpus_id": corpus.corpus_id,
                "name": corpus.name,
                "description": corpus.description,
                "is_active": corpus.is_active,
                "sources_count": 0,
                "indexed_sources_count": 0,
                "pending_sources_count": 0,
                "error_sources_count": 0,
                "created_at": corpus.created_at,
                "updated_at": corpus.updated_at,
            }

        for source in sources:
            if source.corpus_id not in corpus_map:
                corpus_map[source.corpus_id] = {
                    "client_id": source.client_id,
                    "corpus_id": source.corpus_id,
                    "name": source.corpus_id,
                    "description": None,
                    "is_active": True,
                    "sources_count": 0,
                    "indexed_sources_count": 0,
                    "pending_sources_count": 0,
                    "error_sources_count": 0,
                    "created_at": None,
                    "updated_at": None,
                }

            entry = corpus_map[source.corpus_id]
            entry["sources_count"] += 1

            if source.status == "indexed":
                entry["indexed_sources_count"] += 1
            elif source.status in {"pending", "indexing"}:
                entry["pending_sources_count"] += 1
            elif source.status == "error":
                entry["error_sources_count"] += 1

        if not include_empty:
            corpus_map = {
                corpus_id: payload
                for corpus_id, payload in corpus_map.items()
                if payload["sources_count"] > 0
            }

        def sort_key(item: tuple[str, dict]) -> tuple[int, str]:
            corpus_id, _ = item
            return (0 if corpus_id == "default" else 1, corpus_id)

        return [
            RagCorpusResponse(**payload)
            for _, payload in sorted(corpus_map.items(), key=sort_key)
        ]
