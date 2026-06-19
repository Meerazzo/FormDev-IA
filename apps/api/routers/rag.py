"""
Routes HTTP du module RAG documentaire.
"""

from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, Security, UploadFile
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import json
from core.config import settings
from core.rate_limit import limiter
from core.security import authenticate
from db.session import get_db
from schemas.rag import (
    RagCorpusListResponse,
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
    RagConversationCreateRequest,
    RagConversationResponse,
    RagConversationListResponse,
    RagMessageListResponse,
    RagConversationUpdateRequest,
    RagConversationDeleteResponse,
)
from services.rag.ingestion.ingest_service import RagIngestService
from services.rag.ingestion.exceptions import DuplicateSourceError
from services.rag.sources.source_service import RagSourceService
from services.rag.sources.source_lifecycle_service import RagSourceLifecycleService
from services.rag.vectorstore.rag_vector_store import RagVectorStore
from services.rag.indexing.indexing_service import RagIndexingService
from services.rag.chat.rag_service import RagService
from services.rag.corpora.corpus_repository import RagCorpusRepository
from services.rag.jobs.job_repository import RagJobRepository
from services.rag.conversations.conversation_repository import RagConversationRepository
from services.rag.sources.source_repository import RagSourceRepository
from services.rag.queue.rag_queue import (
    enqueue_rag_ingest_job,
    enqueue_rag_index_job,
    enqueue_rag_reindex_job,
    enqueue_rag_resync_job,
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM

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
    """
    Vérifie l'état du module RAG documentaire.
    
    Cette route permet de contrôler la disponibilité de Qdrant, l'existence de la collection vectorielle, l'URL du serveur vLLM et le modèle d'embedding utilisé.
    """
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
    "/sources/upload-async",
    response_description="Job d'ingestion créé",
    response_model=RagAsyncJobResponse,
    summary="Importer un fichier RAG en asynchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def upload_source_async(
    request: Request,
    client_id: str,
    corpus_id: str = "default",
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """
    Importe un fichier documentaire et crée un job d'ingestion asynchrone.
    
    Le fichier est sauvegardé, une source est créée en statut pending, puis un job est envoyé dans la queue RQ. Le worker RAG se charge ensuite du parsing, du chunking, des embeddings et de l'indexation Qdrant.
    
    Cette route est recommandée pour l'intégration CRM.
    """
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

    rq_job_id = enqueue_rag_ingest_job(
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
        source_id=source.source_id,
        job_type=job.job_type,
        status=job.status,
        message="Job d'ingestion RAG ajouté à la queue",
    )


@router.post(
    "/sources/upload",
    response_description="Fichier ingéré",
    response_model=RagUploadResponse,
    summary="Importer un fichier RAG en synchrone",
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
    """
    Importe un fichier documentaire en mode synchrone.
    
    Cette route réalise immédiatement le parsing et le chunking. Elle est utile pour les tests ou les petits fichiers. Pour un usage production, préférer /rag/sources/upload-async.
    """
    authenticate(api_key)

    service = RagIngestService(db)

    try:
        return await service.ingest_upload_preview(
            client_id=client_id,
            corpus_id=corpus_id,
            upload_file=file,
        )
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/sources/url",
    response_description="Source URL créée",
    response_model=RagSourceResponse,
    summary="Créer une source URL RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def create_url_source(
    request: Request,
    payload: RagUrlIngestRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSourceResponse:
    """
    Crée une source de type URL sans lancer immédiatement l'ingestion complète.
    
    Cette route permet d'enregistrer une URL comme source documentaire dans un corpus.
    """
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
    "/sources/url/ingest-async",
    response_description="Job d'ingestion URL créé",
    response_model=RagAsyncJobResponse,
    summary="Importer une URL RAG en asynchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def ingest_url_source_async(
    request: Request,
    payload: RagUrlIngestRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """
    Importe une URL documentaire en asynchrone.
    
    L'API crée une source, crée un job d'ingestion, puis le worker RAG télécharge le contenu, le transforme en texte, le découpe en chunks et l'indexe dans Qdrant.
    """
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

    rq_job_id = enqueue_rag_ingest_job(
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
        source_id=source.source_id,
        job_type=job.job_type,
        status=job.status,
        message="Job d'ingestion URL RAG ajouté à la queue",
    )


@router.post(
    "/sources/url/ingest",
    response_description="URL ingérée",
    response_model=RagUrlIngestPreviewResponse,
    summary="Importer une URL RAG en synchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def ingest_url_source(
    request: Request,
    payload: RagUrlIngestRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagUrlIngestPreviewResponse:
    """
    Importe une URL documentaire en mode synchrone.
    
    Cette route télécharge et traite immédiatement l'URL. Pour un usage production, préférer /rag/sources/url/ingest-async.
    """
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
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erreur ingestion URL: {str(exc)}") from exc



@router.get(
    "/corpora",
    response_description="Liste des corpus",
    response_model=RagCorpusListResponse,
    summary="Lister les corpus RAG d'un client",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_rag_corpora(
    request: Request,
    client_id: str = Query(...),
    include_empty: bool = Query(default=True),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagCorpusListResponse:
    """
    Liste les corpus documentaires associés à un client.
    
    Un corpus représente une base documentaire logique. L'isolation documentaire repose sur le couple client_id + corpus_id.
    """
    authenticate(api_key)

    repository = RagCorpusRepository(db)
    corpora = repository.list_by_client(
        client_id=client_id,
        include_empty=include_empty,
    )

    return RagCorpusListResponse(
        client_id=client_id,
        corpora_count=len(corpora),
        corpora=corpora,
    )


@router.get(
    "/corpora/{corpus_id}/sources",
    response_description="Liste des sources du corpus",
    response_model=list[RagSourceResponse],
    summary="Lister les sources d'un corpus RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def list_rag_corpus_sources(
    request: Request,
    corpus_id: str,
    client_id: str = Query(...),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> list[RagSourceResponse]:
    """
    Liste les sources documentaires d'un corpus.
    
    Les sources peuvent être dans les statuts pending, indexing, indexed, error ou deleted. Cette route permet au CRM d'afficher l'état documentaire d'un corpus.
    """
    authenticate(api_key)

    service = RagSourceService(db)

    return service.list_sources(
        client_id=client_id,
        corpus_id=corpus_id,
        include_deleted=include_deleted,
    )


@router.get(
    "/sources",
    response_description="Liste des sources",
    response_model=list[RagSourceResponse],
    summary="Lister les sources RAG",
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
    """
    Liste les sources documentaires d'un client et d'un corpus.
    
    Cette route permet d'obtenir les métadonnées des documents importés et leur statut d'indexation.
    """
    authenticate(api_key)

    service = RagSourceService(db)
    return service.list_sources(
        client_id=client_id,
        corpus_id=corpus_id,
        include_deleted=include_deleted,
    )

@router.post(
    "/sources/{source_id}/index",
    response_description="Source indexée",
    response_model=RagIndexSourceResponse,
    summary="Indexer une source RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def index_source(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagIndexSourceResponse:
    """
    Indexe une source documentaire en mode synchrone.
    
    La source est transformée en embeddings et ses chunks sont ajoutés à la collection Qdrant. Pour un usage production, préférer la route asynchrone.
    """
    authenticate(api_key)

    service = RagIndexingService(db)

    try:
        return service.index_source(source_id)
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur indexation RAG: {str(exc)}") from exc


@router.post(
    "/search",
    response_description="Résultats de recherche vectorielle",
    response_model=RagSearchResponse,
    summary="Rechercher des passages documentaires",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def search_rag_chunks(
    request: Request,
    payload: RagSearchRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagSearchResponse:
    """
    Recherche des passages documentaires dans Qdrant.
    
    La recherche vectorielle est filtrée par client_id et corpus_id. Cette route est utile pour déboguer le retrieval ou afficher des extraits documentaires pertinents.
    """
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
    "/conversations",
    response_description="Conversation créée",
    response_model=RagConversationResponse,
    summary="Créer une conversation RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def create_rag_conversation(
    request: Request,
    payload: RagConversationCreateRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationResponse:
    """
    Crée une conversation RAG.
    
    Cette route peut être utilisée par le CRM pour créer explicitement une conversation avant d'envoyer des messages. Les routes /rag/chat et /rag/chat/stream peuvent aussi créer automatiquement une conversation.
    """
    authenticate(api_key)

    repository = RagConversationRepository(db)
    conversation = repository.create_conversation(
        client_id=payload.client_id,
        corpus_id=payload.corpus_id,
        title=payload.title,
    )

    return repository.to_conversation_response(conversation)


@router.get(
    "/conversations",
    response_description="Liste des conversations",
    response_model=RagConversationListResponse,
    summary="Lister les conversations RAG",
)
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
    """
    Liste les conversations RAG d'un client et d'un corpus.
    
    Les conversations sont isolées par client_id et corpus_id.
    """
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
        conversations=[
            repository.to_conversation_response(conversation)
            for conversation in conversations
        ],
    )


@router.get(
    "/conversations/{conversation_id}",
    response_description="Conversation trouvée",
    response_model=RagConversationResponse,
    summary="Récupérer une conversation RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def get_rag_conversation(
    request: Request,
    conversation_id: str,
    client_id: str = Query(...),
    corpus_id: str = Query(default="default"),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationResponse:
    """
    Récupère les métadonnées d'une conversation RAG.
    
    La conversation doit appartenir au couple client_id + corpus_id fourni dans la requête.
    """
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


@router.patch(
    "/conversations/{conversation_id}",
    response_description="Conversation mise à jour",
    response_model=RagConversationResponse,
    summary="Renommer une conversation RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def update_rag_conversation(
    request: Request,
    conversation_id: str,
    payload: RagConversationUpdateRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationResponse:
    """
    Renomme une conversation RAG.
    
    Cette route permet de modifier le titre affiché côté CRM.
    """
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


@router.delete(
    "/conversations/{conversation_id}",
    response_description="Conversation supprimée",
    response_model=RagConversationDeleteResponse,
    summary="Supprimer une conversation RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def delete_rag_conversation(
    request: Request,
    conversation_id: str,
    client_id: str = Query(...),
    corpus_id: str = Query(default="default"),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagConversationDeleteResponse:
    """
    Supprime une conversation RAG et ses messages associés.
    
    La suppression est limitée au couple client_id + corpus_id.
    """
    authenticate(api_key)

    repository = RagConversationRepository(db)
    deleted = repository.delete_conversation(
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


@router.get(
    "/conversations/{conversation_id}/messages",
    response_description="Messages de la conversation",
    response_model=RagMessageListResponse,
    summary="Lister les messages d'une conversation RAG",
)
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
    """
    Liste les messages d'une conversation RAG.
    
    Chaque message contient son rôle, son contenu, ses sources éventuelles et ses métadonnées éventuelles.
    """
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
        messages=[
            repository.to_message_response(message)
            for message in messages
        ],
    )



def _format_sse_event(event: str, data: dict) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


@router.post(
    "/chat/stream",
    response_description="Flux SSE de réponse RAG",
    summary="Poser une question au chatbot RAG en streaming SSE",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def chat_with_rag_stream(
    request: Request,
    payload: RagChatRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> StreamingResponse:
    """
    Génère une réponse RAG en streaming SSE.
    
    Cette route est destinée à une intégration chatbot temps réel dans un CRM. Elle retourne des événements metadata, token, sources, done et error.
    
    Comme la route utilise POST, un frontend web doit consommer le stream avec fetch() et non EventSource.
    """
    authenticate(api_key)

    conversation_repository = RagConversationRepository(db)

    stream_client_id = payload.client_id
    stream_corpus_id = payload.corpus_id
    stream_question = payload.question

    if payload.conversation_id:
        conversation = conversation_repository.get_for_client(
            conversation_id=payload.conversation_id,
            client_id=stream_client_id,
            corpus_id=stream_corpus_id,
        )

        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation RAG introuvable")
    else:
        conversation = conversation_repository.create_conversation(
            client_id=stream_client_id,
            corpus_id=stream_corpus_id,
            title=stream_question[:80],
        )

    conversation_id = conversation.conversation_id

    conversation_history = conversation_repository.to_history_payload(
        conversation_repository.get_recent_messages(
            conversation_id=conversation_id,
            limit=6,
        )
    )

    conversation_repository.create_message(
        conversation_id=conversation_id,
        role="user",
        content=stream_question,
        sources=None,
        metadata=None,
    )

    service = RagService()

    def event_generator():
        answer_parts: list[str] = []
        final_sources: list[dict] = []
        done_payload: dict = {}

        yield _format_sse_event(
            "metadata",
            {
                "conversation_id": conversation_id,
                "client_id": stream_client_id,
                "corpus_id": stream_corpus_id,
            },
        )

        try:
            for item in service.stream_answer(
                client_id=stream_client_id,
                corpus_id=stream_corpus_id,
                question=stream_question,
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
                    yield _format_sse_event(event, data)

                elif event == "sources":
                    final_sources = data.get("sources") or []
                    yield _format_sse_event(event, data)

                elif event == "done":
                    done_payload = data
                    if data.get("answer"):
                        answer_parts = [data["answer"]]
                    # Le done final est envoyé plus bas avec le conversation_id.
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

            yield _format_sse_event(
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
            yield _format_sse_event(
                "error",
                {
                    "message": str(exc),
                    "type": exc.__class__.__name__,
                },
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/chat",
    response_description="Réponse RAG sourcée",
    response_model=RagChatResponse,
    summary="Poser une question au chatbot RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def rag_chat(
    request: Request,
    payload: RagChatRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagChatResponse:
    """
    Génère une réponse documentaire complète en JSON.
    
    La réponse est construite à partir des documents du corpus ciblé. Le champ answer contient uniquement le texte de réponse. Les sources utilisées sont fournies séparément dans le champ sources.
    
    Si les documents ne permettent pas de répondre, le backend retourne un fallback strict avec sources vides.
    """
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
        title = payload.question.strip()
        if len(title) > 80:
            title = title[:77].rstrip() + "..."

        conversation = conversation_repository.create_conversation(
            client_id=payload.client_id,
            corpus_id=payload.corpus_id,
            title=title,
        )

    recent_messages = conversation_repository.get_recent_messages(
        conversation_id=conversation.conversation_id,
        limit=6,
    )
    conversation_history = conversation_repository.to_history_payload(recent_messages)

    conversation_repository.create_message(
        conversation_id=conversation.conversation_id,
        role="user",
        content=payload.question,
        metadata={
            "top_k": payload.top_k,
            "score_threshold": payload.score_threshold,
        },
    )

    service = RagService()

    try:
        response = service.answer(
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

    sources_payload = [
        source.model_dump()
        for source in response.sources
    ]

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

    return response.model_copy(
        update={
            "conversation_id": conversation.conversation_id,
        }
    )


@router.post(
    "/sources/{source_id}/reindex",
    response_description="Source réindexée",
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
    """
    Réindexe une source documentaire en mode synchrone.
    
    Cette route reconstruit les chunks et les points vectoriels associés à la source.
    """
    authenticate(api_key)

    service = RagIndexingService(db)

    try:
        return service.reindex_source(source_id)
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur réindexation RAG: {str(exc)}") from exc


@router.post(
    "/corpora/resync",
    response_description="Corpus resynchronisé",
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
    """
    Resynchronise un corpus documentaire en mode synchrone.
    
    Cette route peut réindexer plusieurs sources d'un corpus. Pour les corpus volumineux, préférer /rag/corpora/resync-async.
    """
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
    response_description="Job d'indexation créé",
    response_model=RagAsyncJobResponse,
    summary="Indexer une source RAG en asynchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def index_source_async(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """
    Crée un job d'indexation asynchrone pour une source documentaire.
    
    Le worker RAG se charge ensuite de l'indexation sans bloquer la requête HTTP.
    """
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
    response_description="Job de réindexation créé",
    response_model=RagAsyncJobResponse,
    summary="Réindexer une source RAG en asynchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def reindex_source_async(
    request: Request,
    source_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """
    Crée un job de réindexation asynchrone pour une source documentaire.
    
    Cette route est recommandée pour réindexer une source en production.
    """
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
    response_description="Job de resynchronisation créé",
    response_model=RagAsyncJobResponse,
    summary="Resynchroniser un corpus RAG en asynchrone",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def resync_corpus_async(
    request: Request,
    payload: RagCorpusResyncRequest = Body(...),
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagAsyncJobResponse:
    """
    Crée un job de resynchronisation asynchrone pour un corpus documentaire.
    
    Le worker RAG réindexe les sources éligibles sans bloquer la requête HTTP.
    """
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
    response_description="État du job",
    response_model=RagJobStatusResponse,
    summary="Consulter l'état d'un job RAG",
)
@limiter.limit(f"{RATE_LIMIT_RPM}/minute")
async def get_rag_job_status(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> RagJobStatusResponse:
    """
    Retourne l'état d'un job RAG.
    
    Les statuts possibles sont pending, running, succeeded et failed. Cette route permet au CRM de suivre une ingestion ou une réindexation asynchrone.
    """
    authenticate(api_key)

    job_repository = RagJobRepository(db)
    job = job_repository.get_by_job_id(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job RAG introuvable")

    return job_repository.to_response(job)


@router.delete(
    "/sources/{source_id}",
    response_description="Source supprimée",
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
    """
    Supprime logiquement une source documentaire.
    
    La source ne sera plus utilisée par le retrieval et les points Qdrant associés sont supprimés lorsque c'est possible.
    """
    authenticate(api_key)

    service = RagSourceLifecycleService(db)

    try:
        return service.delete_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur suppression source RAG: {str(exc)}") from exc
