from sqlalchemy import BigInteger, Column, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from db.base import Base


class SurveyResponse(Base):
    __tablename__ = "survey_responses"
    __table_args__ = (
        Index("idx_survey_responses_survey_id", "survey_id"),
        Index("idx_survey_responses_question_id", "question_id"),
        Index("idx_survey_responses_response_id", "response_id"),
        Index("idx_survey_responses_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    survey_id = Column(Text, nullable=False)
    question_id = Column(Text, nullable=False)
    question_text = Column(Text, nullable=False)

    response_id = Column(Text, nullable=False, unique=True)
    response_text = Column(Text, nullable=True)

    response_type = Column(Text, nullable=True)  # open / closed si besoin
    status = Column(Text, nullable=False, default="pending")  # pending / processed / failed

    metadata_json = Column(JSONB, nullable=True)

    pipeline_name = Column(Text, nullable=True)
    pipeline_version = Column(Text, nullable=True)
    prompt_version = Column(Text, nullable=True)