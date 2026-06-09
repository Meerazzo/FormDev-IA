from sqlalchemy import BigInteger, Column, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from db.base import Base


class RagMessage(Base):
    __tablename__ = "rag_messages"
    __table_args__ = (
        Index("idx_rag_messages_conversation_id", "conversation_id"),
        Index("idx_rag_messages_role", "role"),
        Index("idx_rag_messages_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)

    conversation_id = Column(Text, nullable=False)
    role = Column(Text, nullable=False)  # user / assistant / system
    content = Column(Text, nullable=False)

    sources_json = Column(JSONB, nullable=True)
    metadata_json = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
