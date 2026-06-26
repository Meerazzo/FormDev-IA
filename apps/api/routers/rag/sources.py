"""Routes de gestion des sources documentaires RAG.

Responsabilités HTTP couvertes : création de sources, ingestion fichier/URL,
indexation, réindexation et suppression. La logique métier reste dans les
services `services.rag.*`.
"""

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, Security, UploadFile
from sqlalchemy.orm import Session

from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.rag import (
    RagAsyncJobResponse,
    RagDeleteSourceResponse,
    RagIndexSourceResponse,
    RagReindexSourceResponse,
    RagSourceResponse,
    RagSourceUpdateRequest,
    RagUploadResponse,
    RagUrlIngestPreviewResponse,
    RagUrlIngestRequest,
)
from services.rag.ingestion.exceptions import DuplicateSourceError
from services.rag.ingestion.ingest_service import RagIngestService
from services.rag.indexing.indexing_service import RagIndexingService
from services.rag.jobs.job_repository import RagJobRepository
from services.rag.queue.rag_queue import (
    enqueue_rag_index_job,
    enqueue_rag_ingest_job,
    enqueue_rag_reindex_job,
)
from services.rag.sources.source_lifecycle_service import RagSourceLifecycleService
from services.rag.sources.source_repository import RagSourceRepository
from services.rag.sources.source_service import RagSourceService

from .common import RATE_LIMIT_RPM, api_key_header

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/sources/upload-async", response_model=RagAsyncJobResponse, summary="Importer un fichier RAG en asynchrone")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def upload_source_async(
    request: Request,
    client_id: str,
    corpus_id: str = "default",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """Sauvegarde un fichier, crée une source puis envoie un job d'ingestion RQ."""
    authenticate(api_key)
    ingest_service = RagIngestService(db)

    try:
        source = await ingest_service.create_upload_source_for_async(
            client_id=client_id,
            corpus_id=corpus_id,
            upload_file=file,
        )
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_repository = RagJobRepository(db)
    job = job_repository.create_job(
        client_id=source.client_id,
        corpus_id=source.corpus_id,
        source_id=source.source_id,
        job_type="ingest",
        total_sources=1,
        metadata={
            "source_name": source.source_name,
            "source_type": source.source_type,
            "source_uri": source.source_uri,
            "ingestion_mode": "upload_async",
        },
    )
    rq_job_id = enqueue_rag_ingest_job(source_id=source.source_id, job_id=job.job_id)
    job_repository.attach_rq_job_id(job_id=job.job_id, rq_job_id=rq_job_id)

    return RagAsyncJobResponse(
        job_id=job.job_id,
        rq_job_id=rq_job_id,
        client_id=job.client_id,
        corpus_id=job.corpus_id,
        source_id=source.source_id,
        job_type=job.job_type,
        status=job.status,
        message="Job d'ingestion RAG ajouté à la queue",
    )


