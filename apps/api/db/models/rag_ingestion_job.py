from sqlalchemy import BigInteger, Column, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from db.base import Base


class RagIngestionJob(Base):
    __tablename__ = "rag_ingestion_jobs"
    __table_args__ = (
        Index("idx_rag_ingestion_jobs_job_id", "job_id"),
        Index("idx_rag_ingestion_jobs_client_id", "client_id"),
        Index("idx_rag_ingestion_jobs_corpus_id", "corpus_id"),
        Index("idx_rag_ingestion_jobs_source_id", "source_id"),
        Index("idx_rag_ingestion_jobs_status", "status"),
        Index("idx_rag_ingestion_jobs_job_type", "job_type"),
    )

    id = Column(BigInteger, primary_key=True, index=True)

    job_id = Column(Text, nullable=False, unique=True)
    client_id = Column(Text, nullable=False)
    corpus_id = Column(Text, nullable=False, default="default")
    source_id = Column(Text, nullable=True)

    job_type = Column(Text, nullable=False)  # ingest / delete / resync
    status = Column(Text, nullable=False, default="pending")  # pending / running / succeeded / failed

    total_sources = Column(BigInteger, nullable=False, default=0)
    processed_sources = Column(BigInteger, nullable=False, default=0)
    failed_sources = Column(BigInteger, nullable=False, default=0)

    metadata_json = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
