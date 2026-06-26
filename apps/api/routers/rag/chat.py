"""Routes de chat RAG synchrone et streaming."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Security
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.rag import RagChatRequest, RagChatResponse
from services.rag.chat.rag_service import RagService
from services.rag.conversations.conversation_repository import RagConversationRepository

from .common import RATE_LIMIT_RPM, api_key_header, format_sse_event

router = APIRouter(prefix="/rag", tags=["rag"])


def _conversation_title(question: str) -> str:
    title = question.strip()
    return title[:77].rstrip() + "..." if len(title) > 80 else title


@router.post("/chat/stream", response_description="Flux SSE de réponse RAG", summary="Poser une question au chatbot RAG en streaming SSE")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def chat_with_rag_stream(
    request: Request,
    payload: RagChatRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> StreamingResponse:
    """Stream SSE pour une intégration chatbot temps réel côté CRM."""
    authenticate(api_key)
    conversation_repository = RagConversationRepository(db)

    if payload.conversation_id:
        conversation = conversation_repository.get_for_client(
            conversation_id=payload.conversation_id,
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation RAG introuvable")
    else:
        conversation = conversation_repository.create_conversation(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            title=payload.question[:80],
        )

    conversation_id = conversation.conversation_id
    conversation_history = conversation_repository.to_history_payload(
        conversation_repository.get_recent_messages(conversation_id=conversation_id, limit=6)
    )
    conversation_repository.create_message(
        conversation_id=conversation_id,
        role="user",
        content=payload.question,
        sources=None,
        metadata=None,
    )

    service = RagService()

    def event_generator():
        answer_parts: list[str] = []
        final_sources: list[dict] = []
        done_payload: dict = {}

        yield format_sse_event(
            "metadata",
            {
                "conversation_id": conversation_id,
                "client_id": payload.client_id,
                "corpus_id": payload.corpus_id,
            },
        )

        try:
            for item in service.stream_answer(
                client_id=payload.client_id,
                corpus_id=payload.corpus_id,
                question=payload.question,
                top_k=payload.top_k,
                score_threshold=payload.score_threshold,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                conversation_history=conversation_history,
            ):
                event = item["event"]
                data = item["data"]

                if event == "token":
                    answer_parts.append(data.get("content") or "")
                    yield format_sse_event(event, data)
                elif event == "sources":
                    final_sources = data.get("sources") or []
                    yield format_sse_event(event, data)
                elif event == "done":
                    done_payload = data
                    if data.get("answer"):
                        answer_parts = [data["answer"]]
                    continue

            final_answer = "".join(answer_parts).strip()
            conversation_repository.create_message(
                conversation_id=conversation_id,
                role="assistant",
                content=final_answer,
                sources=final_sources,
                metadata={
                    **(done_payload.get("metadata") or {}),
                    "stream": True,
                    "used_chunks_count": done_payload.get("used_chunks_count", 0),
                    "retrieval_confidence": done_payload.get("retrieval_confidence"),
                    "top_score": done_payload.get("top_score"),
                    "retrieval_candidates_count": done_payload.get("retrieval_candidates_count", 0),
                    "filtered_chunks_count": done_payload.get("filtered_chunks_count", 0),
                    "fallback": done_payload.get("fallback", False),
                },
            )
            yield format_sse_event(
                "done",
                {
                    "conversation_id": conversation_id,
                    "used_chunks_count": done_payload.get("used_chunks_count", 0),
                    "retrieval_confidence": done_payload.get("retrieval_confidence"),
                    "top_score": done_payload.get("top_score"),
                    "retrieval_candidates_count": done_payload.get("retrieval_candidates_count", 0),
                    "filtered_chunks_count": done_payload.get("filtered_chunks_count", 0),
                    "fallback": done_payload.get("fallback", False),
                },
            )
        except Exception as exc:
            yield format_sse_event("error", {"message": str(exc), "type": exc.__class__.__name__})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", response_model=RagChatResponse, summary="Poser une question au chatbot RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def rag_chat(
    request: Request,
    payload: RagChatRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagChatResponse:
    """Réponse RAG JSON avec sources et persistance en conversation."""
    authenticate(api_key)
    conversation_repository = RagConversationRepository(db)

    if payload.conversation_id:
        conversation = conversation_repository.get_for_client(
            conversation_id=payload.conversation_id,
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation RAG introuvable")
    else:
        conversation = conversation_repository.create_conversation(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            title=_conversation_title(payload.question),
        )

    conversation_history = conversation_repository.to_history_payload(
        conversation_repository.get_recent_messages(
            conversation_id=conversation.conversation_id,
            limit=6,
        )
    )
    conversation_repository.create_message(
        conversation_id=conversation.conversation_id,
        role="user",
        content=payload.question,
        metadata={
            "top_k": payload.top_k,
            "score_threshold": payload.score_threshold,
        },
    )

    try:
        response = RagService().answer(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            question=payload.question,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            conversation_history=conversation_history,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur génération RAG: {str(exc)}") from exc

    sources_payload = [source.model_dump() for source in response.sources]
    conversation_repository.create_message(
        conversation_id=conversation.conversation_id,
        role="assistant",
        content=response.answer,
        sources=sources_payload,
        metadata={
            **(response.metadata or {}),
            "used_chunks_count": response.used_chunks_count,
            "retrieval_confidence": response.retrieval_confidence,
            "top_score": response.top_score,
            "retrieval_candidates_count": response.retrieval_candidates_count,
            "filtered_chunks_count": response.filtered_chunks_count,
            "conversation_history_messages_count": len(conversation_history),
        },
    )

    return response.model_copy(update={"conversation_id": conversation.conversation_id})
