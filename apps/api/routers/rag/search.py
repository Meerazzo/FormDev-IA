"""Routes de recherche vectorielle RAG."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Security
from sqlalchemy.orm import Session

from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.rag import RagSearchRequest, RagSearchResponse
from services.rag.indexing.indexing_service import RagIndexingService

from .common import RATE_LIMIT_RPM, api_key_header

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/search", response_model=RagSearchResponse, summary="Rechercher des passages documentaires")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def search_rag_chunks(
    request: Request,
    payload: RagSearchRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSearchResponse:
    authenticate(api_key)
    try:
        return RagIndexingService(db).search(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            query=payload.query,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur recherche RAG: {str(exc)}") from exc
