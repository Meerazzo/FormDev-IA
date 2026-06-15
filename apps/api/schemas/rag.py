"""
Schémas Pydantic du module RAG documentaire.

Ce fichier regroupe les contrats d'API utilisés par les routes /rag/*.
Le MVP jour 1 expose uniquement /rag/health, mais les modèles principaux
sont déjà posés pour préparer l'ingestion, le chat, la suppression de sources
et le Full Resync.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class RagSourceType(str, Enum):
    """Types de sources documentaires supportées par le RAG."""

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    URL = "url"


class RagSourceStatus(str, Enum):
    """Cycle de vie d'une source documentaire."""

    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ERROR = "error"
    DELETED = "deleted"


class RagHealthResponse(BaseModel):
    """Réponse du healthcheck du module RAG."""

    status: Literal["ok", "degraded"]
    module: str = "rag"
    qdrant_url: str
    qdrant_collection: str
    qdrant_available: bool
    qdrant_collection_exists: bool | None = None
    vllm_base_url: str
    embedding_model: str
    vector_size: int
    message: str | None = None


class RagSourceResponse(BaseModel):
    """Vue API d'une source documentaire."""

    source_id: str
    client_id: str
    corpus_id: str = "default"
    source_type: RagSourceType
    source_name: str
    status: RagSourceStatus
    source_uri: str | None = None
    qdrant_points_count: int = 0
    error_message: str | None = None


class RagUrlIngestRequest(BaseModel):
    """Demande d'ingestion d'une URL."""

    client_id: str = Field(..., min_length=1)
    corpus_id: str = Field(default="default", min_length=1)
    url: HttpUrl
    source_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagChatRequest(BaseModel):
    client_id: str
    corpus_id: str = "default"
    question: str
    top_k: int = Field(default=5, ge=1, le=10)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    max_tokens: int = Field(default=700, ge=64, le=2000)

class RagChatSource(BaseModel):
    source_id: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    score: float | None = None
    text: str | None = None


class RagSourceCitation(BaseModel):
    """Source documentaire utilisée pour construire une réponse."""

    source_id: str
    source_name: str
    source_type: RagSourceType | None = None
    page: int | None = None
    chunk_index: int | None = None
    score: float | None = None
    excerpt: str


class RagChatResponse(BaseModel):
    """Réponse générée par le chatbot RAG."""

    client_id: str
    corpus_id: str
    question: str
    answer: str
    sources: list[RagChatSource] = Field(default_factory=list)
    used_chunks_count: int


class RagResyncSourceInput(BaseModel):
    """Source transmise dans une demande de Full Resync."""

    source_type: RagSourceType
    source_name: str
    source_uri: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagResyncRequest(BaseModel):
    """Demande de reconstruction complète d'un corpus documentaire."""

    client_id: str = Field(..., min_length=1)
    corpus_id: str = Field(default="default", min_length=1)
    sources: list[RagResyncSourceInput]


class RagResyncResponse(BaseModel):
    """Bilan d'un Full Resync."""

    client_id: str
    corpus_id: str
    status: Literal["accepted", "completed", "partial_error", "error"]
    sources_count: int
    message: str | None = None

class RagUploadResponse(BaseModel):
    source_id: str
    client_id: str
    corpus_id: str
    source_type: str
    source_name: str
    status: str
    file_path: str
    chunks_path: str
    chunks_count: int
    preview_chunks: list[dict] = Field(default_factory=list)
    parser_metadata: dict[str, Any] = Field(default_factory=dict)


class RagUrlIngestPreviewResponse(BaseModel):
    source_id: str
    client_id: str
    corpus_id: str
    source_type: str
    source_name: str
    status: str
    source_uri: str
    chunks_path: str
    chunks_count: int
    preview_chunks: list[dict] = Field(default_factory=list)
    parser_metadata: dict[str, Any] = Field(default_factory=dict)


class RagIndexSourceResponse(BaseModel):
    source_id: str
    client_id: str
    corpus_id: str
    status: str
    qdrant_collection: str
    chunks_indexed: int


class RagSearchRequest(BaseModel):
    client_id: str
    corpus_id: str = "default"
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class RagSearchResult(BaseModel):
    score: float
    source_id: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagSearchResponse(BaseModel):
    client_id: str
    corpus_id: str
    query: str
    results_count: int
    results: list[RagSearchResult]


class RagChatSource(BaseModel):
    source_id: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    score: float | None = None
    text: str | None = None


class RagChatRequest(BaseModel):
    client_id: str
    corpus_id: str = "default"
    conversation_id: str | None = None
    question: str
    top_k: int = Field(default=5, ge=1, le=10)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    max_tokens: int = Field(default=700, ge=64, le=2000)


class RagChatResponse(BaseModel):
    conversation_id: str | None = None
    client_id: str
    corpus_id: str
    question: str
    answer: str
    sources: list[RagChatSource] = Field(default_factory=list)
    used_chunks_count: int
    retrieval_confidence: str = "none"
    top_score: float | None = None
    retrieval_candidates_count: int = 0
    filtered_chunks_count: int = 0



class RagConversationCreateRequest(BaseModel):
    client_id: str = Field(..., min_length=1)
    corpus_id: str = Field(default="default", min_length=1)
    title: str | None = None


class RagConversationResponse(BaseModel):
    conversation_id: str
    client_id: str
    corpus_id: str
    title: str | None = None
    messages_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RagConversationListResponse(BaseModel):
    client_id: str
    corpus_id: str | None = None
    conversations_count: int
    conversations: list[RagConversationResponse]


class RagMessageResponse(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class RagMessageListResponse(BaseModel):
    conversation_id: str
    messages_count: int
    messages: list[RagMessageResponse]


class RagDeleteSourceResponse(BaseModel):
    source_id: str
    client_id: str
    corpus_id: str
    status: str
    qdrant_points_deleted: bool
    message: str


class RagReindexSourceResponse(BaseModel):
    source_id: str
    client_id: str
    corpus_id: str
    status: str
    qdrant_collection: str
    chunks_indexed: int
    message: str


class RagCorpusResyncRequest(BaseModel):
    client_id: str
    corpus_id: str = "default"
    include_pending: bool = True
    include_error: bool = True


class RagCorpusResyncSourceResult(BaseModel):
    source_id: str
    source_name: str | None = None
    previous_status: str | None = None
    new_status: str | None = None
    chunks_indexed: int = 0
    success: bool
    error_message: str | None = None


class RagCorpusResyncResponse(BaseModel):
    client_id: str
    corpus_id: str
    total_sources: int
    indexed_sources: int
    failed_sources: int
    results: list[RagCorpusResyncSourceResult]



class RagAsyncJobResponse(BaseModel):
    job_id: str
    rq_job_id: str | None = None
    client_id: str
    corpus_id: str
    source_id: str | None = None
    job_type: str
    status: str
    message: str


class RagJobStatusResponse(BaseModel):
    job_id: str
    rq_job_id: str | None = None
    client_id: str
    corpus_id: str
    source_id: str | None = None
    job_type: str
    status: str
    total_sources: int
    processed_sources: int
    failed_sources: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
