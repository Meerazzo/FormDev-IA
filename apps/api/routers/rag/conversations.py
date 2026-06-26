"""Routes de gestion des conversations RAG."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Security
from sqlalchemy.orm import Session

from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.rag import (
    RagConversationCreateRequest,
    RagConversationDeleteResponse,
    RagConversationListResponse,
    RagConversationResponse,
    RagConversationUpdateRequest,
    RagMessageListResponse,
)
from services.rag.conversations.conversation_repository import RagConversationRepository

from .common import RATE_LIMIT_RPM, api_key_header

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/conversations", response_model=RagConversationResponse, summary="Créer une conversation RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def create_rag_conversation(
    request: Request,
    payload: RagConversationCreateRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationResponse:
    authenticate(api_key)
    repository = RagConversationRepository(db)
    conversation = repository.create_conversation(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        title=payload.title,
    )
    return repository.to_conversation_response(conversation)


@router.get("/conversations", response_model=RagConversationListResponse, summary="Lister les conversations RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_rag_conversations(
    request: Request,
    client_id: str = Query(...),
    corpus_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationListResponse:
    authenticate(api_key)
    repository = RagConversationRepository(db)
    conversations = repository.list_conversations(
        client_id=client_id,
        corpus_id=corpus_id,
        limit=limit,
        offset=offset,
    )
    return RagConversationListResponse(
        client_id=client_id,
        corpus_id=corpus_id,
        conversations_count=len(conversations),
        conversations=[repository.to_conversation_response(item) for item in conversations],
    )


@router.get("/conversations/{conversation_id}", response_model=RagConversationResponse, summary="Récupérer une conversation RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def get_rag_conversation(
    request: Request,
    conversation_id: str,
    client_id: str = Query(...),
    corpus_id: str = Query(default="default"),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationResponse:
    authenticate(api_key)
    repository = RagConversationRepository(db)
    conversation = repository.get_for_client(
        conversation_id=conversation_id,
        client_id=client_id,
        corpus_id=corpus_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation RAG introuvable")
    return repository.to_conversation_response(conversation)


@router.patch("/conversations/{conversation_id}", response_model=RagConversationResponse, summary="Renommer une conversation RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def update_rag_conversation(
    request: Request,
    conversation_id: str,
    payload: RagConversationUpdateRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationResponse:
    authenticate(api_key)
    repository = RagConversationRepository(db)
    conversation = repository.update_title(
        conversation_id=conversation_id,
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        title=payload.title,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation RAG introuvable")
    return repository.to_conversation_response(conversation)


@router.delete("/conversations/{conversation_id}", response_model=RagConversationDeleteResponse, summary="Supprimer une conversation RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def delete_rag_conversation(
    request: Request,
    conversation_id: str,
    client_id: str = Query(...),
    corpus_id: str = Query(default="default"),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationDeleteResponse:
    authenticate(api_key)
    deleted = RagConversationRepository(db).delete_conversation(
        conversation_id=conversation_id,
        client_id=client_id,
        corpus_id=corpus_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation RAG introuvable")
    return RagConversationDeleteResponse(
        conversation_id=conversation_id,
        client_id=client_id,
        corpus_id=corpus_id,
        deleted=True,
        message="Conversation RAG supprimée",
    )


@router.get("/conversations/{conversation_id}/messages", response_model=RagMessageListResponse, summary="Lister les messages d'une conversation RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_rag_conversation_messages(
    request: Request,
    conversation_id: str,
    client_id: str = Query(...),
    corpus_id: str = Query(default="default"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagMessageListResponse:
    authenticate(api_key)
    repository = RagConversationRepository(db)
    conversation = repository.get_for_client(
        conversation_id=conversation_id,
        client_id=client_id,
        corpus_id=corpus_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation RAG introuvable")

    messages = repository.list_messages(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )
    return RagMessageListResponse(
        conversation_id=conversation_id,
        messages_count=len(messages),
        messages=[repository.to_message_response(message) for message in messages],
    )
