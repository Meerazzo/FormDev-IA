"""Routes de gestion des corpus RAG."""

from fastapi import APIRouter, Body, Depends, Query, Request, Security
from sqlalchemy.orm import Session

from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.rag import (
    RagAsyncJobResponse,
    RagCorpusListResponse,
    RagCorpusResyncRequest,
    RagCorpusResyncResponse,
    RagSourceResponse,
)
from services.rag.corpora.corpus_repository import RagCorpusRepository
from services.rag.indexing.indexing_service import RagIndexingService
from services.rag.jobs.job_repository import RagJobRepository
from services.rag.queue.rag_queue import enqueue_rag_resync_job
from services.rag.sources.source_repository import RagSourceRepository
from services.rag.sources.source_service import RagSourceService

from .common import RATE_LIMIT_RPM, api_key_header

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/corpora", response_model=RagCorpusListResponse, summary="Lister les corpus RAG d'un client")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_rag_corpora(
    request: Request,
    client_id: str = Query(...),
    include_empty: bool = Query(default=True),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagCorpusListResponse:
    """Liste les bases documentaires logiques d'un client."""
    authenticate(api_key)
    corpora = RagCorpusRepository(db).list_by_client(
        client_id=client_id,
        include_empty=include_empty,
    )
    return RagCorpusListResponse(
        client_id=client_id,
        corpora_count=len(corpora),
        corpora=corpora,
    )


@router.get("/corpora/{corpus_id}/sources", response_model=list[RagSourceResponse], summary="Lister les sources d'un corpus RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_rag_corpus_sources(
    request: Request,
    corpus_id: str,
    client_id: str = Query(...),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> list[RagSourceResponse]:
    """Liste les sources d'un corpus en respectant l'isolation client."""
    authenticate(api_key)
    return RagSourceService(db).list_sources(
        client_id=client_id,
        corpus_id=corpus_id,
        include_deleted=include_deleted,
    )


@router.post("/corpora/resync", response_model=RagCorpusResyncResponse, summary="Resynchroniser un corpus RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def resync_corpus(
    request: Request,
    payload: RagCorpusResyncRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagCorpusResyncResponse:
    """Réindexe en synchrone les sources éligibles d'un corpus."""
    authenticate(api_key)
    return RagIndexingService(db).resync_corpus(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        include_pending=payload.include_pending,
        include_error=payload.include_error,
    )


@router.post("/corpora/resync-async", response_model=RagAsyncJobResponse, summary="Resynchroniser un corpus RAG en asynchrone")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def resync_corpus_async(
    request: Request,
    payload: RagCorpusResyncRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """Crée un job RQ pour réindexer les sources éligibles d'un corpus."""
    authenticate(api_key)
    sources = RagSourceRepository(db).list_by_corpus(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        include_deleted=False,
    )
    eligible_sources = [
        source
        for source in sources
        if source.status == "indexed"
        or (payload.include_pending and source.status == "pending")
        or (payload.include_error and source.status == "error")
    ]

    job_repository = RagJobRepository(db)
    job = job_repository.create_job(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        source_id=None,
        job_type="resync",
        total_sources=len(eligible_sources),
        metadata={
            "include_pending": payload.include_pending,
            "include_error": payload.include_error,
            "eligible_source_ids": [source.source_id for source in eligible_sources],
        },
    )
    rq_job_id = enqueue_rag_resync_job(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        job_id=job.job_id,
        include_pending=payload.include_pending,
        include_error=payload.include_error,
    )
    job_repository.attach_rq_job_id(job_id=job.job_id, rq_job_id=rq_job_id)

    return RagAsyncJobResponse(
        job_id=job.job_id,
        rq_job_id=rq_job_id,
        client_id=job.client_id,
        corpus_id=job.corpus_id,
        source_id=None,
        job_type=job.job_type,
        status=job.status,
        message="Job de resynchronisation RAG ajouté à la queue",
    )
