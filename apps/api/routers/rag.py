"""
Routes HTTP du module RAG documentaire.
"""

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, Security, UploadFile
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.rag import (
    RagHealthResponse,
    RagSourceResponse,
    RagUploadResponse,
    RagUrlIngestPreviewResponse,
    RagUrlIngestRequest,
    RagIndexSourceResponse,
    RagSearchRequest,
    RagSearchResponse,
    RagChatRequest,
    RagChatResponse,
    RagDeleteSourceResponse,
    RagReindexSourceResponse,
    RagCorpusResyncRequest,
    RagCorpusResyncResponse,
    RagAsyncJobResponse,
    RagJobStatusResponse,
)
from services.rag.ingestion.ingest_service import RagIngestService
from services.rag.sources.source_service import RagSourceService
from services.rag.sources.source_lifecycle_service import RagSourceLifecycleService
from services.rag.vectorstore.rag_vector_store import RagVectorStore
from services.rag.indexing.indexing_service import RagIndexingService
from services.rag.chat.rag_service import RagService
from services.rag.jobs.job_repository import RagJobRepository
from services.rag.sources.source_repository import RagSourceRepository
from services.rag.queue.rag_queue import (
    enqueue_rag_index_job,
    enqueue_rag_reindex_job,
    enqueue_rag_resync_job,
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get(
    "/health",
    response_model=RagHealthResponse,
    summary="Vérifier l'état du module RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def rag_health(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> RagHealthResponse:
    authenticate(api_key)

    vector_store = RagVectorStore()
    qdrant_status = vector_store.health()

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


@router.post(
    "/sources/upload",
    response_model=RagUploadResponse,
    summary="Uploader un fichier TXT, PDF ou DOCX et préparer les chunks RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def upload_source(
    request: Request,
    client_id: str,
    corpus_id: str = "default",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagUploadResponse:
    authenticate(api_key)

    service = RagIngestService(db)

    try:
        return await service.ingest_upload_preview(
            client_id=client_id,
            corpus_id=corpus_id,
            upload_file=file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/sources/url",
    response_model=RagSourceResponse,
    summary="Déclarer une URL comme source RAG sans ingestion",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def create_url_source(
    request: Request,
    payload: RagUrlIngestRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSourceResponse:
    authenticate(api_key)

    service = RagSourceService(db)
    return service.create_url_source(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        url=str(payload.url),
        source_name=payload.source_name,
        metadata=payload.metadata,
    )


@router.post(
    "/sources/url/ingest",
    response_model=RagUrlIngestPreviewResponse,
    summary="Ingestion d'une URL et préparation des chunks RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def ingest_url_source(
    request: Request,
    payload: RagUrlIngestRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagUrlIngestPreviewResponse:
    authenticate(api_key)

    service = RagIngestService(db)

    try:
        return service.ingest_url_preview(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            url=str(payload.url),
            source_name=payload.source_name,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erreur ingestion URL: {str(exc)}") from exc


@router.get(
    "/sources",
    response_model=list[RagSourceResponse],
    summary="Lister les sources RAG d'un client",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_sources(
    request: Request,
    client_id: str = Query(...),
    corpus_id: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> list[RagSourceResponse]:
    authenticate(api_key)

    service = RagSourceService(db)
    return service.list_sources(
        client_id=client_id,
        corpus_id=corpus_id,
        include_deleted=include_deleted,
    )

@router.post(
    "/sources/{source_id}/index",
    response_model=RagIndexSourceResponse,
    summary="Indexer une source RAG dans Qdrant",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def index_source(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagIndexSourceResponse:
    authenticate(api_key)

    service = RagIndexingService(db)

    try:
        return service.index_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur indexation RAG: {str(exc)}") from exc


@router.post(
    "/search",
    response_model=RagSearchResponse,
    summary="Recherche vectorielle dans les chunks RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def search_rag_chunks(
    request: Request,
    payload: RagSearchRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSearchResponse:
    authenticate(api_key)

    service = RagIndexingService(db)

    try:
        return service.search(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            query=payload.query,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur recherche RAG: {str(exc)}") from exc


@router.post(
    "/chat",
    response_model=RagChatResponse,
    summary="Générer une réponse RAG avec sources",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def rag_chat(
    request: Request,
    payload: RagChatRequest = Body(...),
    api_key: str | None = Security(api_key_header),
) -> RagChatResponse:
    authenticate(api_key)

    service = RagService()

    try:
        return service.answer(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            question=payload.question,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur génération RAG: {str(exc)}") from exc

@router.post(
    "/sources/{source_id}/reindex",
    response_model=RagReindexSourceResponse,
    summary="Réindexer une source RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def reindex_source(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagReindexSourceResponse:
    authenticate(api_key)

    service = RagIndexingService(db)

    try:
        return service.reindex_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur réindexation RAG: {str(exc)}") from exc


@router.post(
    "/corpora/resync",
    response_model=RagCorpusResyncResponse,
    summary="Resynchroniser un corpus RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def resync_corpus(
    request: Request,
    payload: RagCorpusResyncRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagCorpusResyncResponse:
    authenticate(api_key)

    service = RagIndexingService(db)

    try:
        return service.resync_corpus(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            include_pending=payload.include_pending,
            include_error=payload.include_error,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur resync corpus RAG: {str(exc)}") from exc



@router.post(
    "/sources/{source_id}/index-async",
    response_model=RagAsyncJobResponse,
    summary="Indexer une source RAG en tâche asynchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def index_source_async(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    authenticate(api_key)

    source_repository = RagSourceRepository(db)
    source = source_repository.get_by_source_id(source_id)

    if source is None:
        raise HTTPException(status_code=404, detail="Source RAG introuvable")

    if source.status == "deleted":
        raise HTTPException(status_code=400, detail="Impossible d'indexer une source supprimée")

    job_repository = RagJobRepository(db)
    job = job_repository.create_job(
        client_id=source.client_id,
        corpus_id=source.corpus_id,
        source_id=source.source_id,
        job_type="index",
        total_sources=1,
        metadata={
            "source_name": source.source_name,
            "source_type": source.source_type,
        },
    )

    rq_job_id = enqueue_rag_index_job(
        source_id=source.source_id,
        job_id=job.job_id,
    )

    job_repository.attach_rq_job_id(
        job_id=job.job_id,
        rq_job_id=rq_job_id,
    )

    return RagAsyncJobResponse(
        job_id=job.job_id,
        rq_job_id=rq_job_id,
        client_id=job.client_id,
        corpus_id=job.corpus_id,
        source_id=job.source_id,
        job_type=job.job_type,
        status=job.status,
        message="Job d'indexation RAG ajouté à la queue",
    )


@router.post(
    "/sources/{source_id}/reindex-async",
    response_model=RagAsyncJobResponse,
    summary="Réindexer une source RAG en tâche asynchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def reindex_source_async(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    authenticate(api_key)

    source_repository = RagSourceRepository(db)
    source = source_repository.get_by_source_id(source_id)

    if source is None:
        raise HTTPException(status_code=404, detail="Source RAG introuvable")

    if source.status == "deleted":
        raise HTTPException(status_code=400, detail="Impossible de réindexer une source supprimée")

    job_repository = RagJobRepository(db)
    job = job_repository.create_job(
        client_id=source.client_id,
        corpus_id=source.corpus_id,
        source_id=source.source_id,
        job_type="reindex",
        total_sources=1,
        metadata={
            "source_name": source.source_name,
            "source_type": source.source_type,
        },
    )

    rq_job_id = enqueue_rag_reindex_job(
        source_id=source.source_id,
        job_id=job.job_id,
    )

    job_repository.attach_rq_job_id(
        job_id=job.job_id,
        rq_job_id=rq_job_id,
    )

    return RagAsyncJobResponse(
        job_id=job.job_id,
        rq_job_id=rq_job_id,
        client_id=job.client_id,
        corpus_id=job.corpus_id,
        source_id=job.source_id,
        job_type=job.job_type,
        status=job.status,
        message="Job de réindexation RAG ajouté à la queue",
    )


@router.post(
    "/corpora/resync-async",
    response_model=RagAsyncJobResponse,
    summary="Resynchroniser un corpus RAG en tâche asynchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def resync_corpus_async(
    request: Request,
    payload: RagCorpusResyncRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    authenticate(api_key)

    source_repository = RagSourceRepository(db)
    sources = source_repository.list_by_corpus(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        include_deleted=False,
    )

    eligible_sources = []

    for source in sources:
        if source.status == "indexed":
            eligible_sources.append(source)
        elif payload.include_pending and source.status == "pending":
            eligible_sources.append(source)
        elif payload.include_error and source.status == "error":
            eligible_sources.append(source)

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
            "eligible_source_ids": [
                source.source_id
                for source in eligible_sources
            ],
        },
    )

    rq_job_id = enqueue_rag_resync_job(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        job_id=job.job_id,
        include_pending=payload.include_pending,
        include_error=payload.include_error,
    )

    job_repository.attach_rq_job_id(
        job_id=job.job_id,
        rq_job_id=rq_job_id,
    )

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


@router.get(
    "/jobs/{job_id}",
    response_model=RagJobStatusResponse,
    summary="Consulter le statut d'un job RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def get_rag_job_status(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagJobStatusResponse:
    authenticate(api_key)

    job_repository = RagJobRepository(db)
    job = job_repository.get_by_job_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job RAG introuvable")

    return job_repository.to_response(job)


@router.delete(
    "/sources/{source_id}",
    response_model=RagDeleteSourceResponse,
    summary="Supprimer une source RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def delete_source(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagDeleteSourceResponse:
    authenticate(api_key)

    service = RagSourceLifecycleService(db)

    try:
        return service.delete_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur suppression source RAG: {str(exc)}") from exc
