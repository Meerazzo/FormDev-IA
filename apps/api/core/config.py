from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    VLLM_BASE_URL: str = "http://localhost:8000"
    RATE_LIMIT_RPM: int = 30
    API_KEYS_RAW: str = ""
    LOG_LEVEL: str = "INFO"

settings = Settings()