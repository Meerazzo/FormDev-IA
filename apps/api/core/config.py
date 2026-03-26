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
    """
    VLLM_BASE_URL: str = "http://localhost:8000"
    RATE_LIMIT_RPM: int = 30
    API_KEYS: str = ""
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str

settings = Settings()