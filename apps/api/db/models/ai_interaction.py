from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, Text, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from db.base import Base


class AIInteraction(Base):
    __tablename__ = "ai_interactions"
    __table_args__ = (
        Index("idx_ai_interactions_created_at", "created_at"),
        Index("idx_ai_interactions_project", "project"),
        Index("idx_ai_interactions_client_id", "client_id"),
        Index("idx_ai_interactions_request_id", "request_id"),
        Index("idx_ai_interactions_feature", "feature"),
        Index("idx_ai_interactions_status_code", "status_code"),
        Index("idx_ai_interactions_project_created_at", "project", "created_at"),
        Index("idx_ai_interactions_client_created_at", "client_id", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    request_id = Column(UUID(as_uuid=False), nullable=True)
    project = Column(Text, nullable=False)
    client_id = Column(Text, nullable=True)
    endpoint = Column(Text, nullable=False)
    feature = Column(Text, nullable=False, default="unknown")

    model_requested = Column(Text, nullable=True)
    model_used = Column(Text, nullable=True)

    input_text = Column(Text, nullable=True)
    messages_json = Column(JSONB, nullable=True)
    request_params_json = Column(JSONB, nullable=True)

    output_text = Column(Text, nullable=True)
    response_json = Column(JSONB, nullable=True)
    finish_reason = Column(Text, nullable=True)

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)

    status_code = Column(Integer, nullable=False)
    error_type = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    pipeline_name = Column(Text, nullable=True)
    pipeline_version = Column(Text, nullable=True)
    prompt_version = Column(Text, nullable=True)
    source_ref = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True)