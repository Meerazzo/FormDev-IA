"""
Schémas Pydantic du module RAG documentaire.

Ce fichier regroupe les contrats d'API utilisés par les routes /rag/*.
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

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "module": "rag",
                "qdrant_url": "http://qdrant-dev:6333",
                "qdrant_collection": "rag_chunks",
                "qdrant_available": True,
                "qdrant_collection_exists": True,
                "vllm_base_url": "http://inference:8000",
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                "vector_size": 384,
                "message": None,
            }
        }
    }

class RagCorpusResponse(BaseModel):
    """Vue API d'un corpus RAG."""

    client_id: str
    corpus_id: str
    name: str | None = None
    description: str | None = None
    is_active: bool = True
    sources_count: int = 0
    indexed_sources_count: int = 0
    pending_sources_count: int = 0
    error_sources_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RagCorpusListResponse(BaseModel):
    """Liste des corpus RAG d'un client."""

    client_id: str
    corpora_count: int
    corpora: list[RagCorpusResponse]

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "client_demo",
                "corpora_count": 2,
                "corpora": [
                    {
                        "client_id": "client_demo",
                        "corpus_id": "default",
                        "name": "default",
                        "description": None,
                        "is_active": True,
                        "sources_count": 13,
                        "indexed_sources_count": 3,
                        "pending_sources_count": 10,
                        "error_sources_count": 0,
                        "created_at": None,
                        "updated_at": None,
                    }
                ],
            }
        }
    }

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
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_id": "src_d75a37878f894e4a904a20eff2381dda",
                "client_id": "client_demo",
                "corpus_id": "default",
                "source_type": "txt",
                "source_name": "rag_async_upload_test.txt",
                "status": "indexed",
                "source_uri": "/data/rag/client_demo/rag_async_upload_test.txt",
                "qdrant_points_count": 1,
                "error_message": None,
            }
        }
    }

class RagSourceUpdateRequest(BaseModel):
    """Demande de mise à jour d'une source RAG."""

    client_id: str = Field(..., min_length=1)
    corpus_id: str | None = Field(default=None, min_length=1)
    source_name: str | None = Field(default=None, min_length=1, max_length=300)
    metadata: dict[str, Any] | None = None


class RagUrlIngestRequest(BaseModel):
    """Demande d'ingestion d'une URL."""

    client_id: str = Field(..., min_length=1)
    corpus_id: str = Field(default="default", min_length=1)
    url: HttpUrl
    source_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "client_demo",
                "corpus_id": "default",
                "url": "https://example.com",
                "source_name": "Page de documentation exemple",
                "metadata": {
                    "origin": "crm",
                    "category": "documentation"
                },
            }
        }
    }

class RagUploadResponse(BaseModel):
    """Réponse d'ingestion synchrone d'un fichier."""

    source_id: str
    client_id: str
    corpus_id: str
    source_type: str
    source_name: str
    status: str
    file_path: str
    chunks_path: str
    chunks_count: int
    preview_chunks: list[dict[str, Any]] = Field(default_factory=list)
    parser_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_id": "src_d75a37878f894e4a904a20eff2381dda",
                "client_id": "client_demo",
                "corpus_id": "default",
                "source_type": "txt",
                "source_name": "document.txt",
                "status": "pending",
                "file_path": "/data/rag/client_demo/document.txt",
                "chunks_path": "/data/rag/client_demo/document.chunks.json",
                "chunks_count": 4,
                "preview_chunks": [],
                "parser_metadata": {},
            }
        }
    }

class RagUrlIngestPreviewResponse(BaseModel):
    """Réponse d'ingestion synchrone d'une URL."""

    source_id: str
    client_id: str
    corpus_id: str
    source_type: str
    source_name: str
    status: str
    source_uri: str
    chunks_path: str
    chunks_count: int
    preview_chunks: list[dict[str, Any]] = Field(default_factory=list)
    parser_metadata: dict[str, Any] = Field(default_factory=dict)


class RagIndexSourceResponse(BaseModel):
    """Réponse d'indexation d'une source."""

    source_id: str
    client_id: str
    corpus_id: str
    status: str
    qdrant_collection: str
    chunks_indexed: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_id": "src_d75a37878f894e4a904a20eff2381dda",
                "client_id": "client_demo",
                "corpus_id": "default",
                "status": "indexed",
                "qdrant_collection": "rag_chunks",
                "chunks_indexed": 4,
            }
        }
    }

class RagSearchRequest(BaseModel):
    """Requête de recherche vectorielle RAG."""

    client_id: str
    corpus_id: str = "default"
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "client_demo",
                "corpus_id": "default",
                "query": "Que doit faire le module RAG documentaire ?",
                "top_k": 5,
                "score_threshold": 0.3,
            }
        }
    }

