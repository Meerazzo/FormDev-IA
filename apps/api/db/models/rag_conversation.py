from sqlalchemy import BigInteger, Column, DateTime, Index, Text
from sqlalchemy.sql import func

from db.base import Base


class RagConversation(Base):
    __tablename__ = "rag_conversations"
    __table_args__ = (
        Index("idx_rag_conversations_conversation_id", "conversation_id"),
        Index("idx_rag_conversations_client_id", "client_id"),
        Index("idx_rag_conversations_corpus_id", "corpus_id"),
        Index("idx_rag_conversations_user_id", "user_id"),
        Index(
            "idx_rag_conversations_scope",
            "client_id",
            "corpus_id",
            "user_id",
        ),
        Index("idx_rag_conversations_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)

    conversation_id = Column(Text, nullable=False, unique=True)
    client_id = Column(Text, nullable=False)
    corpus_id = Column(Text, nullable=False, default="default")
    user_id = Column(Text, nullable=True)

    title = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
