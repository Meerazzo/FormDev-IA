"""Dépendances partagées par les sous-routers RAG.

Le package `routers.rag` découpe les routes par responsabilité HTTP
sans modifier les services métier existants.
"""

import json

from fastapi.security import APIKeyHeader

from core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
RATE_LIMIT_RPM = settings.RATE_LIMIT_RPM


def format_sse_event(event: str, data: dict) -> str:
    """Formate un événement Server-Sent Events compatible fetch streaming."""
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )
