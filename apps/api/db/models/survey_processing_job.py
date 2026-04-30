from sqlalchemy import BigInteger, Column, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from db.base import Base


class SurveyProcessingJob(Base):
    __tablename__ = "survey_processing_jobs"
    __table_args__ = (
        Index("idx_survey_processing_jobs_processing_id", "processing_id"),
        Index("idx_survey_processing_jobs_status", "status"),
        Index("idx_survey_processing_jobs_survey_id", "survey_id"),
        Index("idx_survey_processing_jobs_client_id", "client_id"),
        Index("idx_survey_processing_jobs_created_at", "created_at"),
        Index("idx_survey_processing_jobs_request_id", "request_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    processing_id = Column(Text, nullable=False, unique=True)
    survey_id = Column(Text, nullable=False)
    client_id = Column(Text, nullable=True)
    request_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="PENDING")  # PENDING / STARTED / FINISHED / FAILED

    request_payload_json = Column(JSONB, nullable=True)
    result_json = Column(JSONB, nullable=True)

    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)