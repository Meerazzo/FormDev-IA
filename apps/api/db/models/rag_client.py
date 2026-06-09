from sqlalchemy import Boolean, Column, DateTime, Index, Text
from sqlalchemy.sql import func

from db.base import Base


class RagClient(Base):
    __tablename__ = "rag_clients"
    __table_args__ = (
        Index("idx_rag_clients_client_id", "client_id"),
        Index("idx_rag_clients_is_active", "is_active"),
    )

    id = Column(Text, primary_key=True)
    client_id = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
