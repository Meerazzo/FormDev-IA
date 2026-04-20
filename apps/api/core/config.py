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


settings = Settings()