class RagSearchResult(BaseModel):
    """Résultat de recherche vectorielle RAG."""

    score: float
    source_id: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagSearchResponse(BaseModel):
    """Réponse de recherche vectorielle RAG."""

    client_id: str
    corpus_id: str
    query: str
    results_count: int
    results: list[RagSearchResult]

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "client_demo",
                "corpus_id": "default",
                "query": "Que doit faire le module RAG documentaire ?",
                "results_count": 1,
                "results": [
                    {
                        "score": 0.564832,
                        "source_id": "src_d75a37878f894e4a904a20eff2381dda",
                        "source_type": "txt",
                        "source_name": "rag_async_upload_test.txt",
                        "page": None,
                        "chunk_index": 0,
                        "text": "Le module RAG documentaire doit générer ses réponses uniquement à partir des documents fournis.",
                        "metadata": {},
                    }
                ],
            }
        }
    }

class RagChatSource(BaseModel):
    """Source utilisée par une réponse RAG."""

    source_id: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    score: float | None = None
    text: str | None = None


class RagSourceCitation(BaseModel):
    """Ancien format de citation conservé pour compatibilité."""

    source_id: str
    source_name: str
    source_type: RagSourceType | None = None
    page: int | None = None
    chunk_index: int | None = None
    score: float | None = None
    excerpt: str


class RagChatRequest(BaseModel):
    """Requête de chat RAG."""

    client_id: str
    corpus_id: str = "default"
    conversation_id: str | None = None
    question: str
    top_k: int = Field(default=5, ge=1, le=10)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    max_tokens: int = Field(default=700, ge=64, le=2000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "client_demo",
                "corpus_id": "default",
                "conversation_id": None,
                "question": "Que doit faire le module RAG documentaire pour les réponses ?",
                "top_k": 5,
                "score_threshold": None,
                "temperature": 0.2,
                "max_tokens": 512,
            }
        }
    }

class RagChatResponse(BaseModel):
    """Réponse générée par le chatbot RAG."""

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
    metadata: dict | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "conversation_id": "rag_conv_956f9d5b6e1944359cb3120029bd1274",
                "client_id": "client_demo",
                "corpus_id": "default",
                "question": "Que doit faire le module RAG documentaire pour les réponses ?",
                "answer": "Le module RAG documentaire doit générer ses réponses uniquement à partir des documents fournis.",
                "sources": [
                    {
                        "source_id": "src_d75a37878f894e4a904a20eff2381dda",
                        "source_type": "txt",
                        "source_name": "rag_async_upload_test.txt",
                        "page": None,
                        "chunk_index": 0,
                        "score": 0.564832,
                        "text": "Document de test pour l'ingestion asynchrone RAG.",
                    }
                ],
                "used_chunks_count": 1,
                "retrieval_confidence": "high",
                "top_score": 0.564832,
                "retrieval_candidates_count": 14,
                "filtered_chunks_count": 1,
                "metadata": None,
            }
        }
    }

class RagDeleteSourceResponse(BaseModel):
    """Réponse de suppression d'une source RAG."""

    source_id: str
    client_id: str
    corpus_id: str
    status: str
    qdrant_points_deleted: bool
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_id": "src_d75a37878f894e4a904a20eff2381dda",
                "client_id": "client_demo",
                "corpus_id": "default",
                "status": "deleted",
                "qdrant_points_deleted": True,
                "message": "Source supprimée avec succès.",
            }
        }
    }

class RagReindexSourceResponse(BaseModel):
    """Réponse de réindexation d'une source RAG."""

    source_id: str
    client_id: str
    corpus_id: str
    status: str
    qdrant_collection: str
    chunks_indexed: int
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_id": "src_d75a37878f894e4a904a20eff2381dda",
                "client_id": "client_demo",
                "corpus_id": "default",
                "status": "indexed",
                "qdrant_collection": "rag_chunks",
                "chunks_indexed": 4,
                "message": "Source réindexée avec succès.",
            }
        }
    }

class RagCorpusResyncRequest(BaseModel):
    """Demande de resynchronisation d'un corpus existant."""

    client_id: str
    corpus_id: str = "default"
    include_pending: bool = True
    include_error: bool = True

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "client_demo",
                "corpus_id": "default",
                "include_pending": True,
                "include_error": True,
            }
        }
    }

class RagCorpusResyncSourceResult(BaseModel):
    """Résultat de resync pour une source."""

    source_id: str
    source_name: str | None = None
    previous_status: str | None = None
    new_status: str | None = None
    chunks_indexed: int = 0
    success: bool
    error_message: str | None = None


class RagCorpusResyncResponse(BaseModel):
    """Bilan de resynchronisation d'un corpus."""

    client_id: str
    corpus_id: str
    total_sources: int
    indexed_sources: int
    failed_sources: int
    results: list[RagCorpusResyncSourceResult]


