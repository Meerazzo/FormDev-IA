from sqlalchemy import BigInteger, Column, DateTime, Float, Text, Index
from sqlalchemy.sql import func

from db.base import Base


class ResponsePoint(Base):
    __tablename__ = "response_points"
    __table_args__ = (
        Index("idx_response_points_response_id", "response_id"),
        Index("idx_response_points_point_id", "point_id"),
        Index("idx_response_points_category", "category"),
        Index("idx_response_points_sentiment", "sentiment"),
        Index("idx_response_points_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    point_id = Column(Text, nullable=False, unique=True)
    response_id = Column(Text, nullable=False)

    point_text = Column(Text, nullable=False)
    sentiment = Column(Text, nullable=True)   # positive / negative / neutral / unknown
    category = Column(Text, nullable=True)    # catégorie métier / autre / unknown
    confidence = Column(Float, nullable=True)

    source = Column(Text, nullable=False, default="model")  # model / operator
    is_active = Column(Text, nullable=False, default="true")

    pipeline_name = Column(Text, nullable=True)
    pipeline_version = Column(Text, nullable=True)
    prompt_version = Column(Text, nullable=True)