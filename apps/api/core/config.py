"""
Configuration centrale de l'application.

Les paramètres sont chargés depuis les variables d'environnement
grâce à pydantic-settings.

Cela permet de modifier facilement la configuration selon
l'environnement (dev, staging, production) sans changer le code.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Paramètres de configuration utilisés dans l'application.

    VLLM_BASE_URL : adresse du serveur d'inférence vLLM
    RATE_LIMIT_RPM : limite de requêtes par minute
    API_KEYS : liste des clés API autorisées
    LOG_LEVEL : niveau de logs (INFO, DEBUG, etc.)
    DATABASE_URL : URL de connexion PostgreSQL
    QDRANT_URL : URL du serveur Qdrant
    QDRANT_COLLECTION : nom de la collection d'exemples
    QDRANT_EMBEDDING_MODEL : modèle d'embedding utilisé pour les exemples
    QDRANT_VECTOR_SIZE : taille des vecteurs générés
    """
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