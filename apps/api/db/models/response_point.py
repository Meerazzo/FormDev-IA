from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, Text, Index
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
        Index("idx_response_points_client_id", "client_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    client_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    point_id = Column(Text, nullable=False, unique=True)
    response_id = Column(Text, nullable=False)

    point_text = Column(Text, nullable=False)

    # Nouvelle sémantique :
    # 1 = très négatif
    # 2 = négatif
    # 3 = neutre
    # 4 = positif
    # 5 = très positif
    sentiment = Column(Integer, nullable=True)

    category = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)

    source = Column(Text, nullable=False, default="model")
    is_active = Column(Text, nullable=False, default="true")

    pipeline_name = Column(Text, nullable=True)
    pipeline_version = Column(Text, nullable=True)
    prompt_version = Column(Text, nullable=True)