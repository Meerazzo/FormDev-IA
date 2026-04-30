from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from db.base import Base


class PointFeedback(Base):
    __tablename__ = "point_feedback"
    __table_args__ = (
        Index("idx_point_feedback_response_id", "response_id"),
        Index("idx_point_feedback_point_id", "point_id"),
        Index("idx_point_feedback_created_at", "created_at"),
        Index("idx_point_feedback_client_id", "client_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    client_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    response_id = Column(Text, nullable=False)
    point_id = Column(Text, nullable=True)

    is_correct = Column(Boolean, nullable=False, default=False)

    original_text = Column(Text, nullable=True)
    original_sentiment = Column(Integer, nullable=True)
    original_category = Column(Text, nullable=True)

    corrected_text = Column(Text, nullable=True)
    corrected_sentiment = Column(Integer, nullable=True)
    corrected_category = Column(Text, nullable=True)

    action = Column(Text, nullable=True)  # update / delete / add
    operator_id = Column(Text, nullable=True)

    metadata_json = Column(JSONB, nullable=True)