class RagResyncSourceInput(BaseModel):
    """Ancien format de source pour Full Resync conservé pour compatibilité."""

    source_type: RagSourceType
    source_name: str
    source_uri: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagResyncRequest(BaseModel):
    """Ancien format de demande de Full Resync conservé pour compatibilité."""

    client_id: str = Field(..., min_length=1)
    corpus_id: str = Field(default="default", min_length=1)
    sources: list[RagResyncSourceInput]


class RagResyncResponse(BaseModel):
    """Ancien format de réponse de Full Resync conservé pour compatibilité."""

    client_id: str
    corpus_id: str
    status: Literal["accepted", "completed", "partial_error", "error"]
    sources_count: int
    message: str | None = None


class RagAsyncJobResponse(BaseModel):
    """Réponse de création d'un job RAG asynchrone."""

    job_id: str
    rq_job_id: str | None = None
    client_id: str
    corpus_id: str
    source_id: str | None = None
    job_type: str
    status: str
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "rag_job_38d8d136780b4d4986af6fcc67861618",
                "rq_job_id": "295e6769-5942-4bd5-9118-296fc0fd5dce",
                "client_id": "client_demo",
                "corpus_id": "default",
                "source_id": "src_ea272b723f6b4375a7fc72d6eb611cca",
                "job_type": "ingest",
                "status": "pending",
                "message": "Job d'ingestion RAG ajouté à la queue",
            }
        }
    }

class RagJobStatusResponse(BaseModel):
    """Réponse de consultation du statut d'un job RAG."""

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

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "rag_job_38d8d136780b4d4986af6fcc67861618",
                "client_id": "client_demo",
                "corpus_id": "default",
                "source_id": "src_ea272b723f6b4375a7fc72d6eb611cca",
                "job_type": "ingest",
                "status": "succeeded",
                "total_sources": 1,
                "processed_sources": 1,
                "failed_sources": 0,
                "error_message": None,
                "metadata": {
                    "chunks_indexed": 1,
                    "qdrant_collection": "rag_chunks",
                    "final_source_status": "indexed"
                },
            }
        }
    }

class RagConversationCreateRequest(BaseModel):
    """Demande de création d'une conversation RAG."""

    client_id: str = Field(..., min_length=1)
    corpus_id: str = Field(default="default", min_length=1)
    title: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "client_demo",
                "corpus_id": "default",
                "title": "Discussion sur la documentation RAG",
            }
        }
    }

class RagConversationUpdateRequest(BaseModel):
    """Demande de renommage d'une conversation RAG."""

    client_id: str = Field(..., min_length=1)
    corpus_id: str = Field(default="default", min_length=1)
    title: str = Field(..., min_length=1, max_length=200)

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "client_demo",
                "corpus_id": "default",
                "title": "Nouveau titre de conversation",
            }
        }
    }

class RagConversationResponse(BaseModel):
    """Vue API d'une conversation RAG."""

    conversation_id: str
    client_id: str
    corpus_id: str
    title: str | None = None
    messages_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "conversation_id": "rag_conv_956f9d5b6e1944359cb3120029bd1274",
                "client_id": "client_demo",
                "corpus_id": "default",
                "title": "Discussion sur la documentation RAG",
                "messages_count": 2,
                "created_at": "2026-06-16T16:09:56.741000Z",
                "updated_at": "2026-06-16T16:10:02.741000Z",
            }
        }
    }

class RagConversationListResponse(BaseModel):
    """Liste des conversations RAG d'un client/corpus."""

    client_id: str
    corpus_id: str | None = None
    conversations_count: int
    conversations: list[RagConversationResponse]


class RagMessageResponse(BaseModel):
    """Vue API d'un message RAG."""

    id: int
    conversation_id: str
    role: str
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class RagMessageListResponse(BaseModel):
    """Liste des messages d'une conversation RAG."""

    conversation_id: str
    messages_count: int
    messages: list[RagMessageResponse]

    model_config = {
        "json_schema_extra": {
            "example": {
                "conversation_id": "rag_conv_956f9d5b6e1944359cb3120029bd1274",
                "messages_count": 2,
                "messages": [
                    {
                        "role": "user",
                        "content": "Que doit faire le module RAG documentaire ?",
                        "sources": None,
                        "metadata": None,
                        "created_at": "2026-06-16T16:09:56.741000Z",
                    },
                    {
                        "role": "assistant",
                        "content": "Le module RAG documentaire doit répondre à partir des documents fournis.",
                        "sources": [],
                        "metadata": {
                            "retrieval_confidence": "high"
                        },
                        "created_at": "2026-06-16T16:10:02.741000Z",
                    },
                ],
            }
        }
    }

class RagConversationDeleteResponse(BaseModel):
    """Réponse de suppression d'une conversation RAG."""

    conversation_id: str
    client_id: str
    corpus_id: str
    deleted: bool
    message: str
