from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import select
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
        user_id: str,
        corpus_id: str = "default",
        title: str | None = None,
    ) -> RagConversation:
        conversation = RagConversation(
            conversation_id=f"rag_conv_{uuid4().hex}",
            client_id=client_id,
            corpus_id=corpus_id,
            user_id=user_id,
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
        user_id: str,
        corpus_id: str = "default",
    ) -> RagConversation | None:
        return (
            self.db.query(RagConversation)
            .filter(
                RagConversation.conversation_id == conversation_id,
                RagConversation.client_id == client_id,
                RagConversation.corpus_id == corpus_id,
                RagConversation.user_id == user_id,
            )
            .first()
        )

    def list_conversations(
        self,
        *,
        client_id: str,
        user_id: str,
        corpus_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RagConversation]:
        query = self.db.query(RagConversation).filter(
            RagConversation.client_id == client_id,
            RagConversation.user_id == user_id,
        )

        if corpus_id is not None:
            query = query.filter(
                RagConversation.corpus_id == corpus_id
            )

        return (
            query.order_by(RagConversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def update_title(
        self,
        *,
        conversation_id: str,
        client_id: str,
        user_id: str,
        corpus_id: str,
        title: str,
    ) -> RagConversation | None:
        conversation = self.get_for_client(
            conversation_id=conversation_id,
            client_id=client_id,
            corpus_id=corpus_id,
            user_id=user_id,
        )

        if conversation is None:
            return None

        conversation.title = title
        conversation.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(conversation)

        return conversation

    def delete_conversation(
        self,
        *,
        conversation_id: str,
        client_id: str,
        user_id: str,
        corpus_id: str,
    ) -> bool:
        conversation = self.get_for_client(
            conversation_id=conversation_id,
            client_id=client_id,
            corpus_id=corpus_id,
            user_id=user_id,
        )

        if conversation is None:
            return False

        self.db.query(RagMessage).filter(
            RagMessage.conversation_id == conversation_id
        ).delete(synchronize_session=False)

        self.db.delete(conversation)
        self.db.commit()

        return True

    def _add_message(
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

        return message


    def create_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> RagMessage:
        message = self._add_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources,
            metadata=metadata,
        )

        self.db.commit()
        self.db.refresh(message)

        return message


    def create_message_and_prune(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        metadata: dict | None = None,
        keep_last: int = 6,
    ) -> RagMessage:
        """
        Enregistre un message et prune l'historique dans la même transaction SQL.
        """

        if keep_last < 1:
            raise ValueError(
                "keep_last doit être supérieur ou égal à 1"
            )

        try:
            message = self._add_message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                sources=sources,
                metadata=metadata,
            )

            self.db.flush()

            self._prune_messages(
                conversation_id=conversation_id,
                keep_last=keep_last,
            )

            self.db.commit()
            self.db.refresh(message)

            return message

        except Exception:
            self.db.rollback()
            raise


    def create_assistant_message_and_prune(
        self,
        *,
        conversation_id: str,
        content: str,
        sources: list[dict] | None = None,
        metadata: dict | None = None,
        keep_last: int = 6,
    ) -> RagMessage:
        return self.create_message_and_prune(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            sources=sources,
            metadata=metadata,
            keep_last=keep_last,
        )


    def _prune_messages(
        self,
        *,
        conversation_id: str,
        keep_last: int,
    ) -> int:

        keep_ids = (
            select(RagMessage.id)
            .where(
                RagMessage.conversation_id == conversation_id
            )
            .order_by(
                RagMessage.created_at.desc(),
                RagMessage.id.desc(),
            )
            .limit(keep_last)
        )

        return (
            self.db.query(RagMessage)
            .filter(
                RagMessage.conversation_id == conversation_id,
                ~RagMessage.id.in_(keep_ids),
            )
            .delete(synchronize_session=False)
        )


    def prune_messages(
        self,
        *,
        conversation_id: str,
        keep_last: int = 6,
    ) -> int:

        if keep_last < 1:
            raise ValueError(
                "keep_last doit être supérieur ou égal à 1"
            )

        try:
            deleted_count = self._prune_messages(
                conversation_id=conversation_id,
                keep_last=keep_last,
            )

            self.db.commit()

            return deleted_count

        except Exception:
            self.db.rollback()
            raise

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

    def get_recent_messages(
        self,
        *,
        conversation_id: str,
        limit: int = 6,
    ) -> list[RagMessage]:
        messages = (
            self.db.query(RagMessage)
            .filter(RagMessage.conversation_id == conversation_id)
            .order_by(RagMessage.created_at.desc(), RagMessage.id.desc())
            .limit(limit)
            .all()
        )

        return list(reversed(messages))

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
            user_id=conversation.user_id,
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

    def to_history_payload(
        self,
        messages: list[RagMessage],
    ) -> list[dict]:
        return [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
            if message.role in {"user", "assistant"} and message.content
        ]

    def delete_for_corpus(
        self,
        *,
        client_id: str,
        corpus_id: str,
    ) -> tuple[int, int]:
        """Supprime toutes les conversations et messages d'un corpus client."""

        conversation_ids = select(
            RagConversation.conversation_id
        ).where(
            RagConversation.client_id == client_id,
            RagConversation.corpus_id == corpus_id,
        )

        try:
            messages_deleted = (
                self.db.query(RagMessage)
                .filter(
                    RagMessage.conversation_id.in_(conversation_ids)
                )
                .delete(synchronize_session=False)
            )

            conversations_deleted = (
                self.db.query(RagConversation)
                .filter(
                    RagConversation.client_id == client_id,
                    RagConversation.corpus_id == corpus_id,
                )
                .delete(synchronize_session=False)
            )

            self.db.commit()

            return conversations_deleted, messages_deleted

        except Exception:
            self.db.rollback()
            raise
