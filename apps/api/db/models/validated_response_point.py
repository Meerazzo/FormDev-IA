from sqlalchemy import BigInteger, Column, DateTime, Integer, Text, Index
from sqlalchemy.sql import func

from db.base import Base


class ValidatedResponsePoint(Base):
    __tablename__ = "validated_response_points"
    __table_args__ = (
        Index("idx_vrp_response_id", "response_id"),
        Index("idx_vrp_point_id", "point_id"),
        Index("idx_vrp_category", "final_category"),
        Index("idx_vrp_sentiment", "final_sentiment"),
        Index("idx_vrp_created_at", "created_at"),
        Index("idx_vrp_client_id", "client_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    client_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    response_id = Column(Text, nullable=False)
    point_id = Column(Text, nullable=True)  # null pour un point ajouté manuellement

    final_text = Column(Text, nullable=False)
    final_sentiment = Column(Integer, nullable=True)
    final_category = Column(Text, nullable=True)

    source = Column(Text, nullable=False, default="model")
    # model / operator_corrected / operator_added

    is_active = Column(Text, nullable=False, default="true")

    operator_id = Column(Text, nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)