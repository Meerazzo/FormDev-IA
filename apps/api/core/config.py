"""
Configuration centrale de l'application.

Les paramètres sont chargés depuis les variables d'environnement
grâce à pydantic-settings.

Cela permet de modifier facilement la configuration selon
l'environnement (dev, staging, production) sans changer le code.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Paramètres de configuration utilisés dans l'application.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    VLLM_BASE_URL: str = "http://localhost:8000"
    RATE_LIMIT_RPM: int = 30
    API_KEYS: str = ""
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "survey_feedback_examples"
    QDRANT_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    QDRANT_VECTOR_SIZE: int = 384

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    RQ_SURVEY_QUEUE: str = "survey"
    RQ_DEFAULT_TIMEOUT: int = 3600
    RQ_RESULT_TTL: int = 600
    RQ_FAILURE_TTL: int = 86400

    SURVEY_PURGE_AFTER_FEEDBACK: bool = False

    APP_ENV: str = "dev"

    GRAYLOG_ENABLED: bool = False
    GRAYLOG_HOST: str = "graylog"
    GRAYLOG_PORT: int = 12201
    GRAYLOG_FACILITY: str = "formdev-ia"

    # RAG documentaire
    RAG_QDRANT_COLLECTION: str = "rag_chunks"
    RAG_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    RAG_VECTOR_SIZE: int = 384

    RAG_DEFAULT_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.25
    RAG_MIN_RELEVANT_SCORE: float = 0.55
    RAG_RETRIEVAL_CANDIDATE_MULTIPLIER: int = 4
    RAG_MAX_CONTEXT_CHARS: int = 6000
    RAG_MAX_SOURCE_TEXT_CHARS: int = 1200
    RAG_MAX_CHUNKS_PER_SOURCE: int = 2
    RAG_DEDUP_TEXT_SIMILARITY: float = 0.88
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 120

    RAG_STORAGE_DIR: str = "/data/rag"

    # Parsing URL
    # basic = parser historique httpx/trafilatura
    # crawl4ai = navigateur Crawl4AI + raw_markdown + nettoyage léger
    # auto = Crawl4AI puis fallback basic en cas d'erreur
    RAG_URL_PARSER_BACKEND: str = "basic"
    RAG_CRAWL4AI_LIGHT_CLEANING: bool = True
    RQ_RAG_QUEUE: str = "rag"

settings = Settings()