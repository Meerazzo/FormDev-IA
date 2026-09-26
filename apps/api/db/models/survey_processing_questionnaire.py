from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.sql import func

from db.base import Base


class SurveyProcessingQuestionnaire(Base):
    __tablename__ = "survey_processing_questionnaires"
    __table_args__ = (
        UniqueConstraint(
            "processing_id",
            "questionnaire_id",
            name="uq_survey_processing_questionnaires_processing_questionnaire",
        ),
        Index(
            "idx_survey_processing_questionnaires_lookup",
            "client_id",
            "questionnaire_id",
            "created_at",
        ),
        Index(
            "idx_survey_processing_questionnaires_processing_id",
            "processing_id",
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    processing_id = Column(
        Text,
        ForeignKey("survey_processing_jobs.processing_id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id = Column(Text, nullable=False)
    questionnaire_id = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