@router.post("/sources/upload", response_model=RagUploadResponse, summary="Importer un fichier RAG en synchrone")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def upload_source(
    request: Request,
    client_id: str,
    corpus_id: str = "default",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagUploadResponse:
    """Parse et découpe immédiatement un petit fichier documentaire."""
    authenticate(api_key)
    try:
        return await RagIngestService(db).ingest_upload_preview(
            client_id=client_id,
            corpus_id=corpus_id,
            upload_file=file,
        )
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sources/url", response_model=RagSourceResponse, summary="Créer une source URL RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def create_url_source(
    request: Request,
    payload: RagUrlIngestRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSourceResponse:
    """Enregistre une URL comme source sans lancer l'ingestion complète."""
    authenticate(api_key)
    return RagSourceService(db).create_url_source(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        url=str(payload.url),
        source_name=payload.source_name,
        metadata=payload.metadata,
    )


@router.post("/sources/url/ingest-async", response_model=RagAsyncJobResponse, summary="Importer une URL RAG en asynchrone")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def ingest_url_source_async(
    request: Request,
    payload: RagUrlIngestRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """Crée une source URL puis délègue ingestion/chunking/indexation au worker RAG."""
    authenticate(api_key)
    ingest_service = RagIngestService(db)

    try:
        source = ingest_service.create_url_source_for_async(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            url=str(payload.url),
            source_name=payload.source_name,
            metadata=payload.metadata,
        )
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc

    job_repository = RagJobRepository(db)
    job = job_repository.create_job(
        client_id=source.client_id,
        corpus_id=source.corpus_id,
        source_id=source.source_id,
        job_type="ingest",
        total_sources=1,
        metadata={
            "source_name": source.source_name,
            "source_type": source.source_type,
            "source_uri": source.source_uri,
            "ingestion_mode": "url_async",
        },
    )
    rq_job_id = enqueue_rag_ingest_job(source_id=source.source_id, job_id=job.job_id)
    job_repository.attach_rq_job_id(job_id=job.job_id, rq_job_id=rq_job_id)

    return RagAsyncJobResponse(
        job_id=job.job_id,
        rq_job_id=rq_job_id,
        client_id=job.client_id,
        corpus_id=job.corpus_id,
        source_id=source.source_id,
        job_type=job.job_type,
        status=job.status,
        message="Job d'ingestion URL RAG ajouté à la queue",
    )


@router.post("/sources/url/ingest", response_model=RagUrlIngestPreviewResponse, summary="Importer une URL RAG en synchrone")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def ingest_url_source(
    request: Request,
    payload: RagUrlIngestRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagUrlIngestPreviewResponse:
    """Télécharge et traite immédiatement une URL documentaire."""
    authenticate(api_key)
    try:
        return RagIngestService(db).ingest_url_preview(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            url=str(payload.url),
            source_name=payload.source_name,
            metadata=payload.metadata,
        )
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erreur ingestion URL: {str(exc)}") from exc


@router.get("/sources", response_model=list[RagSourceResponse], summary="Lister les sources RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_sources(
    request: Request,
    client_id: str = Query(...),
    corpus_id: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> list[RagSourceResponse]:
    """Liste les sources documentaires d'un client, tous corpus ou un corpus donné."""
    authenticate(api_key)
    return RagSourceService(db).list_sources(
        client_id=client_id,
        corpus_id=corpus_id,
        include_deleted=include_deleted,
    )


@router.get("/sources/{source_id}", response_model=RagSourceResponse, summary="Récupérer une source RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def get_rag_source(
    request: Request,
    source_id: str,
    client_id: str = Query(...),
    corpus_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSourceResponse:
    """Récupère une source en vérifiant son appartenance au client/corpus."""
    authenticate(api_key)
    source = RagSourceService(db).get_source(
        source_id=source_id,
        client_id=client_id,
        corpus_id=corpus_id,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source RAG introuvable")
    return source


@router.patch("/sources/{source_id}", response_model=RagSourceResponse, summary="Mettre à jour une source RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def update_rag_source(
    request: Request,
    source_id: str,
    payload: RagSourceUpdateRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSourceResponse:
    """Met à jour les métadonnées légères d'une source sans réindexer."""
    authenticate(api_key)
    source = RagSourceService(db).update_source(
        source_id=source_id,
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        source_name=payload.source_name,
        metadata=payload.metadata,
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source RAG introuvable")
    return source


@router.post("/sources/{source_id}/index", response_model=RagIndexSourceResponse, summary="Indexer une source RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def index_source(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagIndexSourceResponse:
    """Indexe une source en synchrone dans Qdrant."""
    authenticate(api_key)
    try:
        return RagIndexingService(db).index_source(source_id)
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur indexation RAG: {str(exc)}") from exc


@router.post("/sources/{source_id}/index-async", response_model=RagAsyncJobResponse, summary="Indexer une source RAG en asynchrone")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def index_source_async(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """Crée un job d'indexation sans bloquer la requête HTTP."""
    authenticate(api_key)
    source = RagSourceRepository(db).get_by_source_id(source_id)
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
        metadata={"source_name": source.source_name, "source_type": source.source_type},
    )
    rq_job_id = enqueue_rag_index_job(source_id=source.source_id, job_id=job.job_id)
    job_repository.attach_rq_job_id(job_id=job.job_id, rq_job_id=rq_job_id)

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


@router.post("/sources/{source_id}/reindex", response_model=RagReindexSourceResponse, summary="Réindexer une source RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def reindex_source(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagReindexSourceResponse:
    """Reconstruit les points vectoriels d'une source existante."""
    authenticate(api_key)
    try:
        return RagIndexingService(db).reindex_source(source_id)
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur réindexation RAG: {str(exc)}") from exc


@router.post("/sources/{source_id}/reindex-async", response_model=RagAsyncJobResponse, summary="Réindexer une source RAG en asynchrone")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def reindex_source_async(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """Crée un job de réindexation pour une source existante."""
    authenticate(api_key)
    source = RagSourceRepository(db).get_by_source_id(source_id)
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
        metadata={"source_name": source.source_name, "source_type": source.source_type},
    )
    rq_job_id = enqueue_rag_reindex_job(source_id=source.source_id, job_id=job.job_id)
    job_repository.attach_rq_job_id(job_id=job.job_id, rq_job_id=rq_job_id)

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


@router.delete("/sources/{source_id}", response_model=RagDeleteSourceResponse, summary="Supprimer une source RAG")
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def delete_source(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagDeleteSourceResponse:
    """Supprime logiquement la source, ses points Qdrant et ses artefacts locaux."""
    authenticate(api_key)
    try:
        return RagSourceLifecycleService(db).delete_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur suppression source RAG: {str(exc)}") from exc
