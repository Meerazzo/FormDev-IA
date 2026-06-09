from sqlalchemy import BigInteger, Column, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from db.base import Base


class RagSource(Base):
    __tablename__ = "rag_sources"
    __table_args__ = (
        Index("idx_rag_sources_client_id", "client_id"),
        Index("idx_rag_sources_corpus_id", "corpus_id"),
        Index("idx_rag_sources_source_id", "source_id"),
        Index("idx_rag_sources_status", "status"),
        Index("idx_rag_sources_source_type", "source_type"),
        Index("idx_rag_sources_content_hash", "content_hash"),
        Index("idx_rag_sources_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)

    source_id = Column(Text, nullable=False, unique=True)
    client_id = Column(Text, nullable=False)
    corpus_id = Column(Text, nullable=False, default="default")

    source_type = Column(Text, nullable=False)  # pdf / docx / txt / url
    source_name = Column(Text, nullable=False)
    source_uri = Column(Text, nullable=True)

    status = Column(Text, nullable=False, default="pending")  # pending / indexing / indexed / error / deleted

    content_hash = Column(Text, nullable=True)
    qdrant_points_count = Column(BigInteger, nullable=False, default=0)

    metadata_json = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
