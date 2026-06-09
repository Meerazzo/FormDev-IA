from sqlalchemy import Boolean, Column, DateTime, Index, Text, UniqueConstraint
from sqlalchemy.sql import func

from db.base import Base


class RagCorpus(Base):
    __tablename__ = "rag_corpora"
    __table_args__ = (
        UniqueConstraint("client_id", "corpus_id", name="uq_rag_corpora_client_corpus"),
        Index("idx_rag_corpora_client_id", "client_id"),
        Index("idx_rag_corpora_corpus_id", "corpus_id"),
        Index("idx_rag_corpora_is_active", "is_active"),
    )

    id = Column(Text, primary_key=True)
    client_id = Column(Text, nullable=False)
    corpus_id = Column(Text, nullable=False, default="default")

    name = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
