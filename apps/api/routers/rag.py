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
)
from services.rag.ingestion.ingest_service import RagIngestService
from services.rag.sources.source_service import RagSourceService
from services.rag.vectorstore.rag_vector_store import RagVectorStore


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


@router.delete(
    "/sources/{source_id}",
    response_model=RagSourceResponse,
    summary="Marquer une source RAG comme supprimée",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def delete_source(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSourceResponse:
    authenticate(api_key)

    service = RagSourceService(db)
    source = service.mark_deleted(source_id)

    if source is None:
        raise HTTPException(status_code=404, detail="RAG source not found")

    return source
