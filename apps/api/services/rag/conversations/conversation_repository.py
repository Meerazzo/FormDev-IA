from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from db.models.rag_conversation import RagConversation
from db.models.rag_message import RagMessage
from schemas.rag import (
    RagConversationResponse,
    RagMessageResponse,
)


class RagConversationRepository:
    """Repository PostgreSQL pour les conversations et messages RAG."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_conversation(
        self,
        *,
        client_id: str,
        corpus_id: str = "default",
        title: str | None = None,
    ) -> RagConversation:
        conversation = RagConversation(
            conversation_id=f"rag_conv_{uuid4().hex}",
            client_id=client_id,
            corpus_id=corpus_id,
            title=title,
        )

        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)

        return conversation

    def get_by_conversation_id(
        self,
        conversation_id: str,
    ) -> RagConversation | None:
        return (
            self.db.query(RagConversation)
            .filter(RagConversation.conversation_id == conversation_id)
            .first()
        )

    def get_for_client(
        self,
        *,
        conversation_id: str,
        client_id: str,
        corpus_id: str = "default",
    ) -> RagConversation | None:
        return (
            self.db.query(RagConversation)
            .filter(
                RagConversation.conversation_id == conversation_id,
                RagConversation.client_id == client_id,
                RagConversation.corpus_id == corpus_id,
            )
            .first()
        )

    def list_conversations(
        self,
        *,
        client_id: str,
        corpus_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RagConversation]:
        query = self.db.query(RagConversation).filter(
            RagConversation.client_id == client_id,
        )

        if corpus_id is not None:
            query = query.filter(RagConversation.corpus_id == corpus_id)

        return (
            query.order_by(RagConversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def create_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> RagMessage:
        message = RagMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources_json=sources,
            metadata_json=metadata,
        )

        self.db.add(message)

        conversation = self.get_by_conversation_id(conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(message)

        return message

    def list_messages(
        self,
        *,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RagMessage]:
        return (
            self.db.query(RagMessage)
            .filter(RagMessage.conversation_id == conversation_id)
            .order_by(RagMessage.created_at.asc(), RagMessage.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_messages(self, conversation_id: str) -> int:
        return (
            self.db.query(RagMessage)
            .filter(RagMessage.conversation_id == conversation_id)
            .count()
        )

    def to_conversation_response(
        self,
        conversation: RagConversation,
    ) -> RagConversationResponse:
        return RagConversationResponse(
            conversation_id=conversation.conversation_id,
            client_id=conversation.client_id,
            corpus_id=conversation.corpus_id,
            title=conversation.title,
            messages_count=self.count_messages(conversation.conversation_id),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    def to_message_response(
        self,
        message: RagMessage,
    ) -> RagMessageResponse:
        return RagMessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            sources=message.sources_json or [],
            metadata=message.metadata_json or {},
            created_at=message.created_at,
        )
