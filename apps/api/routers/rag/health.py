"""Routes de diagnostic du module RAG."""

from fastapi import APIRouter, Request, Security

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from schemas.rag import RagHealthResponse
from services.rag.vectorstore.rag_vector_store import RagVectorStore

from .common import RATE_LIMIT_RPM, api_key_header

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get(
    "/health",
    response_description="État du module RAG",
    response_model=RagHealthResponse,
    summary="Vérifier l'état du module RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def rag_health(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> RagHealthResponse:
    """Vérifie Qdrant, la collection RAG et les paramètres d'embedding."""
    authenticate(api_key)

    qdrant_status = RagVectorStore().health()
    status = "ok" if qdrant_status["available"] else "degraded"

    return RagHealthResponse(
        status=status,
        qdrant_url=settings.QDRANT_URL,
        qdrant_collection=settings.RAG_QDRANT_COLLECTION,
        qdrant_available=qdrant_status["available"],
        qdrant_collection_exists=qdrant_status["collection_exists"],
        vllm_base_url=settings.VLLM_BASE_URL,
        embedding_model=settings.RAG_EMBEDDING_MODEL,
        vector_size=settings.RAG_VECTOR_SIZE,
        message=qdrant_status["error"],
    )
