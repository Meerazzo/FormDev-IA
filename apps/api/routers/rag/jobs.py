"""Routes de suivi des jobs RAG asynchrones."""

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from sqlalchemy.orm import Session

from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.rag import RagJobStatusResponse
from services.rag.jobs.job_repository import RagJobRepository

from .common import RATE_LIMIT_RPM, api_key_header

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/jobs/{job_id}", response_model=RagJobStatusResponse, summary="Consulter l'état d'un job RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def get_rag_job_status(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagJobStatusResponse:
    """Retourne l'état d'un job d'ingestion, indexation, réindexation ou resync."""
    authenticate(api_key)
    job = RagJobRepository(db).get_by_job_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job RAG introuvable")
    return RagJobRepository(db).to_response(job)
